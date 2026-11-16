"""Validate evidence references without mistaking code examples for citations."""

import re

from app.agents.base import Evidence

_CODE = re.compile(r"(```[\s\S]*?```|~~~[\s\S]*?~~~|`[^`\n]*`)")
_CITATION = re.compile(r"\[(S\d+)\](?:\([^\n)]*\))?")


def strip_citations(answer: str) -> str:
    """Remove source markers from prose, preserving code examples verbatim."""
    parts = _CODE.split(answer)
    for index in range(0, len(parts), 2):
        parts[index] = re.sub(r"\[S\d+\](?:\([^\n)]*\))?", "", parts[index])
    return "".join(parts).strip()


def has_invalid_citations(answer: str, evidence: list[Evidence]) -> bool:
    allowed = {f"S{n}" for n in range(1, len(evidence) + 1)}
    prose = _CODE.split(answer)[::2]
    return any(match[1] not in allowed for part in prose for match in _CITATION.finditer(part))


def validate_citations(answer: str, evidence: list[Evidence]) -> tuple[str, list[dict]]:
    available = {f"S{n}": item for n, item in enumerate(evidence, 1)}
    used: dict[str, None] = {}

    def replace(match: re.Match) -> str:
        citation = match[1]
        if citation not in available:
            return ""  # An invented ID can never create a source or link.
        used[citation] = None
        return f"[{citation}]"  # Citation targets come from Evidence, never model URLs.

    parts = _CODE.split(answer)
    for index in range(0, len(parts), 2):
        parts[index] = _CITATION.sub(replace, parts[index])
    return "".join(parts), [available[key].source(key) for key in used]
