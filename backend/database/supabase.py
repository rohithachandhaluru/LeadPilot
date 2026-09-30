import os

from dotenv import load_dotenv
from supabase import create_client, Client

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")


if not SUPABASE_URL:
    raise Exception("SUPABASE_URL is missing in .env")


if not SUPABASE_KEY:
    raise Exception("SUPABASE_KEY is missing in .env")


supabase: Client = create_client(
    SUPABASE_URL,
    SUPABASE_KEY
)