import asyncio
import secrets
from pathlib import Path

from fastapi import UploadFile


MAX_IMAGE_SIZE = 2 * 1024 * 1024
CHUNK_SIZE = 64 * 1024
IMAGE_SIGNATURES = {"image/jpeg": (b"\xff\xd8\xff", ".jpg"), "image/png": (b"\x89PNG\r\n\x1a\n", ".png"), "image/gif": (b"GIF8", ".gif"), "image/webp": (b"RIFF", ".webp")}


class UnsupportedMediaTypeError(Exception):
    pass


class InvalidImageError(Exception):
    pass


class FileTooLargeError(Exception):
    pass


_media_write_lock = asyncio.Lock()


def _validate_signature(content_type: str, content: bytes) -> str:
    signature = IMAGE_SIGNATURES.get(content_type)
    if signature is None:
        raise UnsupportedMediaTypeError
    prefix, extension = signature
    if not content.startswith(prefix):
        raise InvalidImageError
    if content_type == "image/webp" and (len(content) < 12 or content[8:12] != b"WEBP"):
        raise InvalidImageError
    return extension


async def save_image(file: UploadFile, media_root: Path) -> tuple[int, str]:
    content_type = file.content_type or ""
    content = bytearray()
    while chunk := await file.read(CHUNK_SIZE):
        content.extend(chunk)
        if len(content) > MAX_IMAGE_SIZE:
            raise FileTooLargeError
    if not content:
        raise InvalidImageError
    extension = _validate_signature(content_type, bytes(content))

    media_root.mkdir(parents=True, exist_ok=True)
    async with _media_write_lock:
        media_id = secrets.randbelow(2**63 - 1) + 1
        destination = media_root / f"{media_id}{extension}"
        while destination.exists():
            media_id = secrets.randbelow(2**63 - 1) + 1
            destination = media_root / f"{media_id}{extension}"
        await asyncio.to_thread(destination.write_bytes, bytes(content))
    return media_id, destination.name
