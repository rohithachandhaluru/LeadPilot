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


def generate_reply(
    lead_name: str,
    lead_company: str,
    campaign_subject: str,
    campaign_body: str,
    customer_reply: str,
    intent: str,
    knowledge_context: str
):
    """
    Generate a professional email reply based on:
    - Lead context (name, company)
    - Original campaign email
    - Customer's reply
    - Classified intent
    - Relevant company knowledge
    """

    # --------------------------------------------------
    # Build intent-specific instruction
    # --------------------------------------------------

    intent_instruction = {
        "interested": (
            "The lead is interested. "
            "Write a warm, enthusiastic follow-up. "
            "Thank them for their interest, "
            "highlight the key value, "
            "and suggest a clear next step."
        ),
        "needs_more_information": (
            "The lead needs more information. "
            "Use the company knowledge provided below to answer their question. "
            "Be specific and helpful. "
            "Do not invent facts not in the knowledge context."
        ),
        "meeting_request": (
            "The lead wants to schedule a meeting. "
            "Respond warmly, confirm availability, "
            "and suggest they pick a time or share your calendar link. "
            "Keep it professional and concise."
        ),
        "not_interested": (
            "The lead is not interested. "
            "Respond politely. "
            "Thank them for their time. "
            "Do not push aggressively. "
            "Leave the door open for the future."
        ),
        "unclear": (
            "The lead's reply is unclear. "
            "Respond politely and ask a simple clarifying question. "
            "Do not assume their intent. "
            "Keep your reply brief."
        ),
    }.get(intent, (
        "Respond professionally and helpfully based on the reply."
    ))

    # --------------------------------------------------
    # Build prompt
    # --------------------------------------------------

    knowledge_section = (
        f"Company Knowledge:\n{knowledge_context}"
        if knowledge_context
        else "Company Knowledge: Not available."
    )

    prompt = f"""
You are a professional sales representative writing an email reply on behalf of your company.

Lead Name: {lead_name}
Lead Company: {lead_company}

Original Campaign Email:
Subject: {campaign_subject}
Body:
{campaign_body}

Customer Reply:
{customer_reply}

Detected Intent: {intent}

{knowledge_section}

Instructions:
{intent_instruction}

Rules:
- Address the lead by their first name.
- Write only the email body. Do not write a subject line.
- Do not include placeholders like [Your Name] or [Company Name].
- Do not invent any company information not found in the Company Knowledge.
- Keep the tone professional and friendly.
- Maximum 150 words.

Write the email reply now:
"""

    response = client.interactions.create(
        model="gemini-3.8-flash",
        input=prompt,
        timeout=30
    )

    return response.output_text.strip()