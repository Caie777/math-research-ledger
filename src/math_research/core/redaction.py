"""Redact credentials in source notes without a network runtime."""

import re


def redact(text: str) -> str:
    return re.sub(
        r"(?i)([?&](?:api_key|apikey|key|token|access_token|secret|password)=)[^&\s]+",
        r"\1REDACTED",
        text,
    )
