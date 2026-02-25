from typing import Optional
from pathlib import Path
import os
import time
import subprocess
from typing import Any, Dict, List, Optional

from langchain.tools import tool


MAX_OUTPUT_CHARS = 12_000          # cap to keep tokens low
DEFAULT_TIMEOUT_S = 120
ALLOWED_CWD_ROOT = os.path.abspath(".")  # restrict to agent workspace


def _truncate(s: str, limit: int = MAX_OUTPUT_CHARS) -> str:
    if s is None:
        return ""
    if len(s) <= limit:
        return s
    # keep tail (usually where errors are)
    tail = s[-limit:]
    return f"[truncated {len(s) - limit} chars]\n{tail}"


def _safe_cwd(cwd: Optional[str]) -> str:
    if not cwd:
        return ALLOWED_CWD_ROOT
    abs_cwd = os.path.abspath(cwd)
    root = ALLOWED_CWD_ROOT
    # ensure cwd is within workspace
    if abs_cwd == root or abs_cwd.startswith(root + os.sep):
        return abs_cwd
    raise ValueError(f"cwd is outside allowed workspace: {abs_cwd}")


def shell_run(
    cmd: List[str],
    cwd: Optional[str] = None,
    timeout_s: Optional[int] = None,
    env: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """
    Run a command with no shell. Returns truncated stdout/stderr.
    Minimal + portable (Windows/Linux).
    """
    if not isinstance(cmd, list) or not cmd or not all(isinstance(x, str) for x in cmd):
        raise ValueError("cmd must be a non-empty list[str]")

    safe_cwd = _safe_cwd(cwd)
    to = int(timeout_s or DEFAULT_TIMEOUT_S)

    # Minimal environment: inherit current env, optionally add overrides
    run_env = os.environ.copy()
    if env:
        for k, v in env.items():
            if not isinstance(k, str) or not isinstance(v, str):
                raise ValueError("env must be dict[str,str]")
            run_env[k] = v

    t0 = time.perf_counter()
    try:
        p = subprocess.run(
            cmd,
            cwd=safe_cwd,
            env=run_env,
            capture_output=True,
            text=True,
            timeout=to,
            shell=False,
        )
        dur_ms = int((time.perf_counter() - t0) * 1000)
        out = p.stdout or ""
        err = p.stderr or ""
        return {
            "ok": p.returncode == 0,
            "exit_code": p.returncode,
            "stdout": _truncate(out),
            "stderr": _truncate(err),
            "duration_ms": dur_ms,
            "cwd": safe_cwd,
            "cmd": cmd,
        }
    except subprocess.TimeoutExpired as e:
        dur_ms = int((time.perf_counter() - t0) * 1000)
        out = (e.stdout or "") if isinstance(e.stdout, str) else ""
        err = (e.stderr or "") if isinstance(e.stderr, str) else ""
        return {
            "ok": False,
            "exit_code": 124,
            "stdout": _truncate(out),
            "stderr": _truncate(err) + "\n[timeout]",
            "duration_ms": dur_ms,
            "cwd": safe_cwd,
            "cmd": cmd,
        }

@tool
def shell_run_tool(cmd: list, cwd: str = None, timeout_s: int = 120) -> dict:
    """Run a command in the agent workspace. cmd must be list of strings."""
    return shell_run(cmd=cmd, cwd=cwd, timeout_s=timeout_s)


@tool
def fs_read(path_string: str) -> str:
    """
    Read content from a file.
    Args: path_string: str (file to read)
    Returns: package: str (entire file content)
    """
    print(f"[Tools] File System Read {path}")
    try:
        path = Path(path_string)
        with open(file=path, mode="r", encoding="utf-8") as file:
            package = file.read()
        return package
    except Exception as e:
        return f"fs_read error: {type(e).__name__}: {e}"


@tool
def fs_write(path_string: str, mode: str, content: str) -> Optional[str]:
    """
    Write content to a file in write mode (w) or append mode (a)
    Args:
        path_string: str (the file to write to)
        mode: str (w for write or a for append)
        content: str (content to add)
    Returns: None if success, otherwise str error message
    """
    print(f"[Tools] File System Write {path}")
    try:
        path = Path(path_string)
        with open(file=path, mode=mode, encoding="utf-8") as file:
            file.write(content)
        return None
    except Exception as e:
        return f"fs_write error: {type(e).__name__}: {e}"


@tool
def fs_list_dir(path_string: str) -> str:
    """
    List directory contents.
    Args:
        path_string: str (directory to list)
    Returns:
        str: newline-separated entries or error message
    """
    print(f"[Tools] File System List {path}")
    try:
        path = Path(path_string)
        if not path.exists():
            return f"fs_list_dir error: FileNotFoundError: Path does not exist: {path_string}"
        if not path.is_dir():
            return f"fs_list_dir error: NotADirectoryError: Path is not a directory: {path_string}"

        entries = sorted([p.name for p in path.iterdir()])
        return "\n".join(entries)
    except Exception as e:
        return f"fs_list_dir error: {type(e).__name__}: {e}"


@tool
def fs_exists(path_string: str) -> str:
    """
    Check whether a path exists.
    Args:
        path_string: str (path to check)
    Returns:
        str: "true" / "false" or error message
    """
    print(f"[Tools] File System Exists {path}")
    try:
        path = Path(path_string)
        return "true" if path.exists() else "false"
    except Exception as e:
        return f"fs_exists error: {type(e).__name__}: {e}"


@tool
def fs_delete(path_string: str) -> Optional[str]:
    """
    Delete a file or empty directory.
    Args:
        path_string: str (path to delete)
    Returns:
        None if success, otherwise str error message
    """
    print(f"[Tools] File System Delete {path}")
    try:
        path = Path(path_string)

        if not path.exists():
            return f"fs_delete error: FileNotFoundError: Path does not exist: {path_string}"

        if path.is_dir():
            # Keep it simple: only delete empty directories
            path.rmdir()
        else:
            path.unlink()

        return None
    except Exception as e:
        return f"fs_delete error: {type(e).__name__}: {e}"