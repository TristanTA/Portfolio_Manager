import requests
import base64
from github_app_auth import gh_headers, GITHUB_API
from langchain.tools import tool


@tool
def github_list_tree(owner: str, repo: str, path: str = "", branch: str = "main") -> dict:
    """
    List files in a repository path.
    Args:
        owner: str
        repo: str
        path: str (optional, default="")
        branch: str (optional, default="main")
    Returns:
        dict: {"ok": True, ...} or {"ok": False, "error": "..."}
    """
    try:
        url = f"{GITHUB_API}/repos/{owner}/{repo}/contents/{path}"
        resp = requests.get(url, headers=gh_headers(), params={"ref": branch})
        resp.raise_for_status()

        return {"ok": True, "data": resp.json()}

    except Exception as e:
        return {"ok": False, "error": f"github_list_tree error: {type(e).__name__}: {e}"}


@tool
def github_read_text_file(owner: str, repo: str, path: str, branch: str = "main") -> dict:
    """
    Read a text file from a repository.
    Args:
        owner: str
        repo: str
        path: str
        branch: str (optional, default="main")
    Returns:
        dict
    """
    try:
        url = f"{GITHUB_API}/repos/{owner}/{repo}/contents/{path}"
        resp = requests.get(url, headers=gh_headers(), params={"ref": branch})
        resp.raise_for_status()

        data = resp.json()
        if data.get("encoding") == "base64":
            content = base64.b64decode(data["content"]).decode("utf-8")
        else:
            content = data.get("content", "")

        return {"ok": True, "content": content}

    except Exception as e:
        return {"ok": False, "error": f"github_read_text_file error: {type(e).__name__}: {e}"}


@tool
def github_search_code(query: str, owner: str = "", repo: str = "") -> dict:
    """
    Search code in a repository.
    Args:
        query: str
        owner: str (optional)
        repo: str (optional)
    Returns:
        dict
    """
    try:
        if owner and repo:
            query = f"{query} repo:{owner}/{repo}"

        url = f"{GITHUB_API}/search/code"
        resp = requests.get(url, headers=gh_headers(), params={"q": query})
        resp.raise_for_status()

        return {"ok": True, "data": resp.json()}

    except Exception as e:
        return {"ok": False, "error": f"github_search_code error: {type(e).__name__}: {e}"}


@tool
def github_propose_change(
    owner: str,
    repo: str,
    path: str,
    content: str,
    message: str,
    branch: str = "main",
    sha: str = ""
) -> dict:
    """
    Create or update a file in a repository.
    Args:
        owner: str
        repo: str
        path: str
        content: str
        message: str
        branch: str (optional)
        sha: str (optional, required for update)
    Returns:
        dict
    """
    try:
        url = f"{GITHUB_API}/repos/{owner}/{repo}/contents/{path}"
        encoded_content = base64.b64encode(content.encode("utf-8")).decode("utf-8")

        payload = {
            "message": message,
            "content": encoded_content,
            "branch": branch,
        }

        if sha:
            payload["sha"] = sha

        resp = requests.put(url, headers=gh_headers(), json=payload)
        resp.raise_for_status()

        return {"ok": True, "data": resp.json()}

    except Exception as e:
        return {"ok": False, "error": f"github_propose_change error: {type(e).__name__}: {e}"}