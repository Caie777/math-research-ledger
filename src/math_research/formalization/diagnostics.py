"""Deterministic compression of Lean's human-readable build diagnostics."""

from __future__ import annotations

import re

from pydantic import BaseModel

from .freeze import hash_bytes

_HEADER = re.compile(
    r"^(?:(error|warning|info):\s*)?(.+?\.lean):(\d+):(\d+):\s*"
    r"(?:(error|warning|info):\s*)?(.*)$"
)


class LeanDiagnostic(BaseModel):
    file: str
    line: int
    column: int
    severity: str
    message: str
    context: str = ""
    signature: str


def extract_diagnostics(text: str) -> list[LeanDiagnostic]:
    text = re.sub(r"\x1b\[[0-9;]*[A-Za-z]", "", text)
    groups: list[tuple[re.Match, list[str]]] = []
    for line in text.splitlines():
        match = _HEADER.match(line)
        if match:
            if len(groups) == 20:
                break
            groups.append((match, []))
        elif groups and not line.startswith(("trace:", "Some required", "error: build", "$ ")):
            groups[-1][1].append(line)
    result = []
    for match, context in groups:
        message = match[6][:2000]
        normalized = re.sub(r"\s+", " ", re.sub(r"\b\d+\b", "#", message)).strip()
        result.append(
            LeanDiagnostic(
                file=match[2],
                line=int(match[3]),
                column=int(match[4]),
                severity=match[1] or match[5] or "error",
                message=message,
                context="\n".join(context)[:3000],
                signature=hash_bytes(normalized.encode())[:20],
            )
        )
    if not result and ("error" in text.lower() or "failed" in text.lower()):
        message = text[-2500:]
        result.append(
            LeanDiagnostic(
                file="",
                line=0,
                column=0,
                severity="error",
                message=message,
                signature=hash_bytes(message.encode())[:20],
            )
        )
    return result
