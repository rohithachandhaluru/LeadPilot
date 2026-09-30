from fastapi import FastAPI

from app.routers import gmail, leads, knowledge
from database.supabase import supabase


app = FastAPI(
    title="LeadPilot",
    description="AI-Based Lead Qualification and Email Automation",
    version="1.0.0"
)


# --------------------------------------------------
# Routers
# --------------------------------------------------

app.include_router(gmail.router)
app.include_router(leads.router)
app.include_router(knowledge.router)


# --------------------------------------------------
# Root
# --------------------------------------------------

@app.get("/")
def root():

    return {
        "message": "LeadPilot API is running"
    }


# --------------------------------------------------
# Supabase Connection Test
# --------------------------------------------------

@app.get("/test/supabase")
def test_supabase():

    try:

        response = (
            supabase
            .table("connection_test")
            .select("*")
            .limit(1)
            .execute()
        )

        return {
            "message": "Supabase connection successful",
            "data": response.data
        }

    except Exception as e:

        return {
            "message": "Supabase connection failed",
            "error": str(e)
        }