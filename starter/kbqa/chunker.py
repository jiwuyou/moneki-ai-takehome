"""把文档切成检索用的小块。"""

from __future__ import annotations

from dataclasses import dataclass, field

from .loader import Document
from .sanitize import sanitize

#: 切块参数变了，索引缓存必须失效，所以写进缓存键里。
CHUNKER_VERSION = "chunker-4"

CHUNK_SIZE = 300


@dataclass
class Chunk:
    doc_id: str
    chunk_id: str
    text: str
    source_text: str
    heading: str = ""
    kind: str = "text"
    table_header: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "doc_id": self.doc_id,
            "chunk_id": self.chunk_id,
            "text": self.text,
            "source_text": self.source_text,
            "heading": self.heading,
            "kind": self.kind,
            "table_header": self.table_header,
        }


def chunk_document(document: Document) -> list[Chunk]:
    """Split text while keeping Markdown tables as citeable units."""
    # Knowledge-base text is untrusted data.  Instruction-like sentences are
    # excluded from retrieval context; the original full text remains in the
    # index for citation verification.
    text, _dropped = sanitize(document.text)
    chunks: list[Chunk] = []
    segments: list[tuple[str, str, list[str]]] = []
    normal: list[str] = []

    def flush_normal() -> None:
        nonlocal normal
        body = "\n".join(normal).strip()
        if body:
            for start in range(0, len(body), CHUNK_SIZE):
                piece = body[start : start + CHUNK_SIZE]
                segments.append((piece, "text", []))
        normal = []

    lines = text.splitlines()
    index = 0
    while index < len(lines):
        line = lines[index]
        if (
            line.strip().startswith("|")
            and index + 1 < len(lines)
            and lines[index + 1].strip().startswith("|")
            and set(lines[index + 1].strip()) <= set("|:- ")
        ):
            flush_normal()
            header = [cell.strip() for cell in line.strip().strip("|").split("|")]
            table_lines = [line, lines[index + 1]]
            index += 2
            while index < len(lines) and lines[index].strip().startswith("|"):
                table_lines.append(lines[index])
                index += 1
            segments.append(("\n".join(table_lines), "table", header))
            continue
        normal.append(line)
        index += 1
    flush_normal()

    for number, (piece, kind, header) in enumerate(segments, start=1):
        chunks.append(
            Chunk(
                doc_id=document.doc_id,
                chunk_id="%s#%d" % (document.doc_id, number),
                text=piece,
                source_text=piece,
                heading=document.title,
                kind=kind,
                table_header=header,
            )
        )
    if not chunks:
        piece = text.strip() or document.title
        chunks.append(
            Chunk(
                doc_id=document.doc_id,
                chunk_id="%s#1" % document.doc_id,
                text=piece,
                source_text=piece,
                heading=document.title,
            )
        )
    return chunks


def chunk_documents(documents: list[Document]) -> list[Chunk]:
    chunks: list[Chunk] = []
    for document in documents:
        chunks.extend(chunk_document(document))
    return chunks
