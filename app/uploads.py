"""Upload validation: extension, browser content-type, and magic-byte signature
checks (plus size cap) before any bytes are forwarded to Gemini."""

from dataclasses import dataclass
from pathlib import Path

from fastapi import UploadFile

from .errors import AppError

MAX_UPLOAD_BYTES = 10 * 1024 * 1024
READ_CHUNK_BYTES = 1024 * 1024

ALLOWED_UPLOADS = {
    ".jpeg": "image/jpeg",
    ".jpg": "image/jpeg",
    ".pdf": "application/pdf",
    ".png": "image/png",
    ".webp": "image/webp",
}


@dataclass(frozen=True)
class ValidatedUpload:
    data: bytes
    mime_type: str


def _extension(filename: str | None) -> str:
    return Path(filename or "").suffix.lower()


# Browsers vary in how they label the same file: case ("IMAGE/PNG"), a trailing
# parameter ("image/jpeg; charset=binary"), and the non-standard "image/jpg"
# alias all describe a supported type. Normalise before the equality check so a
# valid upload is not rejected on a cosmetic header difference. The magic-byte
# check below is the real signature gate; this header check only screens intent.
_CONTENT_TYPE_ALIASES = {"image/jpg": "image/jpeg", "image/pjpeg": "image/jpeg"}


def _normalize_content_type(content_type: str | None) -> str:
    base = (content_type or "").split(";", 1)[0].strip().lower()
    return _CONTENT_TYPE_ALIASES.get(base, base)


def _detect_mime_type(data: bytes) -> str | None:
    if data.startswith(b"%PDF"):
        return "application/pdf"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


async def read_validated_upload(upload: UploadFile, field_name: str) -> ValidatedUpload:
    extension = _extension(upload.filename)
    expected_mime_type = ALLOWED_UPLOADS.get(extension)

    if not expected_mime_type:
        raise AppError(
            status_code=400,
            code="UNSUPPORTED_FILE_EXTENSION",
            message=f"{field_name} must be a PDF, PNG, JPEG, or WebP file.",
            details={
                "field": field_name,
                "filename": upload.filename,
                "allowed_extensions": sorted(ALLOWED_UPLOADS),
            },
        )

    if _normalize_content_type(upload.content_type) != expected_mime_type:
        raise AppError(
            status_code=400,
            code="UNSUPPORTED_FILE_TYPE",
            message=f"{field_name} has an unsupported file type.",
            details={
                "field": field_name,
                "filename": upload.filename,
                "content_type": upload.content_type,
                "expected_content_type": expected_mime_type,
            },
        )

    chunks = []
    total_size = 0

    while True:
        chunk = await upload.read(READ_CHUNK_BYTES)
        if not chunk:
            break
        chunks.append(chunk)
        total_size += len(chunk)

        if total_size > MAX_UPLOAD_BYTES:
            raise AppError(
                status_code=413,
                code="UPLOAD_TOO_LARGE",
                message=f"{field_name} is too large. Upload files must be 10 MB or smaller.",
                details={
                    "field": field_name,
                    "filename": upload.filename,
                    "size_bytes_read": total_size,
                    "max_size_bytes": MAX_UPLOAD_BYTES,
                },
            )

    data = b"".join(chunks)

    if not data:
        raise AppError(
            status_code=400,
            code="EMPTY_UPLOAD",
            message=f"{field_name} is empty.",
            details={"field": field_name, "filename": upload.filename},
        )

    detected_mime_type = _detect_mime_type(data)
    if detected_mime_type != expected_mime_type:
        raise AppError(
            status_code=400,
            code="INVALID_FILE_SIGNATURE",
            message=f"{field_name} contents do not match the uploaded file type.",
            details={
                "field": field_name,
                "filename": upload.filename,
                "content_type": upload.content_type,
                "expected_content_type": expected_mime_type,
                "detected_content_type": detected_mime_type,
            },
        )

    return ValidatedUpload(data=data, mime_type=detected_mime_type)
