"""Validates the AI chat 503 handling — run, then delete."""
import json
import os

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'FinSyncAI.settings')
import django
django.setup()

from django.test import Client
from django.contrib.auth import get_user_model
from google.genai.errors import ClientError

from ai.models import AIChatMessage
from ai import views
from ai.ai_services.chat_service import (
    AIServiceUnavailableError,
    ChatService,
    MAX_ATTEMPTS,
)

User = get_user_model()
User.objects.filter(username='aichatsmoke').delete()
user = User.objects.create_user(username='aichatsmoke', email='aichatsmoke@example.com', password='Aichatsmoke123!')

c = Client()
c.login(username='aichatsmoke', password='Aichatsmoke123!')

# ---------- 1. Transient 503 -> friendly 503 JSON, no rows persisted ----------
class Fail503Service:
    def generate_response(self, user, user_message):
        raise AIServiceUnavailableError(
            "AI is unusually busy right now. Please try again in a few seconds — this usually clears up quickly."
        )

views.ChatService = Fail503Service
resp = c.post('/ai/chat/', {'message': 'hello'})
data = resp.json()
print('fail-503 status:', resp.status_code, '| success:', data['success'])
print('fail-503 message:', data['message'])
assert resp.status_code == 503
assert data['success'] is False
assert 'busy' in data['message']
assert not any('raw' in str(data).lower() for _ in [])

rows = AIChatMessage.objects.filter(user=user)
print('rows after failure:', rows.count())
assert rows.count() == 0, 'failed turns must not be persisted'

# ---------- 2. Success path -> 200, user + assistant rows ----------
class OkService:
    def generate_response(self, user, user_message):
        return "Here is your reply."

views.ChatService = OkService
resp = c.post('/ai/chat/', {'message': 'hello again'})
data = resp.json()
print('ok status:', resp.status_code, '| reply:', data['reply'])
assert resp.status_code == 200 and data['success'] is True
rows = AIChatMessage.objects.filter(user=user)
print('rows after success:', rows.count())
assert rows.count() == 2
assert rows.filter(role='user').count() == 1
assert rows.filter(role='assistant').count() == 1

# ---------- 3. ChatService retries transient errors then succeeds ----------
calls = {'n': 0}
def flaky_generate(self, prompt):
    calls['n'] += 1
    if calls['n'] < 3:
        raise ClientError(503, {'error': {'message': 'high demand'}})
    return "recovered reply"

cs = ChatService()
cs._generate = flaky_generate.__get__(cs, ChatService)
reply = cs.generate_response(user, 'retry me')
print('retry calls:', calls['n'], '| reply:', reply)
assert calls['n'] == 3
assert reply == 'recovered reply'

# ---------- 4. Retries exhausted -> friendly error, no raw payload ----------
calls2 = {'n': 0}
def always_fail(self, prompt):
    calls2['n'] += 1
    raise ClientError(503, {'error': {'message': 'high demand'}})

cs2 = ChatService()
cs2._generate = always_fail.__get__(cs2, ChatService)
try:
    cs2.generate_response(user, 'retry exhausted')
    raise AssertionError('expected AIServiceUnavailableError')
except AIServiceUnavailableError as e:
    print('exhausted attempts:', calls2['n'], '| message:', e.friendly_message)
    assert calls2['n'] == MAX_ATTEMPTS
    assert '503' not in e.friendly_message and 'high demand' not in e.friendly_message

# ---------- 5. Non-transient 400 -> immediate friendly error, no retry ----------
calls3 = {'n': 0}
def bad_request(self, prompt):
    calls3['n'] += 1
    raise ClientError(400, {'error': {'message': 'bad prompt'}})

cs3 = ChatService()
cs3._generate = bad_request.__get__(cs3, ChatService)
try:
    cs3.generate_response(user, 'bad')
    raise AssertionError('expected AIServiceUnavailableError')
except AIServiceUnavailableError as e:
    print('bad-request attempts:', calls3['n'], '| message:', e.friendly_message)
    assert calls3['n'] == 1
    assert 'rephras' in e.friendly_message

# ---------- 6. Unexpected exception -> 500 friendly JSON ----------
class BoomService:
    def generate_response(self, user, user_message):
        raise RuntimeError('boom')

views.ChatService = BoomService
resp = c.post('/ai/chat/', {'message': 'x'})
data = resp.json()
print('boom status:', resp.status_code, '| success:', data['success'])
assert resp.status_code == 500 and data['success'] is False
assert 'boom' not in data['message']

User.objects.filter(username='aichatsmoke').delete()
print('AI CHAT ERROR HANDLING TEST OK')