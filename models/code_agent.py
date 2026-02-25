from __future__ import annotations

from openai import OpenAI
from langchain_core.tools import tool


@tool("message_code_agent")
def message_code_agent(agent_msg: str) -> str:
    """Write or modify code. Input: plain English request. Output: code-focused answer."""
    client = OpenAI()
    resp = client.responses.create(
        model="gpt-5-codex",
        input=agent_msg,
    )
    return resp.output_text or ""