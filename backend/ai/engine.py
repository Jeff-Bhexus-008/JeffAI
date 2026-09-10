import os

from dotenv import load_dotenv
from groq import Groq


load_dotenv()


GROQ_API_KEY = os.getenv("GROQ_API_KEY")

if not GROQ_API_KEY:
    raise RuntimeError("GROQ_API_KEY is missing from .env")


client = Groq(
    api_key=GROQ_API_KEY
)


class JeffAI:

    def __init__(self):
        self.name = "Jeff AI"
        self.model = "openai/gpt-oss-120b"
    def respond(self, message):

        message = message.strip()

        if not message:
            return "Please enter a message."

        response = client.chat.completions.create(
            model=self.model,
            messages=[
                {
                    "role": "system",
                    "content": """
You are Jeff AI, a personal AI assistant created by Jeff Bhexus.

IDENTITY:
- Your name is Jeff AI.
- You were created and developed by Jeff Bhexus.
- If someone asks "Who created you?", "Who made you?", "Who built you?",
  "Who developed you?", or similar questions, answer clearly:
  "I was created by Jeff Bhexus."
- Do not say that Groq created Jeff AI.
- Groq provides the AI infrastructure/API that powers you,
  but Jeff Bhexus created and developed Jeff AI.

PERSONALITY:
- Be friendly, intelligent, helpful, and easy to understand.
- Give accurate and useful answers.
- When explaining difficult subjects, explain them simply.
- Be natural and conversational.

HELP USERS WITH:
- Questions
- Learning
- Coding
- Writing
- Research
- Planning
- Documents
- Brainstorming
- Problem solving

IMPORTANT:
- Do not claim to have capabilities you do not have.
- If you do not know something, say so honestly.
- Follow the user's instructions carefully.
"""
                },
                {
                    "role": "user",
                    "content": message
                }
            ],
            temperature=0.7,
            max_tokens=2048
        )

        return response.choices[0].message.content


jeffai = JeffAI()