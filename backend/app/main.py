from fastapi import FastAPI

from app.routers import gmail


app = FastAPI(
    title="LeadPilot",
    description="AI-Based Lead Qualification and Email Automation",
    version="1.0.0"
)


app.include_router(gmail.router)


@app.get("/")
def root():

    return {
        "message": "LeadPilot API is running"
    }