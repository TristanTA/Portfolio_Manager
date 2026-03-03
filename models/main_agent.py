import os
import time
import uuid
from typing import Optional

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain.agents import create_agent
from langchain_openai import ChatOpenAI
from langchain.tools import tool
from langgraph.checkpoint.memory import InMemorySaver

from models.agent_router import AgentRouter
from tools.fs_tools import shell_run_tool, fs_read, fs_write, fs_list_dir, fs_exists, fs_delete
from tools.github_tools import (
    github_list_tree,
    github_read_text_file,
    github_search_code,
    github_propose_change,
    github_create_branch,
    github_create_pull_request,
)
from tools.memory_tools import memory_load, memory_save
from tools.notify_tools import telegram_send, telegram_get_response
from tools.repo_tools import repo_verify


class MainAgent:
    def __init__(self):
        self.debug = True
        self.failover = False
        self.system_msg = self._load_system_prompt()

        # Run completion flags (set by wrapped tools)
        self.run_flags = {"notified": False, "pr_created": False, "no_changes": False}

        # Model failover order
        self.models = [
            {"provider": "openrouter", "model": "z-ai/glm-4.5-air:free"},
            {"provider": "openrouter", "model": "openai/gpt-oss-20b:free"},
            {"provider": "openrouter", "model": "openai/gpt-oss-120b:free"},
            {"provider": "openai", "model": "gpt-5-mini"},
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
            """Get code or reasoning from a specialized LLM."""
            return self.router.message(content)

        # ---- Wrapped tools that set completion flags ----

        @tool
        def notify_user(message: str) -> str:
            """Send the user a Telegram message."""
            self.run_flags["notified"] = True
            return telegram_send(message)

        @tool
        def create_pr(title: str, body: str, head: str, base: str = "main") -> str:
            """Create a GitHub pull request."""
            self.run_flags["pr_created"] = True
            return github_create_pull_request(title=title, body=body, head=head, base=base)

        @tool
        def report_no_changes(reason: str = "") -> str:
            """Explicitly mark that there are no changes to apply this run (and notify)."""
            self.run_flags["no_changes"] = True
            msg = "✅ Weekly audit complete: no changes needed."
            if reason.strip():
                msg += f"\nReason: {reason.strip()}"
            self.run_flags["notified"] = True
            return telegram_send(msg)

        # Tools
        self.tools = [
            call_agent_router,
            shell_run_tool,
            fs_read,
            fs_write,
            fs_list_dir,
            fs_exists,
            fs_delete,
            github_list_tree,
            github_read_text_file,
            github_search_code,
            github_propose_change,
            github_create_branch,
            create_pr,            # wrapped
            memory_load,
            memory_save,
            notify_user,          # wrapped
            telegram_get_response,
            report_no_changes,    # new
            repo_verify,
        ]

        # Agent
        self.checkpointer = InMemorySaver()
        self.model = self._make_llm(self.models[self.model_idx])
        self.agent = create_agent(
            model=self.model,
            tools=self.tools,
            checkpointer=self.checkpointer,
            system_prompt=self.system_msg,
        )

    # --------------------
    # Setup
    # --------------------

    def _load_system_prompt(self) -> str:
        with open("system_prompt.txt", "r", encoding="utf-8") as f:
            return f.read()

    def _make_llm(self, spec: dict) -> ChatOpenAI:
        model_name = spec["model"]
        provider = spec.get("provider", "openrouter")
        print(f"[DEBUG] Using Model: {model_name}")
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
        self.agent = create_agent(
            model=self.model,
            tools=self.tools,
            checkpointer=self.checkpointer,
            system_prompt=self.system_msg,
        )

    def _failover(self) -> None:
        self.model_idx = (self.model_idx + 1) % len(self.models)
        self.failover = True
        if self.debug:
            spec = self.models[self.model_idx]
            print(
                f"[chat] failover -> idx={self.model_idx} model={spec['model']} provider={spec.get('provider')}"
            )
        self._rebuild_agent()

    # --------------------
    # Tool-call id normalization (OpenAI requires <= 40 chars)
    # --------------------

    def _normalize_tool_ids(self, messages):
        MAX_TOOL_ID = 40
        id_map = {}

        for m in messages:
            if isinstance(m, AIMessage) and getattr(m, "tool_calls", None):
                for tc in m.tool_calls:
                    tc_id = tc.get("id")
                    if isinstance(tc_id, str) and len(tc_id) > MAX_TOOL_ID:
                        new_id = uuid.uuid4().hex  # 32 chars
                        id_map[tc_id] = new_id
                        tc["id"] = new_id

        if id_map:
            for m in messages:
                if isinstance(m, ToolMessage):
                    if m.tool_call_id in id_map:
                        m.tool_call_id = id_map[m.tool_call_id]

        return messages

    # --------------------
    # Chat
    # --------------------

    def message(self, user_msg: str, thread_id: str = "default") -> str:
        if self.debug:
            print(f"[chat] recv thread={thread_id}")

        if user_msg.strip().lower() in {"reload system", "reload_system", "/reload_system", "/reload"}:
            try:
                self.system_msg = self._load_system_prompt()
                self._rebuild_agent()
                return "System prompt reloaded."
            except Exception as e:
                return f"System prompt reload failed: {type(e).__name__}: {e}"

        # Reset run flags for this call
        self.run_flags = {"notified": False, "pr_created": False, "no_changes": False}

        last_err: Optional[Exception] = None

        # We allow multiple "turns" per model attempt, because free models may respond briefly.
        MAX_TURNS = 6

        # Try each model at most once (but each model can get multiple turns)
        for attempt in range(len(self.models)):
            spec = self.models[self.model_idx]

            if self.debug:
                print(f"[chat] -> invoke attempt {attempt+1}/{len(self.models)} model={spec['model']}")

            try:
                for turn in range(MAX_TURNS):
                    t0 = time.perf_counter()

                    # If current provider is OpenAI, sanitize history first
                    if spec.get("provider") == "openai":
                        state = self.checkpointer.get(thread_id)
                        if state and "messages" in state:
                            state["messages"] = self._normalize_tool_ids(state["messages"])

                    if turn == 0:
                        input_payload = {"messages": [HumanMessage(content=user_msg)]}
                    else:
                        input_payload = {
                            "messages": [
                                HumanMessage(
                                    content=(
                                        "Continue the weekly audit workflow. "
                                        "Do not stop early. You MUST do one of:\n"
                                        "1) notify_user(...) and create_pr(...), then notify_user(...) with the PR link, OR\n"
                                        "2) report_no_changes(...).\n"
                                    )
                                )
                            ]
                        }

                    result = self.agent.invoke(
                        input_payload,
                        {"configurable": {"thread_id": thread_id}},
                    )

                    text = self._extract_text(result)

                    # Completion gate: we only end when the user was notified
                    # AND either a PR was created OR we explicitly reported no changes.
                    if self.run_flags["notified"] and (self.run_flags["pr_created"] or self.run_flags["no_changes"]):
                        if self.debug:
                            dt = time.perf_counter() - t0
                            print(f"[chat] <- ok {dt:.2f}s chars={len(text or '')}")
                        return text or "Done."

                    if self.debug:
                        dt = time.perf_counter() - t0
                        print(
                            f"[chat] .. incomplete turn={turn+1}/{MAX_TURNS} "
                            f"notified={self.run_flags['notified']} pr={self.run_flags['pr_created']} "
                            f"no_changes={self.run_flags['no_changes']} dt={dt:.2f}s"
                        )

                # If we hit MAX_TURNS without completion, treat as failure for this model.
                raise RuntimeError("Model did not complete workflow within MAX_TURNS")

            except Exception as e:
                last_err = e
                if self.debug:
                    print(f"[chat] !! error model={spec['model']} type={type(e).__name__}")
                    print(f"[chat] !! {e}")

                if self._should_failover(e):
                    self._failover()
                    time.sleep(0.4)
                    continue

                raise

        raise last_err if last_err else RuntimeError("All models failed")

    def _extract_text(self, result) -> str:
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
            "did not complete workflow within max_turns",
        ]
        return any(x in msg for x in retry_markers)