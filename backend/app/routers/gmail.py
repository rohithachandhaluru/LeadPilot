import os
import base64

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from dotenv import load_dotenv

from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request

from email.mime.text import MIMEText


# --------------------------------------------------
# Load environment variables
# --------------------------------------------------

load_dotenv()


# --------------------------------------------------
# Router
# --------------------------------------------------

router = APIRouter(
    prefix="/gmail",
    tags=["Gmail"]
)


# --------------------------------------------------
# Gmail OAuth Configuration
# --------------------------------------------------

SCOPES = [
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.readonly"
]

GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")
REDIRECT_URI = os.getenv("GOOGLE_REDIRECT_URI")


# --------------------------------------------------
# Token Storage
# --------------------------------------------------

# Save token.json in the backend folder
BASE_DIR = os.path.abspath(
    os.path.join(
        os.path.dirname(__file__),
        "..",
        ".."
    )
)

TOKEN_FILE = os.path.join(
    BASE_DIR,
    "token.json"
)


# --------------------------------------------------
# Temporary OAuth Flow Storage
# --------------------------------------------------

oauth_flows = {}


# --------------------------------------------------
# Gmail Credentials Storage
# --------------------------------------------------

credentials_storage = {}


# --------------------------------------------------
# Load previously saved Gmail credentials
# --------------------------------------------------

def load_saved_credentials():

    if not os.path.exists(TOKEN_FILE):
        return

    try:

        credentials = Credentials.from_authorized_user_file(
            TOKEN_FILE,
            SCOPES
        )

        credentials_storage["gmail"] = credentials

        print("Saved Gmail credentials loaded.")

    except Exception as e:

        print(
            f"Could not load saved Gmail credentials: {e}"
        )


# Load credentials when application starts
load_saved_credentials()


# --------------------------------------------------
# Request Models
# --------------------------------------------------

class EmailRequest(BaseModel):
    to: str
    subject: str
    body: str


class Lead(BaseModel):
    email: str
    name: str
    company: str


class BatchEmailRequest(BaseModel):
    recipients: list[Lead]
    subject: str
    body: str


# --------------------------------------------------
# Create Gmail OAuth Flow
# --------------------------------------------------

def create_flow():

    if not GOOGLE_CLIENT_ID:
        raise Exception(
            "GOOGLE_CLIENT_ID is missing in .env"
        )

    if not GOOGLE_CLIENT_SECRET:
        raise Exception(
            "GOOGLE_CLIENT_SECRET is missing in .env"
        )

    if not REDIRECT_URI:
        raise Exception(
            "GOOGLE_REDIRECT_URI is missing in .env"
        )

    client_config = {
        "web": {
            "client_id": GOOGLE_CLIENT_ID,
            "client_secret": GOOGLE_CLIENT_SECRET,
            "auth_uri": (
                "https://accounts.google.com/o/oauth2/auth"
            ),
            "token_uri": (
                "https://oauth2.googleapis.com/token"
            ),
            "redirect_uris": [REDIRECT_URI]
        }
    }

    flow = Flow.from_client_config(
        client_config,
        scopes=SCOPES
    )

    flow.redirect_uri = REDIRECT_URI

    return flow


# --------------------------------------------------
# Gmail Login
# --------------------------------------------------

@router.get("/login")
def gmail_login():

    try:

        flow = create_flow()

        authorization_url, state = (
            flow.authorization_url(
                access_type="offline",
                prompt="consent"
            )
        )

        # Keep flow temporarily for OAuth callback
        oauth_flows[state] = flow

        return {
            "authorization_url": authorization_url,
            "state": state
        }

    except Exception as e:

        raise HTTPException(
            status_code=500,
            detail=str(e)
        )


# --------------------------------------------------
# Gmail OAuth Callback
# --------------------------------------------------

@router.get("/callback")
def gmail_callback(
    code: str,
    state: str
):

    try:

        flow = oauth_flows.get(state)

        if not flow:

            raise HTTPException(
                status_code=400,
                detail=(
                    "OAuth session expired or invalid. "
                    "Please start Gmail login again."
                )
            )

        # Exchange authorization code for tokens
        flow.fetch_token(
            code=code
        )

        credentials = flow.credentials

        # Store credentials in memory
        credentials_storage["gmail"] = credentials

        # ------------------------------------------
        # IMPORTANT:
        # Save credentials permanently
        # ------------------------------------------

        with open(
            TOKEN_FILE,
            "w",
            encoding="utf-8"
        ) as token:

            token.write(
                credentials.to_json()
            )

        # Remove used OAuth flow
        del oauth_flows[state]

        return {
            "message": "Gmail connected successfully"
        }

    except HTTPException:

        raise

    except Exception as e:

        raise HTTPException(
            status_code=400,
            detail=str(e)
        )


