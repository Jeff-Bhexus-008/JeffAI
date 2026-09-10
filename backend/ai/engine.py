import os

from dotenv import load_dotenv
from groq import Groq
from openai import OpenAI


load_dotenv()


GROQ_API_KEY = os.getenv("GROQ_API_KEY")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")


if not GROQ_API_KEY:
    raise RuntimeError("GROQ_API_KEY is missing from .env")

if not OPENROUTER_API_KEY:
    raise RuntimeError("OPENROUTER_API_KEY is missing from .env")


groq_client = Groq(
    api_key=GROQ_API_KEY
)


openrouter_client = OpenAI(
    api_key=OPENROUTER_API_KEY,
    base_url="https://openrouter.ai/api/v1"
)


class JeffAI:

    def __init__(self):
        self.name = "Jeff AI"

        self.providers = [
            {
                "name": "Groq",
                "client": groq_client,
                "model": "openai/gpt-oss-120b"
            },
            {
                "name": "OpenRouter",
                "client": openrouter_client,
                "model": "openai/gpt-oss-120b"
            }
        ]

        self.system_prompt = """
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

    def respond(self, message):

        message = message.strip()

        if not message:
            return "Please enter a message."

        last_error = None

        for provider in self.providers:

            try:

                print(f"JeffAI trying {provider['name']}...")

                response = provider["client"].chat.completions.create(
                    model=provider["model"],
                    messages=[
                        {
                            "role": "system",
                            "content": self.system_prompt
                        },
                        {
                            "role": "user",
                            "content": message
                        }
                    ],
                    temperature=0.7,
                    max_tokens=2048
                )

                print(f"JeffAI response from {provider['name']}")

                return response.choices[0].message.content

            except Exception as error:

                last_error = error

                print(
                    f"{provider['name']} failed: {error}"
                )

                print(
                    f"Trying next provider..."
                )

        return (
            "I'm temporarily unable to respond because "
            "all of my AI providers are unavailable."
        )


jeffai = JeffAI()