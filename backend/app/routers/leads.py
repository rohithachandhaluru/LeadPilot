import pandas as pd
import base64
import re

from io import BytesIO
from email.mime.text import MIMEText
from email.utils import parseaddr
from datetime import datetime, timezone

from fastapi import APIRouter, UploadFile, File, HTTPException
from pydantic import BaseModel

from app.routers.gmail import get_gmail_service
from database.supabase import supabase


router = APIRouter(
    prefix="/leads",
    tags=["Leads"]
)


# --------------------------------------------------
# Required columns
# --------------------------------------------------

REQUIRED_COLUMNS = [
    "name",
    "email",
    "company"
]


# --------------------------------------------------
# Temporary lead storage
# --------------------------------------------------

uploaded_leads = []

# Prevent sending the same uploaded list twice
campaign_sent = False


# --------------------------------------------------
# Send Request Model
# --------------------------------------------------

class LeadSendRequest(BaseModel):
    subject: str
    body: str


# --------------------------------------------------
# Upload Leads
# --------------------------------------------------

@router.post("/upload")
async def upload_leads(
    file: UploadFile = File(...)
):

    global uploaded_leads
    global campaign_sent

    try:

        # ------------------------------------------
        # Reset current in-memory campaign
        # ------------------------------------------

        uploaded_leads = []
        campaign_sent = False

        # ------------------------------------------
        # Check filename
        # ------------------------------------------

        if not file.filename:
            raise HTTPException(
                status_code=400,
                detail="No file selected."
            )

        filename = file.filename.lower()

        # ------------------------------------------
        # Check file format
        # ------------------------------------------

        if not (
            filename.endswith(".xlsx")
            or filename.endswith(".xls")
            or filename.endswith(".csv")
        ):
            raise HTTPException(
                status_code=400,
                detail=(
                    "Invalid file format. "
                    "Please upload an Excel or CSV file."
                )
            )

        # ------------------------------------------
        # Read uploaded file
        # ------------------------------------------

        file_content = await file.read()

        if not file_content:
            raise HTTPException(
                status_code=400,
                detail="Uploaded file is empty."
            )

        # ------------------------------------------
        # Read CSV
        # ------------------------------------------

        if filename.endswith(".csv"):

            df = pd.read_csv(
                BytesIO(file_content)
            )

        # ------------------------------------------
        # Read Excel
        # ------------------------------------------

        else:

            df = pd.read_excel(
                BytesIO(file_content)
            )

        # ------------------------------------------
        # Check empty file
        # ------------------------------------------

        if df.empty:
            raise HTTPException(
                status_code=400,
                detail="The uploaded file contains no data."
            )

        # ------------------------------------------
        # Clean column names
        # ------------------------------------------

        df.columns = (
            df.columns
            .astype(str)
            .str.strip()
            .str.lower()
        )

        # ------------------------------------------
        # Check required columns
        # ------------------------------------------

        missing_columns = [
            column
            for column in REQUIRED_COLUMNS
            if column not in df.columns
        ]

        if missing_columns:

            raise HTTPException(
                status_code=400,
                detail={
                    "message": "Missing required columns.",
                    "missing_columns": missing_columns,
                    "required_columns": REQUIRED_COLUMNS
                }
            )

        # ------------------------------------------
        # Add optional unsubscribe column
        # ------------------------------------------

        if "unsubscribed" not in df.columns:
            df["unsubscribed"] = ""

        # ------------------------------------------
        # Keep required columns
        # ------------------------------------------

        df = df[
            [
                "name",
                "email",
                "company",
                "unsubscribed"
            ]
        ].copy()

        # ------------------------------------------
        # Remove completely empty rows
        # ------------------------------------------

        df = df.dropna(
            how="all"
        )

        # ------------------------------------------
        # Clean values
        # ------------------------------------------

        for column in [
            "name",
            "email",
            "company",
            "unsubscribed"
        ]:

            df[column] = (
                df[column]
                .fillna("")
                .astype(str)
                .str.strip()
            )

        # ------------------------------------------
        # Normalize email
        # ------------------------------------------

        df["email"] = (
            df["email"]
            .str.lower()
            .str.strip()
        )

        # ------------------------------------------
        # Remove empty emails
        # ------------------------------------------

        df = df[
            df["email"] != ""
        ]

        # ------------------------------------------
        # Count duplicates inside Excel
        # ------------------------------------------

        duplicate_count = int(
            df.duplicated(
                subset=["email"],
                keep="first"
            ).sum()
        )

        # ------------------------------------------
        # Remove duplicates
        # ------------------------------------------

        df = df.drop_duplicates(
            subset=["email"],
            keep="first"
        )

        # ------------------------------------------
        # Validate leads
        # ------------------------------------------

        valid_leads = []
        invalid_leads = []

        for _, row in df.iterrows():

            name = str(
                row["name"]
            ).strip()

            email = str(
                row["email"]
            ).strip()

            company = str(
                row["company"]
            ).strip()

            unsubscribe_value = str(
                row["unsubscribed"]
            ).strip().lower()

            # --------------------------------------
            # Validate email
            # --------------------------------------

            if (
                "@" not in email
                or "." not in email.split("@")[-1]
            ):

                invalid_leads.append({
                    "name": name,
                    "email": email,
                    "company": company,
                    "reason": "Invalid email format"
                })

                continue

            # --------------------------------------
            # Validate name
            # --------------------------------------

            if not name:

                invalid_leads.append({
                    "name": name,
                    "email": email,
                    "company": company,
                    "reason": "Name is empty"
                })

                continue

            # --------------------------------------
            # Validate company
            # --------------------------------------

            if not company:

                invalid_leads.append({
                    "name": name,
                    "email": email,
                    "company": company,
                    "reason": "Company is empty"
                })

                continue

            # --------------------------------------
            # Check unsubscribe
            # --------------------------------------

            unsubscribe_values = [
                "yes",
                "true",
                "1",
                "unsubscribe",
                "unsubscribed"
            ]

            is_unsubscribed = (
                unsubscribe_value
                in unsubscribe_values
            )

            # --------------------------------------
            # Add valid lead
            # --------------------------------------

            valid_leads.append({
                "name": name,
                "email": email,
                "company": company,
                "unsubscribed": is_unsubscribed
            })

        # ------------------------------------------
        # Save leads to Supabase
        # ------------------------------------------

        if valid_leads:

            supabase_leads = []

            for lead in valid_leads:

                supabase_leads.append({
                    "name": lead["name"],
                    "email": lead["email"],
                    "company": lead["company"],
                    "unsubscribed": lead["unsubscribed"]
                })

            (
                supabase
                .table("leads")
                .upsert(
                    supabase_leads,
                    on_conflict="email"
                )
                .execute()
            )

            # --------------------------------------
            # Get database IDs
            # --------------------------------------

            saved_emails = [
                lead["email"]
                for lead in valid_leads
            ]

            db_response = (
                supabase
                .table("leads")
                .select(
                    "id,name,email,company,unsubscribed"
                )
                .in_(
                    "email",
                    saved_emails
                )
                .execute()
            )

            database_leads = {
                row["email"]: row
                for row in db_response.data
            }

            # --------------------------------------
            # Attach Supabase ID to each lead
            # --------------------------------------

            for lead in valid_leads:

                database_lead = database_leads.get(
                    lead["email"]
                )

                if database_lead:

                    lead["id"] = database_lead["id"]

        # ------------------------------------------
        # Store current leads in memory
        # ------------------------------------------

        uploaded_leads = valid_leads

        # ------------------------------------------
        # Counts
        # ------------------------------------------

        unsubscribed_count = int(
            sum(
                1
                for lead in valid_leads
                if lead["unsubscribed"]
            )
        )

        sendable_count = int(
            len(valid_leads)
            - unsubscribed_count
        )

        total_rows = int(
            len(valid_leads)
            + len(invalid_leads)
            + duplicate_count
        )

        # ------------------------------------------
        # Return
        # ------------------------------------------

        return {
            "message": "Leads uploaded successfully",
            "filename": file.filename,
            "total_rows": total_rows,
            "valid_leads": len(valid_leads),
            "invalid_leads": len(invalid_leads),
            "duplicates_removed": duplicate_count,
            "unsubscribed_leads": unsubscribed_count,
            "sendable_leads": sendable_count,
            "leads": valid_leads,
            "invalid_records": invalid_leads
        }

    except HTTPException:
        raise

    except Exception as e:

        raise HTTPException(
            status_code=500,
            detail=str(e)
        )


