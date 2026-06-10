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
    # Robustness: when the cheap default model returns a low-confidence read (or a
    # warning that does not match the statute, a likely misread), re-read once with
    # this stronger model. The 3x cost is paid only on the hard labels that need it.
    escalation_model: str = os.getenv("ESCALATION_MODEL") or "claude-sonnet-4-6"
    enable_escalation: bool = os.getenv("ENABLE_ESCALATION", "true").lower() not in ("0", "false", "no")
    # Reject uploads larger than this before doing any work.
    max_upload_mb: int = int(os.getenv("MAX_UPLOAD_MB", "10"))
    # Most labels one batch request processes synchronously. The batch runs the
    # per-label vision calls concurrently (see BATCH_CONCURRENCY), so wall-clock
    # no longer grows linearly; production would still move 200-300 label runs to
    # a background queue. This cap keeps the live demo responsive while proving the
    # cost story (the result page projects the measured per-label figures out to
    # any volume).
    max_batch: int = int(os.getenv("MAX_BATCH", "50"))
    # How many labels in a batch are read at once. Each label is one network call
    # that mostly waits on the model, so overlapping them cuts batch wall-clock
    # roughly N-fold. 8 is well within Anthropic's rate limits for Haiku and light
    # on memory. Raise for speed, lower if a small API tier returns rate limits.
    batch_concurrency: int = int(os.getenv("BATCH_CONCURRENCY", "8"))
    app_env: str = os.getenv("APP_ENV", "dev")


settings = Settings()
