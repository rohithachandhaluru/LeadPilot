import os

from dotenv import load_dotenv
from google import genai


# Load environment variables
load_dotenv()


# Get Gemini API key
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

if not GEMINI_API_KEY:
    raise Exception(
        "GEMINI_API_KEY is missing in .env"
    )


# Create Gemini client
client = genai.Client(
    api_key=GEMINI_API_KEY
)


def analyze_lead_reply(reply: str):

    prompt = f"""
You are an AI lead qualification assistant.

Analyze the following email reply from a potential customer.

Classify the reply into exactly ONE of these intents:

- interested
- not_interested
- needs_more_information
- meeting_request
- unclear

Email reply:
{reply}

Return ONLY the intent name.
Do not explain your answer.
"""

    response = client.interactions.create(
        model="gemini-3.8-flash",
        input=prompt,
        timeout=30
    )

    return response.output_text.strip().lower()