# --------------------------------------------------
# Get Uploaded Leads
# --------------------------------------------------

@router.get("/")
def get_uploaded_leads():

    return {
        "total": len(uploaded_leads),
        "leads": uploaded_leads
    }


# --------------------------------------------------
# Send Uploaded Leads
# --------------------------------------------------

@router.post("/send")
def send_uploaded_leads(
    request: LeadSendRequest
):

    global campaign_sent

    # ------------------------------------------
    # Check leads
    # ------------------------------------------

    if not uploaded_leads:

        raise HTTPException(
            status_code=400,
            detail=(
                "No leads uploaded. "
                "Please upload an Excel or CSV file first."
            )
        )

    # ------------------------------------------
    # Prevent duplicate campaign
    # ------------------------------------------

    if campaign_sent:

        raise HTTPException(
            status_code=400,
            detail=(
                "This uploaded lead list has already "
                "been processed. Upload a new file "
                "before sending another campaign."
            )
        )

    try:

        # ------------------------------------------
        # Create campaign in Supabase
        # ------------------------------------------

        campaign_response = (
            supabase
            .table("campaigns")
            .insert({
                "subject": request.subject,
                "body": request.body
            })
            .execute()
        )

        if not campaign_response.data:

            raise HTTPException(
                status_code=500,
                detail="Failed to create campaign in Supabase."
            )

        campaign_id = campaign_response.data[0]["id"]

        # ------------------------------------------
        # Gmail service
        # ------------------------------------------

        gmail_service = get_gmail_service()

        results = []

        successful = 0
        failed = 0
        skipped = 0

        # ------------------------------------------
        # Send to every lead
        # ------------------------------------------

        for lead in uploaded_leads:

            # --------------------------------------
            # Skip unsubscribed
            # --------------------------------------

            if lead["unsubscribed"]:

                skipped += 1

                results.append({
                    "name": lead["name"],
                    "email": lead["email"],
                    "company": lead["company"],
                    "status": "skipped",
                    "reason": "Lead is unsubscribed"
                })

                continue

            try:

                # ----------------------------------
                # Personalize
                # ----------------------------------

                personalized_body = (
                    request.body
                    .replace(
                        "{{name}}",
                        lead["name"]
                    )
                    .replace(
                        "{{company}}",
                        lead["company"]
                    )
                )

                # ----------------------------------
                # Create email
                # ----------------------------------

                message = MIMEText(
                    personalized_body
                )

                message["to"] = lead["email"]
                message["subject"] = request.subject

                # ----------------------------------
                # Encode
                # ----------------------------------

                encoded_message = (
                    base64.urlsafe_b64encode(
                        message.as_bytes()
                    )
                    .decode()
                )

                # ----------------------------------
                # Send Gmail
                # ----------------------------------

                result = (
                    gmail_service
                    .users()
                    .messages()
                    .send(
                        userId="me",
                        body={
                            "raw": encoded_message
                        }
                    )
                    .execute()
                )

                gmail_message_id = result["id"]

                gmail_thread_id = result.get(
                    "threadId"
                )

                sent_at = datetime.now(
                    timezone.utc
                ).isoformat()

                # ----------------------------------
                # Store IDs in memory
                # ----------------------------------

                lead["gmail_message_id"] = (
                    gmail_message_id
                )

                lead["gmail_thread_id"] = (
                    gmail_thread_id
                )

                lead["campaign_id"] = campaign_id

                # ----------------------------------
                # Save campaign lead
                # ----------------------------------

                (
                    supabase
                    .table("campaign_leads")
                    .insert({
                        "campaign_id": campaign_id,
                        "lead_id": lead["id"],
                        "gmail_message_id": (
                            gmail_message_id
                        ),
                        "gmail_thread_id": (
                            gmail_thread_id
                        ),
                        "status": "sent",
                        "sent_at": sent_at
                    })
                    .execute()
                )

                # ----------------------------------
                # Save sent email
                # ----------------------------------

                (
                    supabase
                    .table("email_messages")
                    .insert({
                        "lead_id": lead["id"],
                        "campaign_id": campaign_id,
                        "gmail_message_id": (
                            gmail_message_id
                        ),
                        "gmail_thread_id": (
                            gmail_thread_id
                        ),
                        "direction": "sent",
                        "subject": request.subject,
                        "body": personalized_body
                    })
                    .execute()
                )

                successful += 1

                # ----------------------------------
                # API result
                # ----------------------------------

                results.append({
                    "name": lead["name"],
                    "email": lead["email"],
                    "company": lead["company"],
                    "status": "sent",
                    "gmail_message_id": (
                        gmail_message_id
                    ),
                    "gmail_thread_id": (
                        gmail_thread_id
                    ),
                    "campaign_id": campaign_id
                })

            except Exception as e:

                failed += 1

                results.append({
                    "name": lead["name"],
                    "email": lead["email"],
                    "company": lead["company"],
                    "status": "failed",
                    "error": str(e)
                })

        # ------------------------------------------
        # Mark campaign as processed
        # ------------------------------------------

        campaign_sent = True

        # ------------------------------------------
        # Return result
        # ------------------------------------------

        return {
            "message": "Lead email sending completed",
            "campaign_id": campaign_id,
            "total": len(uploaded_leads),
            "successful": successful,
            "failed": failed,
            "skipped": skipped,
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
# Clean Email Reply
# --------------------------------------------------

def clean_email_reply(body: str) -> str:

    if not body:
        return ""

    # Normalize line endings
    body = body.replace(
        "\r\n",
        "\n"
    )

    body = body.replace(
        "\r",
        "\n"
    )

    # Remove quoted Gmail conversation
    body = re.split(
        r"\nOn .+",
        body,
        maxsplit=1,
        flags=re.IGNORECASE | re.DOTALL
    )[0]

    # Remove quoted lines
    lines = body.split("\n")

    cleaned_lines = []

    for line in lines:

        if line.strip().startswith(">"):
            break

        cleaned_lines.append(line)

    return "\n".join(
        cleaned_lines
    ).strip()


# --------------------------------------------------
# Extract Plain Text Email Body
# --------------------------------------------------

def extract_plain_text_body(payload):

    if not payload:
        return ""

    # ------------------------------------------
    # Direct text/plain
    # ------------------------------------------

    body_data = (
        payload
        .get("body", {})
        .get("data")
    )

    if (
        body_data
        and payload.get("mimeType")
        == "text/plain"
    ):

        try:

            return base64.urlsafe_b64decode(
                body_data
            ).decode(
                "utf-8",
                errors="ignore"
            )

        except Exception:

            return ""

    # ------------------------------------------
    # Multipart
    # ------------------------------------------

    parts = payload.get(
        "parts",
        []
    )

    for part in parts:

        mime_type = part.get(
            "mimeType"
        )

        # --------------------------------------
        # text/plain
        # --------------------------------------

        if mime_type == "text/plain":

            body_data = (
                part
                .get("body", {})
                .get("data")
            )

            if body_data:

                try:

                    return base64.urlsafe_b64decode(
                        body_data
                    ).decode(
                        "utf-8",
                        errors="ignore"
                    )

                except Exception:

                    pass

        # --------------------------------------
        # Nested multipart
        # --------------------------------------

        if part.get("parts"):

            nested_body = (
                extract_plain_text_body(
                    part
                )
            )

            if nested_body:

                return nested_body

    return ""


# --------------------------------------------------
# Get Replies From Campaign Leads
# --------------------------------------------------

@router.get("/replies")
def get_lead_replies():

    try:

        # ------------------------------------------
        # Get campaign leads from Supabase
        # ------------------------------------------

        campaign_leads_response = (
            supabase
            .table("campaign_leads")
            .select(
                """
                id,
                campaign_id,
                lead_id,
                gmail_message_id,
                gmail_thread_id,
                status,
                sent_at
                """
            )
            .execute()
        )

        campaign_leads = (
            campaign_leads_response.data
            or []
        )

        if not campaign_leads:

            return {
                "total_replies": 0,
                "replies": [],
                "message": "No campaign emails found."
            }

        # ------------------------------------------
        # Get lead IDs
        # ------------------------------------------

        lead_ids = list({
            row["lead_id"]
            for row in campaign_leads
            if row.get("lead_id") is not None
        })

        if not lead_ids:

            return {
                "total_replies": 0,
                "replies": []
            }

        # ------------------------------------------
        # Get leads from Supabase
        # ------------------------------------------

        leads_response = (
            supabase
            .table("leads")
            .select(
                "id,name,email,company,unsubscribed"
            )
            .in_(
                "id",
                lead_ids
            )
            .execute()
        )

        leads_data = (
            leads_response.data
            or []
        )

        leads_by_id = {
            lead["id"]: lead
            for lead in leads_data
        }

        # ------------------------------------------
        # Create thread lookup
        # ------------------------------------------

        campaign_by_thread = {}

        for campaign_lead in campaign_leads:

            thread_id = (
                campaign_lead.get(
                    "gmail_thread_id"
                )
            )

            if not thread_id:
                continue

            lead = leads_by_id.get(
                campaign_lead["lead_id"]
            )

            if not lead:
                continue

            campaign_by_thread[thread_id] = {
                "campaign_lead": campaign_lead,
                "lead": lead
            }

        # ------------------------------------------
        # Gmail service
        # ------------------------------------------

        gmail_service = get_gmail_service()

        # ------------------------------------------
        # Get incoming messages only
        # ------------------------------------------

        response = (
            gmail_service
            .users()
            .messages()
            .list(
                userId="me",
                q="in:inbox -from:me",
                maxResults=50
            )
            .execute()
        )

        messages = response.get(
            "messages",
            []
        )

        replies = []

        # ------------------------------------------
        # Process Gmail messages
        # ------------------------------------------

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

            message_thread_id = (
                message_data.get("threadId")
            )

            # --------------------------------------
            # Match thread with campaign
            # --------------------------------------

            matched_campaign = (
                campaign_by_thread.get(
                    message_thread_id
                )
            )

            if not matched_campaign:
                continue

            campaign_lead = (
                matched_campaign["campaign_lead"]
            )

            lead = (
                matched_campaign["lead"]
            )

            payload = message_data.get(
                "payload",
                {}
            )

            headers = payload.get(
                "headers",
                []
            )

            sender = ""
            subject = ""

            # --------------------------------------
            # Read headers
            # --------------------------------------

            for header in headers:

                header_name = (
                    header["name"]
                    .lower()
                )

                if header_name == "from":

                    sender = header["value"]

                elif header_name == "subject":

                    subject = header["value"]

            # --------------------------------------
            # Sender email
            # --------------------------------------

            sender_email = (
                parseaddr(sender)[1]
                .lower()
                .strip()
            )

            lead_email = (
                lead["email"]
                .lower()
                .strip()
            )

            # --------------------------------------
            # Verify sender
            # --------------------------------------

            if sender_email != lead_email:
                continue

            # --------------------------------------
            # Extract body
            # --------------------------------------

            raw_body = (
                extract_plain_text_body(
                    payload
                )
            )

            clean_body = (
                clean_email_reply(
                    raw_body
                )
            )

            # --------------------------------------
            # Ignore empty reply
            # --------------------------------------

            if not clean_body:
                continue

            # --------------------------------------
            # Prevent duplicate database entry
            # --------------------------------------

            existing_response = (
                supabase
                .table("email_messages")
                .select("id")
                .eq(
                    "gmail_message_id",
                    message_id
                )
                .limit(1)
                .execute()
            )

            existing_messages = (
                existing_response.data
                or []
            )

            if existing_messages:
                continue

            # --------------------------------------
            # Save incoming reply
            # --------------------------------------

            (
                supabase
                .table("email_messages")
                .insert({
                    "lead_id": lead["id"],
                    "campaign_id": (
                        campaign_lead["campaign_id"]
                    ),
                    "gmail_message_id": message_id,
                    "gmail_thread_id": (
                        message_thread_id
                    ),
                    "direction": "received",
                    "subject": subject,
                    "body": clean_body
                })
                .execute()
            )

            # --------------------------------------
            # Add API response
            # --------------------------------------

            replies.append({
                "message_id": message_id,
                "thread_id": message_thread_id,
                "lead_id": lead["id"],
                "campaign_id": (
                    campaign_lead["campaign_id"]
                ),
                "name": lead["name"],
                "email": lead["email"],
                "company": lead["company"],
                "subject": subject,
                "reply": clean_body
            })

        # ------------------------------------------
        # Return
        # ------------------------------------------

        return {
            "total_replies": len(replies),
            "replies": replies
        }

    except HTTPException:
        raise

    except Exception as e:

        raise HTTPException(
            status_code=500,
            detail=str(e)
        )