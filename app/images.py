"""Image intake and normalization.

Every uploaded file passes through normalize_to_jpeg() before anything else
touches it. This single step does several jobs at once:

  1. Validation      - confirm the bytes really are a readable image.
  2. Format unify    - convert anything (incl. HEIC) to one format: JPEG.
  3. Security        - re-encoding discards the original bytes, which defuses
                       malformed or "polyglot" files (a file that is secretly
                       something else). EXIF metadata (GPS, device, timestamp)
                       is dropped because the freshly saved JPEG carries none.
  4. Performance     - downscale huge phone photos so the request stays small
                       and fast, protecting the 5 second latency target.

Think of it as a clean-room airlock: whatever comes in, only a sanitized,
predictable JPEG comes out the other side.
"""
import io

from PIL import Image, ImageOps
import pillow_heif

# Teach Pillow how to open HEIC/HEIF (the format iPhones save by default).
pillow_heif.register_heif_opener()

# Friendly extensions we accept. Real validation is "can Pillow open it?",
# but this gives a fast, clear rejection message for obvious wrong types.
ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".heic", ".heif"}

# Longest side, in pixels, after downscaling. Labels remain very legible at
# this size and the payload to the model stays small.
MAX_DIMENSION = 2000

# JPEG quality for the normalized output. 90 is visually lossless for text.
JPEG_QUALITY = 90


class ImageValidationError(Exception):
    """Raised when an upload is not a usable image. Carries a user-safe message."""


def normalize_to_jpeg(raw: bytes, max_mb: int) -> bytes:
    """Validate and normalize raw upload bytes into a clean JPEG.

    Raises ImageValidationError (with a message safe to show the user) if the
    file is too large or is not a readable image.
    """
    # Size gate first: cheapest check, and stops resource exhaustion via a
    # giant upload before we spend any memory decoding it.
    if len(raw) > max_mb * 1024 * 1024:
        raise ImageValidationError(
            f"Image is larger than the {max_mb} MB limit. Please upload a smaller photo."
        )

    try:
        img = Image.open(io.BytesIO(raw))
        img.load()  # force a full decode so a corrupt file fails here, not later
    except Exception:
        raise ImageValidationError(
            "Could not read this file as an image. Please upload a JPG, PNG, WebP, or HEIC."
        )

    # Honor the photo's EXIF orientation (so sideways phone photos come out
    # upright), THEN flatten to RGB. The re-save below carries no EXIF, so the
    # orientation must be baked into the pixels now or it is lost.
    img = ImageOps.exif_transpose(img)
    img = img.convert("RGB")

    # Downscale in place if either side exceeds the cap (keeps aspect ratio).
    img.thumbnail((MAX_DIMENSION, MAX_DIMENSION))

    out = io.BytesIO()
    img.save(out, format="JPEG", quality=JPEG_QUALITY)
    return out.getvalue()


def has_allowed_extension(filename: str) -> bool:
    """Quick filename check for an early, friendly rejection."""
    name = (filename or "").lower()
    return any(name.endswith(ext) for ext in ALLOWED_EXTENSIONS)
