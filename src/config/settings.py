import os
import tempfile
import logging
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

# Centralized filesystem paths.
# Production (Azure Functions Linux) keeps the original /tmp layout, while
# local dev (e.g. Windows) falls back to the OS temp dir so we never try to
# write to a non-existent C:\tmp. Both can be overridden via env vars.
_DEFAULT_BASE = "/tmp" if os.name == "posix" else tempfile.gettempdir()
DATA_DIR = os.getenv("BOARDROOM_DATA_DIR", os.path.join(_DEFAULT_BASE, "data"))
OUTPUT_DIR = os.getenv("BOARDROOM_OUTPUT_DIR", os.path.join(_DEFAULT_BASE, "output"))


class Settings:
    FMP_API_KEY = os.getenv("FMP_API_KEY")
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
    AZURE_CONN_STR = os.getenv("AZURE_STORAGE_CONNECTION_STRING")
    SENDER_EMAIL = os.getenv("SENDER_EMAIL")
    SENDER_PASSWORD = os.getenv("SENDER_PASSWORD")
    STAN_PERSONAL_EMAIL = os.getenv("STAN_PERSONAL_EMAIL")

    DATA_DIR = DATA_DIR
    OUTPUT_DIR = OUTPUT_DIR

    @classmethod
    def validate(cls):
        missing = []
        if not cls.GEMINI_API_KEY: missing.append("GEMINI_API_KEY")
        if not cls.FMP_API_KEY: missing.append("FMP_API_KEY")
        if not cls.AZURE_CONN_STR: missing.append("AZURE_STORAGE_CONNECTION_STRING")
        if not cls.SENDER_EMAIL: missing.append("SENDER_EMAIL")
        
        if missing:
            logger.error(f"FATAL: Missing critical environment variables: {', '.join(missing)}.")
            return False
        return True

settings = Settings()
