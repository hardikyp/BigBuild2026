from __future__ import annotations

from io import BytesIO
from pathlib import Path

from PIL import Image, ImageOps, UnidentifiedImageError


PHOTO_MIME_TYPES = {"JPEG": "image/jpeg", "PNG": "image/png", "WEBP": "image/webp", "GIF": "image/gif"}
PHOTO_ACCEPT = ",".join(PHOTO_MIME_TYPES.values())
REPORT_MAX_PIXELS = 1600


def photo_mime_type(data: bytes) -> str | None:
    """Return the MIME type of a supported photo, or None if the bytes are not one.

    The browser-supplied content type is not trusted; the file is decoded instead.
    """
    try:
        with Image.open(BytesIO(data)) as image:
            image.verify()
            return PHOTO_MIME_TYPES.get(image.format)
    except (UnidentifiedImageError, Image.DecompressionBombError, OSError, SyntaxError, ValueError):
        return None


def report_image(path: Path) -> tuple[BytesIO, int, int]:
    """Return an upright, downscaled JPEG copy of a stored photo for the PDF report.

    Phones store orientation in EXIF rather than rotating pixels, so the
    rotation is applied here. The stored original is never modified.
    """
    with Image.open(path) as source:
        image = ImageOps.exif_transpose(source)
        image.thumbnail((REPORT_MAX_PIXELS, REPORT_MAX_PIXELS))
        if image.mode not in ("RGB", "L"):
            image = image.convert("RGB")
        buffer = BytesIO()
        image.save(buffer, format="JPEG", quality=82)
    buffer.seek(0)
    return buffer, image.width, image.height
