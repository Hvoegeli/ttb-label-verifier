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
    # Vision model id. Default is the cheapest vision-capable model (Haiku 4.5,
    # $1/$5 per 1M tokens). Override with CLAUDE_MODEL=claude-sonnet-4-6 if Haiku
    # misreads small warning text too often. Confirmed via the claude-api reference.
    claude_model: str = os.getenv("CLAUDE_MODEL") or "claude-haiku-4-5"
    # Reject uploads larger than this before doing any work.
    max_upload_mb: int = int(os.getenv("MAX_UPLOAD_MB", "10"))
    # Most labels one batch request processes synchronously. The batch runs the
    # vision call per label in series, so a large batch would outlast an HTTP
    # request; production would move 200-300 label runs to a background queue.
    # This cap keeps the live demo responsive while still proving the cost story
    # (the result page projects the measured per-label figures out to any volume).
    max_batch: int = int(os.getenv("MAX_BATCH", "25"))
    app_env: str = os.getenv("APP_ENV", "dev")


settings = Settings()
