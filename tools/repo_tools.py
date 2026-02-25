import os
import re
import shutil
from typing import Any, Dict, List, Optional

from langchain_core.tools import tool

from tools.fs_tools import shell_run

VERIFY_ROOT = os.path.abspath("./_verify")
SANDBOX_ROOT = os.path.abspath("./_sandbox")

DEFAULT_TIMEOUT_CLONE = 180
DEFAULT_TIMEOUT_INSTALL = 300
DEFAULT_TIMEOUT_TEST = 300
DEFAULT_TIMEOUT_BUILD = 300


def _repo_key_from_url(repo_url: str) -> str:
    """
    Supports:
      https://github.com/Owner/Repo.git
      https://github.com/Owner/Repo
      git@github.com:Owner/Repo.git
    """
    m = re.search(r"github\.com[/:]([^/]+)/([^/.]+)(?:\.git)?$", repo_url.strip())
    if not m:
        # fallback: last 2 path segments
        parts = re.split(r"[/:]", repo_url.strip().rstrip(".git"))
        if len(parts) >= 2:
            return f"{parts[-2]}__{parts[-1]}"
        return "unknown__repo"
    owner, repo = m.group(1), m.group(2)
    return f"{owner}__{repo}"


def _ensure_dir(p: str) -> None:
    os.makedirs(p, exist_ok=True)


def _copy_overlay(overlay_dir: str, repo_dir: str) -> int:
    """
    Copies overlay_dir/** into repo_dir/** (same relative paths), overwriting.
    Returns count of files copied.
    """
    if not os.path.isdir(overlay_dir):
        return 0

    copied = 0
    for root, _, files in os.walk(overlay_dir):
        for fn in files:
            src = os.path.join(root, fn)
            rel = os.path.relpath(src, overlay_dir)
            dst = os.path.join(repo_dir, rel)
            _ensure_dir(os.path.dirname(dst))
            shutil.copy2(src, dst)
            copied += 1
    return copied


def _detect_project_type(repo_dir: str) -> str:
    """
    Minimal heuristics:
      - "jekyll" if Gemfile exists OR (_config.yml exists and (Gemfile OR .ruby-version exists))
      - "python" if requirements.txt OR pyproject.toml OR setup.py exists
      - else "unknown"
    """
    def exists(name: str) -> bool:
        return os.path.exists(os.path.join(repo_dir, name))

    if exists("Gemfile") or (exists("_config.yml") and (exists(".ruby-version") or exists("Gemfile.lock"))):
        return "jekyll"
    if exists("requirements.txt") or exists("pyproject.toml") or exists("setup.py") or exists("setup.cfg"):
        return "python"
    return "unknown"


def _venv_python(repo_dir: str) -> Optional[str]:
    """
    Returns path to venv python if .venv exists.
    """
    cand = [
        os.path.join(repo_dir, ".venv", "bin", "python"),
        os.path.join(repo_dir, ".venv", "Scripts", "python.exe"),
        os.path.join(repo_dir, ".venv", "Scripts", "python"),
    ]
    for p in cand:
        if os.path.exists(p):
            return p
    return None


def _has_tests(repo_dir: str) -> bool:
    if os.path.isdir(os.path.join(repo_dir, "tests")):
        return True
    # minimal: any file starting with test_*.py in root
    for fn in os.listdir(repo_dir):
        if fn.startswith("test_") and fn.endswith(".py"):
            return True
    return False


