from __future__ import annotations

import os
import shutil
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from langchain.tools import tool

from tools.fs_tools import shell_run


# -----------------------------
# Helpers
# -----------------------------

def _rc(r: Dict[str, Any]) -> int:
    """Return a normalized return code for shell_run outputs (supports legacy 'exit_code')."""
    if isinstance(r, dict):
        if "returncode" in r and isinstance(r["returncode"], int):
            return int(r["returncode"])
        if "exit_code" in r and isinstance(r["exit_code"], int):
            return int(r["exit_code"])
    return 1


def _ok(r: Dict[str, Any]) -> bool:
    """Return a normalized ok value for shell_run outputs."""
    if isinstance(r, dict) and "ok" in r:
        return bool(r["ok"])
    return _rc(r) == 0


def _step(name: str, r: Dict[str, Any], extra: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    s = {
        "name": name,
        "ok": _ok(r),
        "returncode": _rc(r),
        "stdout": (r.get("stdout") if isinstance(r, dict) else "") or "",
        "stderr": (r.get("stderr") if isinstance(r, dict) else "") or "",
        "cmd": (r.get("cmd") if isinstance(r, dict) else None),
        "cwd": (r.get("cwd") if isinstance(r, dict) else None),
    }
    if extra:
        s.update(extra)
    return s


def _ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def _safe_sandbox_dir(sandbox_key: str) -> str:
    # Keep it filesystem-friendly.
    cleaned = "".join(ch for ch in sandbox_key if ch.isalnum() or ch in ("-", "_")).strip("_-")
    return cleaned or f"sandbox_{int(time.time())}"


# -----------------------------
# Core verifier
# -----------------------------

def verify_repo(repo_url: str, ref: Optional[str] = None, sandbox_key: str = "default") -> Dict[str, Any]:
    """
    Verify a repo can be fetched/checked out and (if applicable) built.

    Returns:
      {
        "ok": bool,
        "repo_url": str,
        "ref": str|None,
        "workdir": str,
        "steps": [ {name, ok, returncode, stdout, stderr, ...}, ... ],
        "error": optional str,
      }
    """
    steps: List[Dict[str, Any]] = []

    if not repo_url or not isinstance(repo_url, str):
        return {"ok": False, "error": "verify_repo: repo_url is required", "steps": steps}

    base = Path(".sandbox_repos")
    _ensure_dir(base)

    sandbox_dir = base / _safe_sandbox_dir(sandbox_key)
    _ensure_dir(sandbox_dir)

    repo_dir = sandbox_dir / "repo"

    # If repo_dir exists but isn't a git repo, wipe it.
    if repo_dir.exists() and not (repo_dir / ".git").exists():
        shutil.rmtree(repo_dir, ignore_errors=True)

    # Clone or fetch
    if not repo_dir.exists():
        r = shell_run(["git", "clone", repo_url, str(repo_dir)], cwd=str(sandbox_dir), timeout_s=600)
        steps.append(_step("clone", r))
        if not _ok(r):
            return {
                "ok": False,
                "repo_url": repo_url,
                "ref": ref,
                "workdir": str(repo_dir),
                "steps": steps,
                "error": "verify_repo: git clone failed",
            }
    else:
        r = shell_run(["git", "fetch", "--all", "--prune"], cwd=str(repo_dir), timeout_s=600)
        steps.append(_step("fetch", r))
        if not _ok(r):
            return {
                "ok": False,
                "repo_url": repo_url,
                "ref": ref,
                "workdir": str(repo_dir),
                "steps": steps,
                "error": "verify_repo: git fetch failed",
            }

    # Checkout ref (optional)
    if ref:
        r1 = shell_run(["git", "checkout", ref], cwd=str(repo_dir), timeout_s=120)
        steps.append(_step("checkout", r1, {"ref": ref}))

        if not _ok(r1):
            # Fallback to origin/<ref>
            r2 = shell_run(["git", "checkout", f"origin/{ref}"], cwd=str(repo_dir), timeout_s=120)
            steps.append(_step("checkout_origin", r2, {"ref": f"origin/{ref}"}))
            if not _ok(r2):
                return {
                    "ok": False,
                    "repo_url": repo_url,
                    "ref": ref,
                    "workdir": str(repo_dir),
                    "steps": steps,
                    "error": f"verify_repo: git checkout failed for ref={ref}",
                }

    # Ensure clean working tree (after checkout)
    r = shell_run(["git", "status", "--porcelain"], cwd=str(repo_dir), timeout_s=60)
    steps.append(_step("git_status_porcelain", r))
    if _ok(r) and (r.get("stdout") or "").strip():
        return {
            "ok": False,
            "repo_url": repo_url,
            "ref": ref,
            "workdir": str(repo_dir),
            "steps": steps,
            "error": "verify_repo: working tree not clean after checkout/fetch",
        }

    # Build checks
    # Jekyll (Gemfile present)
    gemfile = repo_dir / "Gemfile"
    if gemfile.exists():
        # bundle install (local path to avoid global gem pollution)
        bundle_path = repo_dir / "vendor" / "bundle"
        _ensure_dir(bundle_path)

        r = shell_run(
            ["bundle", "install", "--path", str(bundle_path)],
            cwd=str(repo_dir),
            timeout_s=1200,
        )
        steps.append(_step("bundle_install", r))
        if not _ok(r):
            return {
                "ok": False,
                "repo_url": repo_url,
                "ref": ref,
                "workdir": str(repo_dir),
                "steps": steps,
                "error": "verify_repo: bundle install failed (is Ruby/Bundler installed?)",
            }

        # jekyll build
        r = shell_run(
            ["bundle", "exec", "jekyll", "build"],
            cwd=str(repo_dir),
            timeout_s=1200,
        )
        steps.append(_step("jekyll_build", r))
        if not _ok(r):
            return {
                "ok": False,
                "repo_url": repo_url,
                "ref": ref,
                "workdir": str(repo_dir),
                "steps": steps,
                "error": "verify_repo: jekyll build failed",
            }

    return {
        "ok": True,
        "repo_url": repo_url,
        "ref": ref,
        "workdir": str(repo_dir),
        "steps": steps,
    }


# -----------------------------
# Tool wrapper
# -----------------------------

@tool
def repo_verify(repo_url: str, ref: str = "", sandbox_key: str = "default") -> dict:
    """
    Verify a repo by cloning/fetching and running build checks.
    Args:
      repo_url: e.g. "https://github.com/TristanTA/tristan-allen-portfolio"
      ref: optional git ref (branch/sha). If empty, uses default branch.
      sandbox_key: stable key for caching clone between runs.
    """
    ref_norm = ref.strip() or None
    print("[Tools] Verifying Repo", repo_url)
    return verify_repo(repo_url=repo_url, ref=ref_norm, sandbox_key=sandbox_key)