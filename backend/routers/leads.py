from fastapi import APIRouter, UploadFile, File

router = APIRouter(
    prefix="/leads",
    tags=["Leads"]
)


@router.post("/upload")
async def upload_leads(file: UploadFile = File(...)):

    return {
        "filename": file.filename,
        "message": "File received successfully"
    }