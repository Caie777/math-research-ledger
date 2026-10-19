"""Recovery guidance for malformed Research Agent tool calls."""

TOOL_PARSE_RECOVERY = """Your previous tool call was malformed or truncated.
Retry with compact, valid JSON arguments for an available Research Agent tool.
Do not claim an action succeeded until its tool result confirms it.
"""
