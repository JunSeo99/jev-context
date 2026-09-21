from __future__ import annotations

import hashlib
import re
from pathlib import Path

from .models import Block, Document, Excerpt

IGNORED_DIRS = {".git", ".venv", "venv", "node_modules", "__pycache__", ".ssh"}
SECRET_NAMES = {".env", "credentials", "credentials.json", "id_rsa", "id_ed25519"}


class SourceError(ValueError):
    pass


def source_lines(text: str) -> list[str]:
    """Editor-style LF lines, retaining CRLF and Unicode separators verbatim."""
    parts = text.split("\n")
    return [p + "\n" for p in parts[:-1]] + ([parts[-1]] if parts[-1] else [])


def safe_path(root: Path, relative: str) -> Path:
    path = Path(relative)
    if path.is_absolute() or ".." in path.parts:
        raise SourceError("outside_root")
    if any(p in IGNORED_DIRS for p in path.parts):
        raise SourceError("excluded")
    if (
        path.name in SECRET_NAMES
        or path.name.startswith(".env.")
        or path.suffix in {".pem", ".key"}
    ):
        raise SourceError("excluded_secret")
    resolved_root = root.resolve()
    resolved = (resolved_root / path).resolve()
    if not resolved.is_relative_to(resolved_root):
        raise SourceError("outside_root")
    # Never follow links: a benign-looking filename can alias an excluded secret.
    current = resolved_root
    for part in path.parts:
        current /= part
        if current.is_symlink():
            raise SourceError("symlink")
    return resolved


def split_blocks(text: str, *, max_chars: int = 2400) -> tuple[Block, ...]:
    """Lossless line spans. Paragraphs/headings and top-level code are boundaries."""
    lines = source_lines(text)
    if not lines:
        return ()
    result: list[Block] = []
    start = 0
    size = 0
    heading = ""
    block_heading = ""
    fence_char, fence_length = "", 0

    def emit(end: int):
        nonlocal start, size, block_heading
        chunk = "".join(lines[start:end])
        if chunk.strip():
            result.append(Block(f"b{start + 1}", start + 1, end, chunk, block_heading))
        start, size = end, 0
        block_heading = heading

    for i, line in enumerate(lines):
        in_fence = bool(fence_char)
        is_heading = bool(re.match(r"^#{1,6}\s", line)) and not in_fence
        is_symbol = bool(re.match(r"^(?:async )?(?:def |class )", line)) and not in_fence
        if i > start and (is_heading or is_symbol or size + len(line) > max_chars):
            emit(i)
        if is_heading:
            heading = line.strip()
            if i == start:
                block_heading = heading
        size += len(line)
        fence = re.match(r"^ {0,3}(`{3,}|~{3,})(.*)$", line.rstrip("\r\n"))
        if fence:
            marks, tail = fence.groups()
            if not fence_char:
                fence_char, fence_length = marks[0], len(marks)
            elif marks[0] == fence_char and len(marks) >= fence_length and not tail.strip():
                fence_char, fence_length = "", 0
        if not line.strip() and not fence_char and size >= 200:
            emit(i + 1)
    if start < len(lines):
        emit(len(lines))
    return tuple(result)


def read_document(
    root: Path, relative: str, *, max_bytes: int = 2_000_000, block_chars: int = 2400
) -> Document:
    path = safe_path(root, relative)
    try:
        with path.open("rb") as f:
            raw = f.read(max_bytes + 1)
    except OSError as e:
        raise SourceError("unreadable") from e
    if len(raw) > max_bytes:
        raise SourceError("file_too_large")
    if b"\x00" in raw:
        raise SourceError("binary")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as e:
        raise SourceError("not_utf8") from e
    if not text.strip():
        raise SourceError("empty")
    return Document(
        relative, hashlib.sha256(raw).hexdigest(), text, split_blocks(text, max_chars=block_chars)
    )


def verify_excerpt(root: Path, excerpt: Excerpt) -> str:
    doc = read_document(root, excerpt.path)
    if doc.digest != excerpt.digest:
        raise SourceError("source_changed")
    lines = source_lines(doc.text)
    if not 1 <= excerpt.start <= excerpt.end <= len(lines):
        raise SourceError("invalid_range")
    actual = "".join(lines[excerpt.start - 1 : excerpt.end])
    if actual != excerpt.text:
        raise SourceError("excerpt_mismatch")
    return actual
