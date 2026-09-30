from fastapi import APIRouter, HTTPException, UploadFile, File
from pydantic import BaseModel

from database.supabase import supabase
from services.knowledge_service import split_text


router = APIRouter(
    prefix="/knowledge",
    tags=["Knowledge Base"]
)


# --------------------------------------------------
# Request Model
# --------------------------------------------------

class KnowledgeCreate(BaseModel):
    filename: str
    content: str


# --------------------------------------------------
# Add Knowledge Manually
# --------------------------------------------------

@router.post("/")
def add_knowledge(data: KnowledgeCreate):

    try:

        response = (
            supabase
            .table("knowledge_base")
            .insert({
                "filename": data.filename,
                "content": data.content
            })
            .execute()
        )

        return {
            "message": "Knowledge added successfully",
            "data": response.data
        }

    except Exception as e:

        raise HTTPException(
            status_code=500,
            detail=str(e)
        )


# --------------------------------------------------
# Get All Knowledge
# --------------------------------------------------

@router.get("/")
def get_knowledge():

    try:

        response = (
            supabase
            .table("knowledge_base")
            .select("*")
            .order("created_at", desc=True)
            .execute()
        )

        return {
            "message": "Knowledge retrieved successfully",
            "data": response.data
        }

    except Exception as e:

        raise HTTPException(
            status_code=500,
            detail=str(e)
        )


# --------------------------------------------------
# Upload TXT Knowledge File
# --------------------------------------------------

@router.post("/upload")
async def upload_knowledge(
    file: UploadFile = File(...)
):

    try:

        # ------------------------------------------
        # Check file type
        # ------------------------------------------

        if not file.filename.lower().endswith(".txt"):

            raise HTTPException(
                status_code=400,
                detail="Only .txt files are supported for now"
            )


        # ------------------------------------------
        # Read file
        # ------------------------------------------

        file_content = await file.read()

        try:

            content = file_content.decode("utf-8")

        except UnicodeDecodeError:

            raise HTTPException(
                status_code=400,
                detail="Could not read the file as UTF-8 text"
            )


        # ------------------------------------------
        # Check empty file
        # ------------------------------------------

        if not content.strip():

            raise HTTPException(
                status_code=400,
                detail="Uploaded file is empty"
            )


        # ------------------------------------------
        # Save original document
        # ------------------------------------------

        document_response = (
            supabase
            .table("knowledge_base")
            .insert({
                "filename": file.filename,
                "content": content
            })
            .execute()
        )


        if not document_response.data:

            raise HTTPException(
                status_code=500,
                detail="Failed to save knowledge document"
            )


        # Get generated document ID
        knowledge_id = document_response.data[0]["id"]


        # ------------------------------------------
        # Split document into chunks
        # ------------------------------------------

        chunks = split_text(
            content,
            chunk_size=500,
            chunk_overlap=50
        )


        if not chunks:

            raise HTTPException(
                status_code=400,
                detail="Could not create chunks from the document"
            )


        # ------------------------------------------
        # Prepare chunk records
        # ------------------------------------------

        chunk_records = []

        for index, chunk in enumerate(chunks):

            chunk_records.append({
                "knowledge_id": knowledge_id,
                "chunk_index": index,
                "content": chunk
            })


        # ------------------------------------------
        # Save chunks to Supabase
        # ------------------------------------------

        chunks_response = (
            supabase
            .table("knowledge_chunks")
            .insert(chunk_records)
            .execute()
        )


        return {
            "message": "Knowledge file uploaded and chunked successfully",
            "knowledge_id": knowledge_id,
            "filename": file.filename,
            "total_chunks": len(chunks),
            "chunks": chunks_response.data
        }


    except HTTPException:

        raise


    except Exception as e:

        raise HTTPException(
            status_code=500,
            detail=str(e)
        )