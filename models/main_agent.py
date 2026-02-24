import os
import requests
import time
from typing import Optional

from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.tools import tool
from langchain.agents import create_agent
from langchain_openai import ChatOpenAI

class MainAgent:
    def __init__(self):
        self.system_msg = self.get_system_message()
        self.debug = True

        self.models =[
            {"provider": "openrouter", "model": "openai/gpt-oss-20b:free"},
            {"provider": "openrouter", "model": "openai/gpt-oss-120b:free"},
            {"provider": "openai",     "model": "gpt-5-mini"}
        ]
        self.model_idx = 0

        self.openrouter_api_key = os.environ["OPENROUTER_API_KEY"]
        self.openrouter_base_url = "https://openrouter.ai/api/v1"
        self.openai_api_key = os.environ["OPENAI_API_KEY"]

        self.tools = [github_repo_info, github_search_repos]
        self.model = self._make_llm(self.models[self.model_idx])
        self.agent = create_agent(
            model=self.model,
            tools=self.tools,
            system_prompt=self.system_msg
            )
        
# --------------------
# Init Helpers
# --------------------
    def get_system_message(self) -> str:
        """Load system prompt from system_prompt.txt"""
        with open("system_prompt.txt", "r", encoding="utf-8") as f:
            system_msg = f.read()
            return system_msg

    def _make_llm(self, spec: dict) -> ChatOpenAI:
        """
        Create LLM model based on active model selection
        Default to Openrouter models first (free)
        """
        model_name = spec["model"]
        provider = spec.get("provider", "openrouter")

        if self.debug:
            print(f"[chat] llm init -> {model_name} ({provider})")

        if provider == "openai":
            return ChatOpenAI(
                model=model_name,
                api_key=os.environ["OPENAI_API_KEY"],
                temperature=0.2,
                timeout=90,
                max_retries=0,
            )

        # default: openrouter
        return ChatOpenAI(
            model=model_name,
            base_url=self.openrouter_base_url,
            api_key=self.openrouter_api_key,
            temperature=0.2,
            timeout=90,
            max_retries=0,
        )

# --------------------
# Failover System (if the model call fails, move to next model)
# --------------------
    def _rebuild_agent(self) -> None:
        """Recreate model + agent for the current model_idx."""
        self.model = self._make_llm(self.models[self.model_idx])
        self.agent = create_agent(
            model=self.model,
            tools=self.tools,
            system_prompt=self.system_msg,
        )

    def _failover(self) -> None:
        """Advance to next model (wraps around)."""
        if self.model_idx < len(self.models) - 1:
            self.model_idx += 1
        else:
            self.model_idx = 0
        if self.debug:
            spec = self.models[self.model_idx]
            print(f"[chat] failover -> idx={self.model_idx} model={spec['model']} provider={spec.get('provider')}")
        self._rebuild_agent()

    def _last_ai_message(self, result) -> Optional[AIMessage]:
        """
        create_agent usually returns a dict with 'messages'.
        Find the last AIMessage.
        """
        msgs = None
        if isinstance(result, dict):
            msgs = result.get("messages")
        if not msgs:
            return None

        for m in reversed(msgs):
            if isinstance(m, AIMessage):
                return m
        return None

    def _should_failover(self, e: Exception) -> bool:
        """Conservative retry/failover policy."""
        msg = str(e).lower()
        retry_markers = [
            "timeout",
            "timed out",
            "rate limit",
            "429",
            "502",
            "503",
            "504",
            "bad gateway",
            "service unavailable",
            "gateway timeout",
            "connection",
            "temporarily",
            "try again",
        ]
        return any(x in msg for x in retry_markers)
    
