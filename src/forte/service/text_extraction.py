"""Extract plain text from documents of various file types.

A pure function of a file path to a string — no vault or DB knowledge — so
``DocumentService`` can extract text without coupling ingest orchestration to
any particular file format. Lives beside the service rather than behind an
interface because it depends only on local libraries, not on an external
system that a client would have to abstract.
"""

from __future__ import annotations

from pathlib import Path

import pypdf
from docx import Document as DocxDocument

from forte.model.document import UnsupportedFileTypeError


def extract_text(path: Path) -> str:
    """
    Extract plain text from ``path``, dispatching on its file extension.

    Supported extensions:
      - ``.md`` / ``.txt``: read as plain UTF-8 text, verbatim.
      - ``.docx``: extracted via ``python-docx``, joining each paragraph's
        text with a newline (``"\\n"``). Empty paragraphs become empty lines;
        no extra normalization is applied.
      - ``.pdf``: extracted via ``pypdf``, joining each page's extracted text
        with a blank line separator (``"\\n\\n"``) so page boundaries remain
        visible in the plain-text output.

    Args:
        path (Path): Path to the file to extract text from.

    Returns:
        (str) The extracted plain text.

    Raises:
        UnsupportedFileTypeError: if the file's extension isn't one of the
            supported extensions listed above.
    """
    suffix = path.suffix.lower()

    if suffix in (".md", ".txt", ".py"):
        return path.read_text(encoding="utf-8")

    if suffix == ".docx":
        doc = DocxDocument(str(path))
        return "\n".join(p.text for p in doc.paragraphs)

    if suffix == ".pdf":
        reader = pypdf.PdfReader(str(path))
        pages = [page.extract_text() or "" for page in reader.pages]
        return "\n\n".join(pages)

    raise UnsupportedFileTypeError(
        f"Unsupported file type {suffix!r}: cannot extract text from {path.name}."
    )
