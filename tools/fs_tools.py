from __future__ import annotations
import os
import subprocess
from typing import Any, Dict, List, Optional, Union
from pathlib import Path
import time

from langchain.tools import tool


MAX_OUTPUT_CHARS = 12_000          # cap to keep tokens low
DEFAULT_TIMEOUT_S = 120
ALLOWED_CWD_ROOT = os.path.abspath(".")  # restrict to agent workspace


@tool
def shell_run_tool(cmd: Union[str, List[str]], cwd: Optional[str] = None, timeout_s: int = 120) -> Dict[str, Any]:
    """
    Run a shell command safely and return structured output.
    Never raises FileNotFoundError (WinError 2); returns ok=False instead.
    """
    try:
        # If cmd is a string, use shell=True so Windows can resolve built-ins and spaced commands.
        use_shell = isinstance(cmd, str)

        completed = subprocess.run(
            cmd,
            cwd=cwd,
            timeout=timeout_s,
            capture_output=True,
            text=True,
            shell=use_shell,
        )

        return {
            "ok": completed.returncode == 0,
            "returncode": completed.returncode,
            "stdout": completed.stdout,
            "stderr": completed.stderr,
            "cmd": cmd,
            "cwd": cwd,
            "shell": use_shell,
        }

    except FileNotFoundError as e:
        # This is your WinError 2 case: executable not found.
        return {
            "ok": False,
            "error": f"FileNotFoundError: {e}",
            "cmd": cmd,
            "cwd": cwd,
            "hint": "Executable not found on PATH. Agent likely called a unix tool (rg/grep/ls) or cmd was passed as a single string without shell.",
        }
    except subprocess.TimeoutExpired as e:
        return {
            "ok": False,
            "error": f"TimeoutExpired: {e}",
            "cmd": cmd,
            "cwd": cwd,
        }
    except Exception as e:
        return {
            "ok": False,
            "error": f"{type(e).__name__}: {e}",
            "cmd": cmd,
            "cwd": cwd,
        }

# Non tool-reference verison
def shell_run(cmd: Union[str, List[str]], cwd: Optional[str] = None, timeout_s: int = 120) -> Dict[str, Any]:
    """
    Run a shell command safely and return structured output.
    Never raises FileNotFoundError (WinError 2); returns ok=False instead.
    """
    try:
        # If cmd is a string, use shell=True so Windows can resolve built-ins and spaced commands.
        use_shell = isinstance(cmd, str)

        completed = subprocess.run(
            cmd,
            cwd=cwd,
            timeout=timeout_s,
            capture_output=True,
            text=True,
            shell=use_shell,
        )

        return {
            "ok": completed.returncode == 0,
            "returncode": completed.returncode,
            "stdout": completed.stdout,
            "stderr": completed.stderr,
            "cmd": cmd,
            "cwd": cwd,
            "shell": use_shell,
        }

    except FileNotFoundError as e:
        # This is your WinError 2 case: executable not found.
        return {
            "ok": False,
            "error": f"FileNotFoundError: {e}",
            "cmd": cmd,
            "cwd": cwd,
            "hint": "Executable not found on PATH. Agent likely called a unix tool (rg/grep/ls) or cmd was passed as a single string without shell.",
        }
    except subprocess.TimeoutExpired as e:
        return {
            "ok": False,
            "error": f"TimeoutExpired: {e}",
            "cmd": cmd,
            "cwd": cwd,
        }
    except Exception as e:
        return {
            "ok": False,
            "error": f"{type(e).__name__}: {e}",
            "cmd": cmd,
            "cwd": cwd,
        }

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