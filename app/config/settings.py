"""Application settings and environment variables."""
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Set default user agent for web requests
os.environ['USER_AGENT'] = os.getenv(
    'USER_AGENT', 
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.3'
)

# API Keys
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
GOOGLE_CSE_ID = os.getenv("GOOGLE_CSE_ID")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
ODDS_API_KEY = os.getenv("ODDS_API_KEY", "492431dae9c36c84909c440417fa2e87") # 3b3a5d8e226355d83b47854375dc36b5
REDDIT_CLIENT_ID = os.getenv("REDDIT_CLIENT_ID") 
REDDIT_CLIENT_SECRET = os.getenv("REDDIT_CLIENT_SECRET")

# AWS Configuration
AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID")
AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY")
AWS_REGION = os.getenv("AWS_REGION", "us-east-1")
AWS_BUCKET_NAME = os.getenv("AWS_BUCKET_NAME", "gamimarket")

# OpenAI Settings
DEFAULT_MODEL = os.getenv("DEFAULT_MODEL", "gpt-4o-mini")

# MongoDB Settings
MONGODB_URI = os.getenv("MONGODB_URI", "")
DATABASE_NAME = os.getenv("DATABASE_NAME", "cyrus")
EVENT_COLLECTION = os.getenv("EVENT_COLLECTION", "cyrus_collection")

# Search Settings
RESULTS_PER_REQUEST = int(os.getenv("RESULTS_PER_REQUEST", "10"))
MAX_RESULTS_TO_FETCH = int(os.getenv("MAX_RESULTS_TO_FETCH", "100"))
DESIRED_RECENT_RESULTS = int(os.getenv("DESIRED_RECENT_RESULTS", "50"))
DELAY_BETWEEN_REQUESTS = int(os.getenv("DELAY_BETWEEN_REQUESTS", "2"))

# Default retry settings
DEFAULT_RETRY_COUNT = int(os.getenv("DEFAULT_RETRY_COUNT", "3"))
DEFAULT_RETRY_DELAY = int(os.getenv("DEFAULT_RETRY_DELAY", "2"))

# User agent for web requests
USER_AGENT = os.environ['USER_AGENT']