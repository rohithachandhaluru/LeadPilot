import pandas as pd
import base64

from io import BytesIO
from email.mime.text import MIMEText

from fastapi import APIRouter, UploadFile, File, HTTPException
from pydantic import BaseModel

from app.routers.gmail import get_gmail_service


router = APIRouter(
    prefix="/leads",
    tags=["Leads"]
)


# --------------------------------------------------
# Required Excel / CSV columns
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


# --------------------------------------------------
# Send Email Request
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

    try:

        # ------------------------------------------
        # Check file
        # ------------------------------------------

        if not file.filename:
            raise HTTPException(
                status_code=400,
                detail="No file selected."
            )

        filename = file.filename.lower()

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
        # Read Excel / CSV using Pandas
        # ------------------------------------------

        if filename.endswith(".csv"):

            df = pd.read_csv(
                BytesIO(file_content)
            )

        else:

            df = pd.read_excel(
                BytesIO(file_content)
            )

        # ------------------------------------------
        # Check empty data
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
        # Keep required columns
        # ------------------------------------------

        df = df[
            REQUIRED_COLUMNS
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

        for column in REQUIRED_COLUMNS:

            df[column] = (
                df[column]
                .fillna("")
                .astype(str)
                .str.strip()
            )

        # ------------------------------------------
        # Remove empty email rows
        # ------------------------------------------

        df = df[
            df["email"] != ""
        ]

        # ------------------------------------------
        # Remove duplicate emails
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

            name = row["name"]
            email = row["email"]
            company = row["company"]

            # Basic email validation
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

            # Name validation
            if not name:

                invalid_leads.append({
                    "name": name,
                    "email": email,
                    "company": company,
                    "reason": "Name is empty"
                })

                continue

            # Company validation
            if not company:

                invalid_leads.append({
                    "name": name,
                    "email": email,
                    "company": company,
                    "reason": "Company is empty"
                })

                continue

            valid_leads.append({
                "name": name,
                "email": email,
                "company": company
            })

        # ------------------------------------------
        # Store valid leads temporarily
        # ------------------------------------------

        uploaded_leads = valid_leads

        # ------------------------------------------
        # Return upload result
        # ------------------------------------------

        return {
            "message": "Leads uploaded successfully",
            "filename": file.filename,
            "total_rows": len(valid_leads) + len(invalid_leads),
            "valid_leads": len(valid_leads),
            "invalid_leads": len(invalid_leads),
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
# View Uploaded Leads
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

    if not uploaded_leads:

        raise HTTPException(
            status_code=400,
            detail=(
                "No leads uploaded. "
                "Please upload an Excel or CSV file first."
            )
        )

    try:

        # ------------------------------------------
        # Get Gmail service
        # ------------------------------------------

        gmail_service = get_gmail_service()

        results = []

        successful = 0
        failed = 0

        # ------------------------------------------
        # Send email to each lead
        # ------------------------------------------

        for lead in uploaded_leads:

            try:

                # ----------------------------------
                # Personalize email
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
                # Encode email
                # ----------------------------------

                encoded_message = (
                    base64.urlsafe_b64encode(
                        message.as_bytes()
                    )
                    .decode()
                )

                email_body = {
                    "raw": encoded_message
                }

                # ----------------------------------
                # Send using Gmail API
                # ----------------------------------

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
                    "name": lead["name"],
                    "email": lead["email"],
                    "company": lead["company"],
                    "status": "sent",
                    "gmail_message_id": result["id"]
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
        # Return sending result
        # ------------------------------------------

        return {
            "message": "Lead email sending completed",
            "total": len(uploaded_leads),
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