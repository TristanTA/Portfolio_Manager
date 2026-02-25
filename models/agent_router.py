from __future__ import annotations

from models.code_agent import message_code_agent
from models.reason_agent import message_reasoning_agent

from langchain.tools import tool

class AgentRouter:
    """
    Simple router:
    - If the user is asking for code edits/snippets/files -> code agent
    - Otherwise -> reasoning agent
    """

    def __init__(self):
        pass
    
    def message(self, agent_msg: str) -> str:
        text = (agent_msg or "").lower()

        code_signals = [
            "write code", "implement", "refactor", "function", "class", "bug", "traceback",
            "error:", "stack trace", "python", "typescript", "javascript", "langchain",
            "langgraph", "pydantic", "file:", ".py", ".ts", ".js", "diff", "patch",
            "drop-in", "module", "import", "pip", "venv",
        ]

        wants_code = any(s in text for s in code_signals)
        if wants_code:
            return message_code_agent.run(agent_msg)

        return message_reasoning_agent.run(agent_msg)