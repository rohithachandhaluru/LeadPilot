import os
import base64

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from google_auth_oauthlib.flow import Flow
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

from email.mime.text import MIMEText


router = APIRouter(
    prefix="/gmail",
    tags=["Gmail"]
)


# Gmail permission
SCOPES = [
    "https://www.googleapis.com/auth/gmail.send"
]


CLIENT_SECRET_FILE = "credentials.json"

REDIRECT_URI = "http://localhost:8000/gmail/callback"


# Temporary storage for development
credentials_storage = {}


class EmailRequest(BaseModel):
    to: str
    subject: str
    body: str


def create_flow():

    flow = Flow.from_client_secrets_file(
        CLIENT_SECRET_FILE,
        scopes=SCOPES
    )

    flow.redirect_uri = REDIRECT_URI

    return flow


# -----------------------------------------
# Gmail Login
# -----------------------------------------

@router.get("/login")
def gmail_login():

    flow = create_flow()

    authorization_url, state = flow.authorization_url(
        access_type="offline",
        prompt="consent",
        include_granted_scopes="true"
    )

    return {
        "authorization_url": authorization_url,
        "state": state
    }


# -----------------------------------------
# Gmail OAuth Callback
# -----------------------------------------

@router.get("/callback")
def gmail_callback(code: str):

    try:

        flow = create_flow()

        flow.fetch_token(code=code)

        credentials = flow.credentials

        credentials_storage["gmail"] = credentials

        return {
            "message": "Gmail connected successfully"
        }

    except Exception as e:

        raise HTTPException(
            status_code=400,
            detail=str(e)
        )


# -----------------------------------------
# Send Email
# -----------------------------------------

@router.post("/send")
def send_email(request: EmailRequest):

    if "gmail" not in credentials_storage:

        raise HTTPException(
            status_code=401,
            detail="Gmail is not connected"
        )

    try:

        credentials = credentials_storage["gmail"]

        gmail_service = build(
            "gmail",
            "v1",
            credentials=credentials
        )

        # Create email
        message = MIMEText(request.body)

        message["to"] = request.to
        message["subject"] = request.subject

        # Encode email
        encoded_message = base64.urlsafe_b64encode(
            message.as_bytes()
        ).decode()

        email_body = {
            "raw": encoded_message
        }

        # Send through Gmail API
        result = (
            gmail_service
            .users()
            .messages()
            .send(
                userId="me",
                body=email_body
            )
            .execute()
        )

        return {
            "message": "Email sent successfully",
            "gmail_message_id": result["id"]
        }

    except Exception as e:

        raise HTTPException(
            status_code=500,
            detail=str(e)
        )