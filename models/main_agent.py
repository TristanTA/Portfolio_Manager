import os
import time
from typing import Optional

from langchain_core.messages import AIMessage, HumanMessage
from langchain.agents import create_agent
from langchain_openai import ChatOpenAI
from langchain.tools import tool

from models.agent_router import AgentRouter
from tools.fs_tools import shell_run_tool, fs_read, fs_write, fs_list_dir, fs_exists, fs_delete
from tools.github_tools import github_list_tree, github_read_text_file, github_search_code, github_propose_change, github_create_branch, github_create_pull_request
from tools.memory_tools import memory_load, memory_save
from tools.notify_tools import telegram_send, telegram_get_response
from tools.repo_tools import repo_verify

class MainAgent:
    def __init__(self):
        self.debug = True
        self.system_msg = self._load_system_prompt()

        # Model failover order
        self.models = [
            {"provider":"openrouter","model":"openrouter/free"},
            {"provider":"openrouter","model":"arcee-ai/trinity-large-preview:free"},
            {"provider":"openrouter","model":"z-ai/glm-4.5-air:free"},
            {"provider": "openrouter", "model": "openai/gpt-oss-20b:free"},
            {"provider": "openrouter", "model": "openai/gpt-oss-120b:free"},
            {"provider": "openai",     "model": "gpt-5-mini"},
        ]
        self.model_idx = 0

        # Providers
        self.openrouter_api_key = os.environ["OPENROUTER_API_KEY"]
        self.openrouter_base_url = "https://openrouter.ai/api/v1"
        self.openai_api_key = os.environ["OPENAI_API_KEY"]

        # Router (specialized sub-agents)
        self.router = AgentRouter()
        @tool
        def call_agent_router(content: str) -> str:
            """
            Get code or reasoning from a specialized LLM
            Args: content: str (prompt for reasoning or code agent)
            Returns: str (response from LLM)
            """
            response = self.router.message(content)
            return response

        # Tools (new tool system)
        self.tools = [call_agent_router, shell_run_tool, fs_read, fs_write, fs_list_dir, 
                      fs_exists, fs_delete, github_list_tree, github_read_text_file, 
                      github_search_code, github_propose_change, github_create_branch, github_create_pull_request, 
                      memory_load, memory_save, telegram_send, telegram_get_response, repo_verify]

        # Agent
        self.model = self._make_llm(self.models[self.model_idx])
        self.agent = create_agent(model=self.model, tools=self.tools, system_prompt=self.system_msg)

    # --------------------
    # Setup
    # --------------------

    def _load_system_prompt(self) -> str:
        with open("system_prompt.txt", "r", encoding="utf-8") as f:
            return f.read()

    def _make_llm(self, spec: dict) -> ChatOpenAI:
        model_name = spec["model"]
        provider = spec.get("provider", "openrouter")

        if self.debug:
            print(f"[chat] llm init -> {model_name} ({provider})")

        if provider == "openai":
            return ChatOpenAI(
                model=model_name,
                api_key=self.openai_api_key,
                temperature=0.2,
                timeout=90,
                max_retries=0,
            )

        # openrouter
        return ChatOpenAI(
            model=model_name,
            base_url=self.openrouter_base_url,
            api_key=self.openrouter_api_key,
            temperature=0.2,
            timeout=90,
            max_retries=0,
        )

    def _rebuild_agent(self) -> None:
        self.model = self._make_llm(self.models[self.model_idx])
        self.agent = create_agent(model=self.model, tools=self.tools, system_prompt=self.system_msg)

    def _failover(self) -> None:
        self.model_idx = (self.model_idx + 1) % len(self.models)
        if self.debug:
            spec = self.models[self.model_idx]
            print(f"[chat] failover -> idx={self.model_idx} model={spec['model']} provider={spec.get('provider')}")
        self._rebuild_agent()

    # --------------------
    # Chat
    # --------------------

    def message(self, user_msg: str, thread_id: str = "default") -> str:
        if self.debug:
            print(f"[chat] recv thread={thread_id} text={user_msg!r}")

        # Simple reload command
        if user_msg.strip().lower() in {"reload system", "reload_system", "/reload_system", "/reload"}:
            try:
                self.system_msg = self._load_system_prompt()
                self._rebuild_agent()
                return "System prompt reloaded."
            except Exception as e:
                return f"System prompt reload failed: {type(e).__name__}: {e}"

        last_err: Optional[Exception] = None

        # Try each model at most once
        for attempt in range(len(self.models)):
            spec = self.models[self.model_idx]
            t0 = time.perf_counter()

            if self.debug:
                print(f"[chat] -> invoke attempt {attempt+1}/{len(self.models)} model={spec['model']}")

            try:
                result = self.agent.invoke(
                    {"messages": [HumanMessage(content=user_msg)]},
                    {"configurable": {"thread_id": thread_id}},
                )

                text = self._extract_text(result)
                if not text:
                    raise RuntimeError("Empty assistant text")

                if self.debug:
                    dt = time.perf_counter() - t0
                    print(f"[chat] <- ok {dt:.2f}s chars={len(text)}")
                return text

            except Exception as e:
                last_err = e
                if self.debug:
                    dt = time.perf_counter() - t0
                    print(f"[chat] !! error {dt:.2f}s model={spec['model']} type={type(e).__name__}")
                    print(f"[chat] !! {e}")

                # Failover on common transient issues + empty output
                if self._should_failover(e):
                    self._failover()
                    time.sleep(0.2)
                    continue

                raise

        raise last_err if last_err else RuntimeError("All models failed")

    def _extract_text(self, result) -> str:
        """
        create_agent typically returns {"messages": [...]}.
        Find last AIMessage with non-empty content.
        """
        msgs = result.get("messages") if isinstance(result, dict) else None
        if not msgs:
            return ""

        for m in reversed(msgs):
            if isinstance(m, AIMessage):
                content = getattr(m, "content", "")
                if isinstance(content, str) and content.strip():
                    return content.strip()
        return ""

    def _should_failover(self, e: Exception) -> bool:
        msg = str(e).lower()
        retry_markers = [
            "empty assistant text",
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