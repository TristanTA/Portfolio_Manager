import requests
from github_app_auth import gh_headers, GITHUB_API
from langchain.tools import tool


@tool
def github_list_tree(args: dict) -> dict:
    """
    List files in a repository path.
    Args:
        args: {
            "owner": str,
            "repo": str,
            "path": str (optional, default=""),
            "branch": str (optional, default="main")
        }
    Returns:
        dict: result or error
    """
    try:
        owner = args.get("owner")
        repo = args.get("repo")
        path = args.get("path", "")
        branch = args.get("branch", "main")

        url = f"{GITHUB_API}/repos/{owner}/{repo}/contents/{path}"
        resp = requests.get(url, headers=gh_headers(), params={"ref": branch})
        resp.raise_for_status()

        return {"ok": True, "data": resp.json()}
    except Exception as e:
        return {"ok": False, "error": f"github_list_tree error: {type(e).__name__}: {e}"}


@tool
def github_read_text_file(args: dict) -> dict:
    """
    Read a text file from a repository.
    Args:
        args: {
            "owner": str,
            "repo": str,
            "path": str,
            "branch": str (optional, default="main")
        }
    Returns:
        dict: file content or error
    """
    try:
        owner = args.get("owner")
        repo = args.get("repo")
        path = args.get("path")
        branch = args.get("branch", "main")

        url = f"{GITHUB_API}/repos/{owner}/{repo}/contents/{path}"
        resp = requests.get(url, headers=gh_headers(), params={"ref": branch})
        resp.raise_for_status()

        data = resp.json()
        if data.get("encoding") == "base64":
            import base64
            content = base64.b64decode(data["content"]).decode("utf-8")
        else:
            content = data.get("content", "")

        return {"ok": True, "content": content}
    except Exception as e:
        return {"ok": False, "error": f"github_read_text_file error: {type(e).__name__}: {e}"}


@tool
def github_search_code(args: dict) -> dict:
    """
    Search code in a repository.
    Args:
        args: {
            "query": str,
            "owner": str (optional),
            "repo": str (optional)
        }
    Returns:
        dict: search results or error
    """
    try:
        query = args.get("query")
        owner = args.get("owner")
        repo = args.get("repo")

        if owner and repo:
            query = f"{query} repo:{owner}/{repo}"

        url = f"{GITHUB_API}/search/code"
        resp = requests.get(url, headers=gh_headers(), params={"q": query})
        resp.raise_for_status()

        return {"ok": True, "data": resp.json()}
    except Exception as e:
        return {"ok": False, "error": f"github_search_code error: {type(e).__name__}: {e}"}


@tool
def github_propose_change(args: dict) -> dict:
    """
    Create or update a file in a repository (simple commit).
    Args:
        args: {
            "owner": str,
            "repo": str,
            "path": str,
            "content": str,
            "message": str,
            "branch": str (optional, default="main"),
            "sha": str (optional, required if updating)
        }
    Returns:
        dict: result or error
    """
    try:
        import base64

        owner = args.get("owner")
        repo = args.get("repo")
        path = args.get("path")
        content = args.get("content")
        message = args.get("message")
        branch = args.get("branch", "main")
        sha = args.get("sha")

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