# --------------------
# Message Agent and Helpers
# --------------------
    def message(self, user_msg: str, thread_id: str = "default") -> str:
        """
        Send one user message through the agent, with:
        - /reload command to reload system_prompt.txt
        - failover across models on retryable errors or bad/empty outputs
        """
        if self.debug:
            print(f"[chat] recv thread={thread_id} text={user_msg!r}")

        reload_response = self._maybe_reload_system_prompt(user_msg)
        if reload_response is not None:
            return reload_response

        last_err: Optional[Exception] = None

        for attempt in range(len(self.models)):
            model_name = self.models[self.model_idx]["model"]
            t0 = time.perf_counter()

            if self.debug:
                print(f"[chat] -> invoke attempt {attempt+1}/{len(self.models)} model={model_name}")

            try:
                result = self._invoke_agent(user_msg, thread_id)
                last_ai = self._last_ai_message(result)

                self._raise_if_invalid_tool_calls(last_ai)
                response_text = self._extract_final_text_or_raise(last_ai, t0)

                return response_text

            except Exception as e:
                last_err = e
                self._debug_log_error(e, t0, model_name)

                if self._should_try_next_model(e):
                    self._failover()
                    time.sleep(0.2)
                    continue

                raise

        raise last_err if last_err else RuntimeError("All models failed.")

    def _maybe_reload_system_prompt(self, user_msg: str) -> Optional[str]:
        if user_msg.strip().lower() not in {"reload system", "reload_system", "/reload_system", "/reload"}:
            return None
        try:
            with open("system_prompt.txt", "r", encoding="utf-8") as f:
                self.system_msg = f.read()
            self._rebuild_agent()
            return "System prompt reloaded."
        except Exception as e:
            return f"System prompt reload failed: {type(e).__name__}: {e}"


    def _invoke_agent(self, user_msg: str, thread_id: str):
        return self.agent.invoke(
            {"messages": [HumanMessage(content=user_msg)]},
            {"configurable": {"thread_id": thread_id}},
        )


    def _raise_if_invalid_tool_calls(self, last_ai):
        if last_ai is None:
            return
        invalid = getattr(last_ai, "invalid_tool_calls", None) or []
        if not invalid:
            return

        if self.debug:
            print("[chat] invalid_tool_calls detected:")
            for it in invalid:
                name = getattr(it, "get", lambda k, d=None: None)("name")
                err = getattr(it, "get", lambda k, d=None: None)("error")
                print(f"  - {name}: {err}")

        raise RuntimeError("Invalid tool call JSON from model")


    def _extract_final_text_or_raise(self, last_ai, t0: float) -> str:
        if last_ai is None:
            if self.debug:
                dt = time.perf_counter() - t0
                print(f"[chat] <- no AIMessage {dt:.2f}s")
            raise RuntimeError("No AIMessage returned")

        content = getattr(last_ai, "content", None)
        tool_calls = getattr(last_ai, "tool_calls", None) or []

        # Normal successful response
        if isinstance(content, str) and content.strip():
            if self.debug:
                dt = time.perf_counter() - t0
                print(f"[chat] <- ok {dt:.2f}s chars={len(content.strip())}")
            return content.strip()

        # Empty + no tool calls => bad output
        if not tool_calls:
            if self.debug:
                dt = time.perf_counter() - t0
                print(f"[chat] <- empty assistant content {dt:.2f}s (no tool_calls)")
            raise RuntimeError("Empty assistant text from model")

        # Tool calls but no final text => treat as failure (forces failover)
        if self.debug:
            dt = time.perf_counter() - t0
            print(f"[chat] <- tool_calls={len(tool_calls)} but empty text {dt:.2f}s")
        raise RuntimeError("Tool calls emitted but no final assistant text")


    def _debug_log_error(self, e: Exception, t0: float, model_name: str):
        if not self.debug:
            return
        dt = time.perf_counter() - t0
        print(f"[chat] !! error {dt:.2f}s model={model_name} type={type(e).__name__}")
        print(f"[chat] !! {e}")


    def _should_try_next_model(self, e: Exception) -> bool:
        # Always fail over on our own “bad output” signals
        if isinstance(e, RuntimeError):
            msg = str(e)
            if (
                "Invalid tool call JSON" in msg
                or "Empty assistant text" in msg
                or "No AIMessage returned" in msg
                or "Tool calls emitted but no final assistant text" in msg
            ):
                return True

        # Otherwise defer to retryable error heuristic
        return self._should_failover(e)

# --------------------
# TOOLS
# --------------------
@tool
def github_repo_info(owner: str, repo: str) -> dict:
    """
    Get metadata about a public GitHub repository.

    Args:
        owner: GitHub username or organization name.
        repo: Repository name.

    Returns:
        Dictionary containing repository metadata.
    """
    url = f"https://api.github.com/repos/{owner}/{repo}"

    headers = {}
    token = os.getenv("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"

    response = requests.get(url, headers=headers, timeout=15)

    if response.status_code != 200:
        return {"error": f"GitHub API error: {response.status_code}", "details": response.text}

    data = response.json()

    return {
        "full_name": data.get("full_name"),
        "description": data.get("description"),
        "stars": data.get("stargazers_count"),
        "forks": data.get("forks_count"),
        "open_issues": data.get("open_issues_count"),
        "language": data.get("language"),
        "created_at": data.get("created_at"),
        "updated_at": data.get("updated_at"),
        "url": data.get("html_url"),
    }

@tool
def github_search_repos(query: str) -> list:
    """
    Search GitHub repositories by keyword.
    """
    url = "https://api.github.com/search/repositories"
    response = requests.get(url, params={"q": query, "sort": "stars"}, timeout=15)

    if response.status_code != 200:
        return {"error": f"GitHub API error: {response.status_code}"}

    items = response.json().get("items", [])[:5]

    return [
        {
            "full_name": r["full_name"],
            "stars": r["stargazers_count"],
            "url": r["html_url"],
            "description": r["description"],
        }
        for r in items
    ]