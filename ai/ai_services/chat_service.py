import logging
import os
import time

from dotenv import load_dotenv
from google import genai
from google.genai.errors import APIError

from .prompt_builder import PromptBuilder

load_dotenv()

logger = logging.getLogger(__name__)

# Google's GenAI SDK surfaces HTTP status codes on its errors. These codes
# mean "transient overload / quota" and are retry-safe. Gemini 503s are
# typically short demand spikes — Google's guidance is to retry with backoff.
TRANSIENT_STATUS_CODES = {429, 500, 502, 503}

# Retry policy for transient failures (attempts + sleep seconds between tries)
MAX_ATTEMPTS = 3
BACKOFF_SECONDS = (1.0, 2.0)


class AIServiceUnavailableError(Exception):
    """User-safe error raised once the AI retry budget is exhausted."""

    def __init__(self, friendly_message: str):
        super().__init__(friendly_message)
        self.friendly_message = friendly_message


def _status_code(exc: Exception):
    """HTTP status code from google-genai APIError, else None."""
    if isinstance(exc, APIError):
        code = getattr(exc, "code", None)
        if isinstance(code, int):
            return code
    return None


def _friendly_error(code) -> AIServiceUnavailableError:
    """Map a non-retryable HTTP status to a user-safe error."""
    if code == 400:
        return AIServiceUnavailableError(
            "The AI couldn't process that request. Please try rephrasing."
        )
    if code == 401:
        return AIServiceUnavailableError(
            "The AI service key is invalid. Please contact support."
        )
    if code == 403:
        return AIServiceUnavailableError(
            "The AI service isn't configured for this environment. Please contact support."
        )
    return AIServiceUnavailableError(
        "Something went wrong while reaching the AI. Please try again."
    )


class ChatService:
    """
    Handles all communication with the Gemini API.
    """

    def __init__(self):
        self.api_key = os.getenv("GEMINI_API_KEY")

        if not self.api_key:
            raise ValueError("GEMINI_API_KEY not found.")

        self.client = genai.Client(api_key=self.api_key)

        # Use a stable Gemini flash model. This is intentionally not the
        # experimental preview name — it must exist for every account.
        self.model = os.getenv("GEMINI_MODEL", "gemini-3.6-flash")

    def _generate(self, prompt: str) -> str:
        """Single generate_content call without retry logic."""
        response = self.client.models.generate_content(
            model=self.model,
            contents=prompt
        )

        if hasattr(response, "text") and response.text:
            return response.text.strip()

        return "I'm sorry, I couldn't generate a response."

    def generate_response(
        self,
        user,
        user_message: str,
    ) -> str:
        """
        Generate a response using Gemini.

        Transient API outages (503 high demand, 429 quota, 500/502) are
        retried with a short backoff before a user-friendly error is raised —
        the raw API payload is never surfaced to the caller.
        """

        system_prompt, user_prompt = PromptBuilder.build(
            user,
            user_message
        )

        prompt = f"""
        {system_prompt}

        ----------------------------------------

        USER MESSAGE

        {user_prompt}
"""

        for attempt in range(1, MAX_ATTEMPTS + 1):
            try:
                return self._generate(prompt)
            except Exception as exc:
                code = _status_code(exc)
                transient = code is not None and code in TRANSIENT_STATUS_CODES

                if transient and attempt < MAX_ATTEMPTS:
                    wait = BACKOFF_SECONDS[min(attempt - 1, len(BACKOFF_SECONDS) - 1)]
                    logger.warning(
                        "Gemini transient error (HTTP %s) on attempt %s/%s — "
                        "retrying in %ss.",
                        code, attempt, MAX_ATTEMPTS, wait,
                    )
                    time.sleep(wait)
                    continue

                if transient:
                    logger.warning(
                        "Gemini still busy after %s attempts (HTTP %s).",
                        attempt, code,
                    )
                    raise AIServiceUnavailableError(
                        "AI is unusually busy right now. Please try again in a "
                        "few seconds — this usually clears up quickly."
                    )

                logger.exception("Gemini request failed (HTTP %s).", code)
                raise _friendly_error(code)

        # Unreachable — the loop always returns or raises above.
        raise AIServiceUnavailableError(
            "Something went wrong while reaching the AI. Please try again."
        )

    def health_check(self) -> bool:
        """
        Checks whether Gemini is reachable.
        """

        try:
            response = self.client.models.generate_content(
                model=self.model,
                contents="Reply only with OK."
            )

            return bool(response.text)

        except Exception:
            return False