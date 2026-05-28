import os
import logging
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

class Settings:
    FMP_API_KEY = os.getenv("FMP_API_KEY")
    AZURE_CONN_STR = os.getenv("AZURE_STORAGE_CONNECTION_STRING")
    SENDER_EMAIL = os.getenv("SENDER_EMAIL")
    SENDER_PASSWORD = os.getenv("SENDER_PASSWORD")
    STAN_PERSONAL_EMAIL = os.getenv("STAN_PERSONAL_EMAIL")

    @classmethod
    def validate(cls):
        missing = []
        if not cls.FMP_API_KEY: missing.append("FMP_API_KEY")
        if not cls.AZURE_CONN_STR: missing.append("AZURE_STORAGE_CONNECTION_STRING")
        if not cls.SENDER_EMAIL: missing.append("SENDER_EMAIL")
        
        if missing:
            logger.error(f"FATAL: Missing critical environment variables: {', '.join(missing)}.")
            return False
        return True

settings = Settings()