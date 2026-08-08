"""Sample Python module with various configuration patterns."""
import os

# Environment variable access
SENTRY_DSN = os.environ.get(
    "SENTRY_DSN",
    "https://xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx@sentry.io/12345",
)
DATABASE_URL = os.getenv("DATABASE_URL")
API_KEY = os.environ["OPENAI_API_KEY"]

# Hardcoded secrets (bad practice - for audit demo)
PAYMENT_API_KEY = "payment_live_XXXXXXXXXXXXXXXXXXXXXXXXXXXX"
cloud_access_key = "CLOUDFODNN7XXXXXXXX"
db_password = "SuperSecretPassXXXX!"

config = {
    "api_key": "pk_test_XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX",
    "redis_url": "redis://:secretXXXX@10.0.0.5:6379/0",
    "debug": True,
}

class Settings:
    def __init__(self):
        self.client_secret = "cs_live_XXXXXXXXXXXXXXXXXXXX"
        self.jwt_secret = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.XXXXXXXX.XXXXXXXX"