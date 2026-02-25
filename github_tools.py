import base64
import datetime
import re
import requests
from typing import Optional, List, Dict, Any

from github_app_auth import gh_headers, GITHUB_API


def github_get_file(owner: str, repo: str, path: str, ref: str = "main") -> dict:
    url = f"{GITHUB_API}/repos/{owner}/{repo}/contents/{path}"
    r = requests.get(url, headers=gh_headers(), params={"ref": ref}, timeout=20)
    if r.status_code != 200:
        return {"error": r.status_code, "details": r.text}
    data = r.json()
    return {
        "path": data.get("path"),
        "sha": data.get("sha"),
        "encoding": data.get("encoding"),
        "content": data.get("content"),  # base64
    }

def github_list_tree(owner: str, repo: str, ref: str = "main", recursive: bool = True) -> dict:
    """
    Returns the git tree for a given branch/ref.
    If recursive=True, returns full file tree.
    """
    # Step 1: Get the SHA of the branch reference
    ref_url = f"{GITHUB_API}/repos/{owner}/{repo}/git/ref/heads/{ref}"
    rr = requests.get(ref_url, headers=gh_headers(), timeout=20)

    if rr.status_code != 200:
        return {"error": rr.status_code, "details": rr.text}

    sha = rr.json()["object"]["sha"]

    # Step 2: Get the tree from that SHA
    tree_url = f"{GITHUB_API}/repos/{owner}/{repo}/git/trees/{sha}"
    params = {"recursive": "1"} if recursive else {}

    tr = requests.get(tree_url, headers=gh_headers(), params=params, timeout=20)

    if tr.status_code != 200:
        return {"error": tr.status_code, "details": tr.text}

    return tr.json()


def github_create_branch(owner: str, repo: str, new_branch: str, from_ref: str = "main") -> dict:
    ref_url = f"{GITHUB_API}/repos/{owner}/{repo}/git/ref/heads/{from_ref}"
    rr = requests.get(ref_url, headers=gh_headers(), timeout=20)
    if rr.status_code != 200:
        return {"error": rr.status_code, "details": rr.text}
    sha = rr.json()["object"]["sha"]

    create_url = f"{GITHUB_API}/repos/{owner}/{repo}/git/refs"
    payload = {"ref": f"refs/heads/{new_branch}", "sha": sha}
    cr = requests.post(create_url, headers=gh_headers(), json=payload, timeout=20)

    # If branch already exists, return a clean message
    if cr.status_code == 422 and "Reference already exists" in cr.text:
        return {"ok": True, "note": "branch_exists", "ref": f"refs/heads/{new_branch}", "sha": sha}

    if cr.status_code not in (200, 201):
        return {"error": cr.status_code, "details": cr.text}
    return cr.json()


def github_put_file(
    owner: str,
    repo: str,
    path: str,
    content_b64: str,
    message: str,
    branch: str,
    sha: Optional[str] = None,
) -> dict:
    url = f"{GITHUB_API}/repos/{owner}/{repo}/contents/{path}"
    payload: Dict[str, Any] = {
        "message": message,
        "content": content_b64,
        "branch": branch,
    }
    if sha:
        payload["sha"] = sha

    r = requests.put(url, headers=gh_headers(), json=payload, timeout=20)
    if r.status_code not in (200, 201):
        return {"error": r.status_code, "details": r.text}
    return r.json()


def github_create_pull_request(
    owner: str,
    repo: str,
    title: str,
    head: str,
    base: str = "main",
    body: str = "",
) -> dict:
    url = f"{GITHUB_API}/repos/{owner}/{repo}/pulls"
    payload = {"title": title, "head": head, "base": base, "body": body}
    r = requests.post(url, headers=gh_headers(), json=payload, timeout=20)

    # If PR already exists for head->base, GitHub returns 422 with a message.
    if r.status_code == 422 and "A pull request already exists" in r.text:
        return {"error": 422, "details": r.text, "note": "pr_exists"}

    if r.status_code not in (200, 201):
        return {"error": r.status_code, "details": r.text}

    data = r.json()
    return {
        "number": data.get("number"),
        "url": data.get("html_url"),
        "state": data.get("state"),
        "title": data.get("title"),
    }


def _slug(s: str) -> str:
    s = s.strip().lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return re.sub(r"-+", "-", s).strip("-")[:48]


def github_propose_change(
    owner: str,
    repo: str,
    changes: List[Dict[str, Any]],
    pr_title: str,
    pr_body: str,
    base_branch: str = "main",
    branch_prefix: str = "agent/portfolio",
) -> dict:
    """
    changes: list of
      - {"path": "...", "content_text": "...", "message": "..."}  (upsert)
    """
    stamp = datetime.datetime.utcnow().strftime("%Y%m%d-%H%M%S")
    branch = f"{branch_prefix}-{stamp}-{_slug(pr_title)}"

    br = github_create_branch(owner, repo, branch, from_ref=base_branch)
    if "error" in br:
        return {"error": "create_branch_failed", "details": br}

    results = []
    for ch in changes:
        path = ch["path"]
        content_text = ch["content_text"]
        msg = ch.get("message") or f"Update {path}"

        existing = github_get_file(owner, repo, path, ref=branch)
        sha = None
        if "error" not in existing:
            sha = existing.get("sha")

        content_b64 = base64.b64encode(content_text.encode("utf-8")).decode("utf-8")
        put = github_put_file(owner, repo, path, content_b64, msg, branch=branch, sha=sha)
        results.append({"path": path, "result": put})

        if "error" in put:
            return {"error": "put_file_failed", "branch": branch, "details": results}

    pr = github_create_pull_request(
        owner, repo, title=pr_title, head=branch, base=base_branch, body=pr_body
    )
    if "error" in pr:
        return {"error": "create_pr_failed", "branch": branch, "details": pr, "file_results": results}

    return {"ok": True, "branch": branch, "pr": pr, "file_results": results}