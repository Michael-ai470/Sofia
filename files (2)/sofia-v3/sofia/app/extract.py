"""
Sofia — file text extraction.

Uploads become plain text before anything reaches the AI. Binary never goes
to the model: it costs a fortune in tokens, the model reads it badly, and it
widens the attack surface for no benefit.
"""

from __future__ import annotations

import io
import logging
import os
import re

from config import Config

log = logging.getLogger("sofia.extract")

MIN_USEFUL_CHARS = 80


class ExtractError(Exception):
    pass


def _clean(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", text)   # control chars
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def from_pdf(data: bytes) -> str:
    try:
        from pypdf import PdfReader
    except ImportError as exc:                                  # pragma: no cover
        raise ExtractError("PDF support is not installed on the server.") from exc

    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted:
            try:
                reader.decrypt("")
            except Exception as exc:
                raise ExtractError(
                    "That PDF is password protected. Remove the password and try again."
                ) from exc
        pages = [(page.extract_text() or "") for page in reader.pages[:40]]
    except ExtractError:
        raise
    except Exception as exc:
        raise ExtractError("That PDF could not be read. It may be damaged.") from exc

    return _clean("\n\n".join(pages))


def from_docx(data: bytes) -> str:
    try:
        import docx
    except ImportError as exc:                                  # pragma: no cover
        raise ExtractError("Word support is not installed on the server.") from exc

    try:
        document = docx.Document(io.BytesIO(data))
    except Exception as exc:
        raise ExtractError(
            "That Word file could not be read. If it is an old .doc, save it as .docx first."
        ) from exc

    parts = [p.text for p in document.paragraphs]
    for table in document.tables:
        for row in table.rows:
            cells = [c.text.strip() for c in row.cells if c.text.strip()]
            if cells:
                parts.append(" | ".join(cells))
    return _clean("\n".join(parts))


def from_upload(file_storage) -> str:
    """
    Extract text from a Werkzeug FileStorage.

    Type is decided by extension AND by magic bytes, because an extension
    alone is a claim made by whoever uploaded the file.
    """
    filename = (file_storage.filename or "").strip()
    if not filename:
        raise ExtractError("No file was received.")

    ext = os.path.splitext(filename)[1].lower()
    if ext not in Config.ALLOWED_UPLOAD_EXT:
        allowed = ", ".join(sorted(Config.ALLOWED_UPLOAD_EXT))
        raise ExtractError(f"That file type is not supported. Accepted: {allowed}")

    data = file_storage.read()
    if not data:
        raise ExtractError("That file is empty.")
    if len(data) > Config.MAX_CONTENT_LENGTH:
        raise ExtractError(f"That file is larger than the {Config.MAX_UPLOAD_MB} MB limit.")

    if data[:5] == b"%PDF-":
        text = from_pdf(data)
    elif data[:2] == b"PK":                 # docx is a zip container
        text = from_docx(data)
    elif ext in (".txt", ".md", ".rtf"):
        try:
            text = _clean(data.decode("utf-8", errors="replace"))
        except Exception as exc:
            raise ExtractError("That text file could not be read.") from exc
    elif ext == ".doc":
        raise ExtractError(
            "Old .doc files are not supported. Open it in Word and save as .docx."
        )
    else:
        raise ExtractError("That file could not be identified. Try a PDF or .docx.")

    if len(text) < MIN_USEFUL_CHARS:
        raise ExtractError(
            "Almost no text came out of that file. If it is a scan, the text is an "
            "image — paste the text instead, or use a searchable PDF."
        )

    return text
