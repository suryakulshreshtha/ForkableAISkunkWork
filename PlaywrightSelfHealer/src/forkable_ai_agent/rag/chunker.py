"""Heading-aware chunking.

Splitting on Markdown headings first keeps a chunk semantically whole, which
matters more than raw chunk size when the corpus is a set of engineering notes
and runbooks. Oversized sections are then windowed with overlap.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")


@dataclass
class Chunk:
    text: str
    heading: str
    order: int


def split_sections(text: str) -> list[tuple[str, str]]:
    sections: list[tuple[str, str]] = []
    heading = ""
    buffer: list[str] = []
    for line in text.splitlines():
        match = _HEADING_RE.match(line)
        if match:
            if buffer and any(b.strip() for b in buffer):
                sections.append((heading, "\n".join(buffer).strip()))
            heading = match.group(2).strip()
            buffer = []
        else:
            buffer.append(line)
    if buffer and any(b.strip() for b in buffer):
        sections.append((heading, "\n".join(buffer).strip()))
    return sections


def window(text: str, size: int, overlap: int) -> list[str]:
    if len(text) <= size:
        return [text]
    step = max(1, size - overlap)
    out: list[str] = []
    start = 0
    while start < len(text):
        piece = text[start:start + size]
        # prefer to break on a paragraph or sentence boundary
        if start + size < len(text):
            for sep in ("\n\n", "\n", ". "):
                cut = piece.rfind(sep)
                if cut > size * 0.5:
                    piece = piece[:cut + len(sep)]
                    break
        out.append(piece.strip())
        start += max(step, len(piece) - overlap) if len(piece) > overlap else step
    return [p for p in out if p]


def chunk_document(text: str, chunk_chars: int = 900, overlap: int = 150) -> list[Chunk]:
    chunks: list[Chunk] = []
    order = 0
    for heading, body in split_sections(text):
        for piece in window(body, chunk_chars, overlap):
            prefixed = f"{heading}\n{piece}" if heading else piece
            chunks.append(Chunk(text=prefixed.strip(), heading=heading, order=order))
            order += 1
    return chunks
