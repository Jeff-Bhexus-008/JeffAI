import os

from dotenv import load_dotenv
from openai import OpenAI


load_dotenv()


OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

if not OPENAI_API_KEY:
    raise RuntimeError("OPENAI_API_KEY is missing from .env")


client = OpenAI(
    api_key=OPENAI_API_KEY
)


class JeffAI:

    def __init__(self):
        self.name = "Jeff AI"
        self.model = "gpt-5.6-luna"

    def respond(self, message):

        message = message.strip()

        if not message:
            return "Please enter a message."

        response = client.responses.create(
            model=self.model,
            instructions="""
You are Jeff AI, a helpful personal AI assistant.

Your name is Jeff AI.

Be friendly, intelligent, helpful, and easy to understand.

Give accurate and useful answers.

When explaining difficult subjects, explain them simply.

Help users with:
- Questions
- Learning
- Coding
- Writing
- Research
- Planning
- Documents
- Brainstorming
- Problem solving

Do not claim to have capabilities you do not have.
""",
            input=message
        )

        return response.output_text


jeffai = JeffAI()