# --------------------------------------------------
# Get Gmail Service
# --------------------------------------------------

def get_gmail_service():

    if "gmail" not in credentials_storage:

        raise HTTPException(
            status_code=401,
            detail=(
                "Gmail is not connected. "
                "Please connect Gmail first."
            )
        )

    credentials = credentials_storage["gmail"]

    # ------------------------------------------
    # Refresh expired access token
    # ------------------------------------------

    if credentials.expired:

        if credentials.refresh_token:

            try:

                credentials.refresh(
                    Request()
                )

                # Save refreshed credentials
                with open(
                    TOKEN_FILE,
                    "w",
                    encoding="utf-8"
                ) as token:

                    token.write(
                        credentials.to_json()
                    )

            except Exception as e:

                raise HTTPException(
                    status_code=401,
                    detail=(
                        "Gmail session could not be "
                        f"refreshed: {str(e)}. "
                        "Please connect Gmail again."
                    )
                )

        else:

            raise HTTPException(
                status_code=401,
                detail=(
                    "Gmail authorization has expired. "
                    "Please connect Gmail again."
                )
            )

    return build(
        "gmail",
        "v1",
        credentials=credentials
    )


# --------------------------------------------------
# Send Single Email
# --------------------------------------------------

@router.post("/send")
def send_email(
    request: EmailRequest
):

    try:

        gmail_service = get_gmail_service()

        message = MIMEText(
            request.body
        )

        message["to"] = request.to
        message["subject"] = request.subject

        encoded_message = (
            base64.urlsafe_b64encode(
                message.as_bytes()
            )
            .decode()
        )

        email_body = {
            "raw": encoded_message
        }

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

    except HTTPException:

        raise

    except Exception as e:

        raise HTTPException(
            status_code=500,
            detail=str(e)
        )


# --------------------------------------------------
# Send Personalized Batch Emails
# --------------------------------------------------

@router.post("/send-batch")
def send_batch_emails(
    request: BatchEmailRequest
):

    try:

        gmail_service = get_gmail_service()

        results = []

        successful = 0
        failed = 0

        for lead in request.recipients:

            try:

                personalized_body = (
                    request.body
                    .replace(
                        "{{name}}",
                        lead.name
                    )
                    .replace(
                        "{{company}}",
                        lead.company
                    )
                )

                message = MIMEText(
                    personalized_body
                )

                message["to"] = lead.email
                message["subject"] = request.subject

                encoded_message = (
                    base64.urlsafe_b64encode(
                        message.as_bytes()
                    )
                    .decode()
                )

                email_body = {
                    "raw": encoded_message
                }

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

                successful += 1

                results.append({
                    "email": lead.email,
                    "name": lead.name,
                    "company": lead.company,
                    "status": "sent",
                    "gmail_message_id": result["id"]
                })

            except Exception as e:

                failed += 1

                results.append({
                    "email": lead.email,
                    "name": lead.name,
                    "company": lead.company,
                    "status": "failed",
                    "error": str(e)
                })

        return {
            "total": len(request.recipients),
            "successful": successful,
            "failed": failed,
            "results": results
        }

    except HTTPException:

        raise

    except Exception as e:

        raise HTTPException(
            status_code=500,
            detail=str(e)
        )
# --------------------------------------------------
# Read Recent Gmail Messages
# --------------------------------------------------

@router.get("/inbox")
def get_inbox_messages():

    try:
        gmail_service = get_gmail_service()

        response = (
            gmail_service
            .users()
            .messages()
            .list(
                userId="me",
                maxResults=10
            )
            .execute()
        )

        messages = response.get("messages", [])

        results = []

        for message in messages:

            message_id = message["id"]

            message_data = (
                gmail_service
                .users()
                .messages()
                .get(
                    userId="me",
                    id=message_id,
                    format="full"
                )
                .execute()
            )

            headers = message_data["payload"].get("headers", [])

            sender = ""
            subject = ""

            for header in headers:

                if header["name"].lower() == "from":
                    sender = header["value"]

                elif header["name"].lower() == "subject":
                    subject = header["value"]

            results.append({
                "message_id": message_id,
                "sender": sender,
                "subject": subject,
                "snippet": message_data.get("snippet", "")
            })

        return {
            "total": len(results),
            "messages": results
        }

    except HTTPException:
        raise

    except Exception as e:

        raise HTTPException(
            status_code=500,
            detail=str(e)
        )