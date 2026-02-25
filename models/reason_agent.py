from __future__ import annotations

from openai import OpenAI
from langchain_core.tools import tool


@tool("message_reasoning_agent")
def message_reasoning_agent(agent_msg: str) -> str:
    """Reason, plan, or debug conceptually. Input: request. Output: concise reasoning/planning."""
    client = OpenAI()
    resp = client.responses.create(
        model="gpt-5",
        input=agent_msg,
    )
    return resp.output_text or ""