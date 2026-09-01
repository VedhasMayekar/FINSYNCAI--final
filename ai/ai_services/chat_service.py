import os

from dotenv import load_dotenv
from google import genai

from .prompt_builder import PromptBuilder

load_dotenv()


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

    def generate_response(
        self,
        user,
        user_message: str,
    ) -> str:
        """
        Generate a response using Gemini.
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

        response = self.client.models.generate_content(
            model=self.model,
            contents=prompt
        )

        if hasattr(response, "text") and response.text:
            return response.text.strip()

        return "I'm sorry, I couldn't generate a response."

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