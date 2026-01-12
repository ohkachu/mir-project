import os
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_KEY")
MAKE_IT_REAL_BASE_URL = "https://makeitreal-beta.eufymake.com"
REQUEST_TIMEOUT = 30
SYNC_DELAY = 1
LOG_LEVEL = "INFO"
LOG_FILE = "scraper.log"
