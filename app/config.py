"""Application configuration, read from environment variables.

Secrets never live in code. Locally they come from a .env file (loaded here);
in production they come from the host's secret manager. Either way the code
only ever reads os.environ, so there is one consistent path.
"""
import os

from dotenv import load_dotenv

# Load .env if present. In production the vars are already set in the
# environment, so this call simply finds nothing to load and does no harm.
load_dotenv()


class Settings:
    # Required for extraction (Task Group 3). Empty until a key is provided.
    anthropic_api_key: str = os.getenv("ANTHROPIC_API_KEY", "")
    # The exact vision model id is confirmed via the claude-api reference before
    # the extractor is written, so it stays configurable here.
    claude_model: str = os.getenv("CLAUDE_MODEL", "")
    # Reject uploads larger than this before doing any work.
    max_upload_mb: int = int(os.getenv("MAX_UPLOAD_MB", "10"))
    app_env: str = os.getenv("APP_ENV", "dev")


settings = Settings()