def verify_repo(
    repo_url: str,
    ref: str = "main",
    sandbox_key: Optional[str] = None,
    timeout_clone_s: int = DEFAULT_TIMEOUT_CLONE,
    timeout_install_s: int = DEFAULT_TIMEOUT_INSTALL,
    timeout_test_s: int = DEFAULT_TIMEOUT_TEST,
    timeout_build_s: int = DEFAULT_TIMEOUT_BUILD,
) -> Dict[str, Any]:
    """
    Minimal repo verification:
      1) git clone/fetch/checkout
      2) apply sandbox overlay + optional patch.diff
      3) install deps + run smoke tests (python/jekyll)
      4) return compact report

    Sandbox convention:
      ./_sandbox/<key>/overlay/**        (file overlay)
      ./_sandbox/<key>/patch.diff        (optional unified diff)
    where key defaults to "<owner>__<repo>" derived from repo_url.
    """
    key = sandbox_key or _repo_key_from_url(repo_url)
    run_dir = os.path.join(VERIFY_ROOT, key)
    repo_dir = os.path.join(run_dir, "repo")
    sandbox_dir = os.path.join(SANDBOX_ROOT, key)
    overlay_dir = os.path.join(sandbox_dir, "overlay")
    patch_path = os.path.join(sandbox_dir, "patch.diff")

    _ensure_dir(VERIFY_ROOT)
    _ensure_dir(SANDBOX_ROOT)
    _ensure_dir(run_dir)

    steps: List[Dict[str, Any]] = []

    # --- 1) clone or fetch
    if not os.path.isdir(os.path.join(repo_dir, ".git")):
        # fresh clone
        if os.path.isdir(repo_dir):
            shutil.rmtree(repo_dir, ignore_errors=True)
        r = shell_run(["git", "clone", repo_url, "repo"], cwd=run_dir, timeout_s=timeout_clone_s)
        steps.append({"name": "clone", "exit": r["exit_code"]})
        if not r["ok"]:
            return {"ok": False, "key": key, "repo_dir": repo_dir, "steps": steps, "stderr_tail": r["stderr"], "stdout_tail": r["stdout"]}
    else:
        # update
        r1 = shell_run(["git", "fetch", "--all", "--prune"], cwd=repo_dir, timeout_s=timeout_clone_s)
        steps.append({"name": "fetch", "exit": r1["exit_code"]})
        if not r1["ok"]:
            return {"ok": False, "key": key, "repo_dir": repo_dir, "steps": steps, "stderr_tail": r1["stderr"], "stdout_tail": r1["stdout"]}

    # checkout ref
    r = shell_run(["git", "checkout", ref], cwd=repo_dir, timeout_s=timeout_clone_s)
    steps.append({"name": "checkout", "exit": r["exit_code"], "ref": ref})
    if not r["ok"]:
        # try origin/ref fallback
        r2 = shell_run(["git", "checkout", f"origin/{ref}"], cwd=repo_dir, timeout_s=timeout_clone_s)
        steps.append({"name": "checkout_origin", "exit": r2["exit_code"], "ref": f"origin/{ref}"})
        if not r2["ok"]:
            return {"ok": False, "key": key, "repo_dir": repo_dir, "steps": steps, "stderr_tail": (r["stderr"] + "\n" + r2["stderr"]), "stdout_tail": (r["stdout"] + "\n" + r2["stdout"])}

    # hard reset to avoid local drift (minimal reproducibility)
    r = shell_run(["git", "reset", "--hard"], cwd=repo_dir, timeout_s=timeout_clone_s)
    steps.append({"name": "reset_hard", "exit": r["exit_code"]})
    if not r["ok"]:
        return {"ok": False, "key": key, "repo_dir": repo_dir, "steps": steps, "stderr_tail": r["stderr"], "stdout_tail": r["stdout"]}

    # --- 2) apply sandbox overlay + patch
    copied = _copy_overlay(overlay_dir, repo_dir)
    steps.append({"name": "overlay_copy", "exit": 0, "copied_files": copied})

    if os.path.isfile(patch_path):
        r = shell_run(["git", "apply", "--whitespace=nowarn", patch_path], cwd=repo_dir, timeout_s=60)
        steps.append({"name": "git_apply_patch", "exit": r["exit_code"]})
        if not r["ok"]:
            return {"ok": False, "key": key, "repo_dir": repo_dir, "steps": steps, "stderr_tail": r["stderr"], "stdout_tail": r["stdout"]}

    # --- 3) detect type and run minimal plan
    ptype = _detect_project_type(repo_dir)
    steps.append({"name": "detect_type", "exit": 0, "type": ptype})

    if ptype == "python":
        # create venv
        r = shell_run(["python", "-m", "venv", ".venv"], cwd=repo_dir, timeout_s=120)
        steps.append({"name": "venv_create", "exit": r["exit_code"]})
        if not r["ok"]:
            return {"ok": False, "key": key, "repo_dir": repo_dir, "steps": steps, "stderr_tail": r["stderr"], "stdout_tail": r["stdout"]}

        vpy = _venv_python(repo_dir) or "python"

        # upgrade pip tooling
        r = shell_run([vpy, "-m", "pip", "install", "-U", "pip", "wheel", "setuptools"], cwd=repo_dir, timeout_s=timeout_install_s)
        steps.append({"name": "pip_upgrade", "exit": r["exit_code"]})
        if not r["ok"]:
            return {"ok": False, "key": key, "repo_dir": repo_dir, "steps": steps, "stderr_tail": r["stderr"], "stdout_tail": r["stdout"]}

        # install deps (minimal)
        if os.path.isfile(os.path.join(repo_dir, "requirements.txt")):
            r = shell_run([vpy, "-m", "pip", "install", "-r", "requirements.txt"], cwd=repo_dir, timeout_s=timeout_install_s)
            steps.append({"name": "pip_install_requirements", "exit": r["exit_code"]})
            if not r["ok"]:
                return {"ok": False, "key": key, "repo_dir": repo_dir, "steps": steps, "stderr_tail": r["stderr"], "stdout_tail": r["stdout"]}
        elif os.path.isfile(os.path.join(repo_dir, "pyproject.toml")) or os.path.isfile(os.path.join(repo_dir, "setup.py")) or os.path.isfile(os.path.join(repo_dir, "setup.cfg")):
            r = shell_run([vpy, "-m", "pip", "install", "-e", "."], cwd=repo_dir, timeout_s=timeout_install_s)
            steps.append({"name": "pip_install_editable", "exit": r["exit_code"]})
            if not r["ok"]:
                return {"ok": False, "key": key, "repo_dir": repo_dir, "steps": steps, "stderr_tail": r["stderr"], "stdout_tail": r["stdout"]}
        else:
            steps.append({"name": "pip_install_skip", "exit": 0})

        # smoke: compileall (always safe)
        r = shell_run([vpy, "-m", "compileall", "-q", "."], cwd=repo_dir, timeout_s=timeout_test_s)
        steps.append({"name": "compileall", "exit": r["exit_code"]})
        if not r["ok"]:
            return {"ok": False, "key": key, "repo_dir": repo_dir, "steps": steps, "stderr_tail": r["stderr"], "stdout_tail": r["stdout"]}

        # tests if present
        if _has_tests(repo_dir):
            r = shell_run([vpy, "-m", "pytest", "-q"], cwd=repo_dir, timeout_s=timeout_test_s)
            steps.append({"name": "pytest", "exit": r["exit_code"]})
            if not r["ok"]:
                return {"ok": False, "key": key, "repo_dir": repo_dir, "steps": steps, "stderr_tail": r["stderr"], "stdout_tail": r["stdout"]}
        else:
            steps.append({"name": "pytest_skip_no_tests", "exit": 0})

        print("[Tools] Repo Verification Complete.")
        return {"ok": True, "key": key, "repo_dir": repo_dir, "steps": steps}

    if ptype == "jekyll":
        # install gems + build site
        r = shell_run(["bundle", "install"], cwd=repo_dir, timeout_s=timeout_install_s)
        steps.append({"name": "bundle_install", "exit": r["exit_code"]})
        if not r["ok"]:
            return {"ok": False, "key": key, "repo_dir": repo_dir, "steps": steps, "stderr_tail": r["stderr"], "stdout_tail": r["stdout"]}

        r = shell_run(["bundle", "exec", "jekyll", "build"], cwd=repo_dir, timeout_s=timeout_build_s)
        steps.append({"name": "jekyll_build", "exit": r["exit_code"]})
        if not r["ok"]:
            return {"ok": False, "key": key, "repo_dir": repo_dir, "steps": steps, "stderr_tail": r["stderr"], "stdout_tail": r["stdout"]}

        # minimal output asserts
        expected = ["_site/index.html", "_site/assets/main.css"]
        missing = []
        for rel in expected:
            if not os.path.exists(os.path.join(repo_dir, rel)):
                missing.append(rel)
        steps.append({"name": "assert_outputs", "exit": 0 if not missing else 1, "missing": missing})
        if missing:
            return {"ok": False, "key": key, "repo_dir": repo_dir, "steps": steps, "stderr_tail": "Missing built outputs: " + ", ".join(missing), "stdout_tail": ""}

        print("[Tools] Repo Verification Complete.")
        return {"ok": True, "key": key, "repo_dir": repo_dir, "steps": steps}

    # unknown: do only a git status + compileall if python present
    r = shell_run(["git", "status", "--porcelain"], cwd=repo_dir, timeout_s=30)
    steps.append({"name": "git_status", "exit": r["exit_code"]})

    # If python files exist, try compileall without deps (best-effort)
    any_py = any(fn.endswith(".py") for fn in os.listdir(repo_dir))
    if any_py:
        r = shell_run(["python", "-m", "compileall", "-q", "."], cwd=repo_dir, timeout_s=timeout_test_s)
        steps.append({"name": "compileall_best_effort", "exit": r["exit_code"]})
        if not r["ok"]:
            return {"ok": False, "key": key, "repo_dir": repo_dir, "steps": steps, "stderr_tail": r["stderr"], "stdout_tail": r["stdout"]}

    print("[Tools] Repo Verification Complete.")
    return {"ok": True, "key": key, "repo_dir": repo_dir, "steps": steps}


@tool
def repo_verify(repo_url: str, ref: str = "main", sandbox_key: str = None) -> dict:
    """Clone repo, apply ./_sandbox overlay/patch, install deps, run smoke tests, return compact report."""
    print(f"[Tools] Verifying Repo {repo_url}")
    return verify_repo(repo_url=repo_url, ref=ref, sandbox_key=sandbox_key)