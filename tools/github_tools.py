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
    print(f"[Tools] Listing GitHub Tree {owner, repo}")
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
    print(f"[Tools] Reading GitHub Text File {owner, repo, path}")
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
    Search for code or text within a GitHub repository using the GitHub Code Search API.

    Args:
        query: str  
            The GitHub search query. Supports normal GitHub search syntax
            (e.g., '"Future Work"', 'TODO extension:md', 'path:_case_studies').

        owner: str (optional)  
            Repository owner (e.g., "TristanTA").  
            If provided with repo, the search will be limited to that repository.

        repo: str (optional)  
            Repository name (e.g., "tristan-allen-portfolio").  
            Must be provided together with owner to scope the search.

    Behavior:
        - If both owner and repo are provided, the function automatically scopes
          the query to that repository.
        - Requires authentication (GitHub App or token).
        - Subject to GitHub rate limits for search endpoints.

    Returns:
        dict:
            On success:
                {
                    "ok": True,
                    "data": <full GitHub search API response>
                }

            On failure:
                {
                    "ok": False,
                    "error": "<error message>"
                }

    Example:
        github_search_code(
            query='"Future Work" extension:md',
            owner="TristanTA",
            repo="tristan-allen-portfolio"
        )
    """
    print(f"[Tools] Searching GitHub Code {query, owner, repo}")
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
    Create or update a file in a GitHub repository (SHA-safe).

    Args:
        owner: str
        repo: str
        path: str (file path in repo)
        content: str (new full file contents)
        message: str (commit message)
        branch: str (optional, default="main")
        sha: str (optional) Current file SHA. If omitted and the file exists, this function
             will fetch the SHA automatically before updating.

    Returns:
        dict:
          - success: {"ok": True, "data": <GitHub API response>}
          - failure: {"ok": False, "error": "<error message>"}
    """
    print(f"[Tools] Proposing GitHub Change {owner, repo, message}")
    try:
        url = f"{GITHUB_API}/repos/{owner}/{repo}/contents/{path}"

        # If updating an existing file, GitHub requires the current blob SHA.
        if not sha:
            get_resp = requests.get(url, headers=gh_headers(), params={"ref": branch}, timeout=20)
            if get_resp.status_code == 200:
                sha = (get_resp.json() or {}).get("sha", "")
            elif get_resp.status_code not in (404,):
                # 404 means "file not found" -> create new file, no sha needed
                return {"ok": False, "error": f"github_propose_change error: HTTP {get_resp.status_code}: {get_resp.text}"}

        encoded_content = base64.b64encode(content.encode("utf-8")).decode("utf-8")

        payload = {
            "message": message,
            "content": encoded_content,
            "branch": branch,
        }
        if sha:
            payload["sha"] = sha

        put_resp = requests.put(url, headers=gh_headers(), json=payload, timeout=20)
        if put_resp.status_code not in (200, 201):
            return {"ok": False, "error": f"github_propose_change error: HTTP {put_resp.status_code}: {put_resp.text}"}

        return {"ok": True, "data": put_resp.json()}

    except Exception as e:
        return {"ok": False, "error": f"github_propose_change error: {type(e).__name__}: {e}"}
    
@tool
def github_create_branch(owner: str, repo: str, base_branch: str, new_branch: str) -> dict:
    """
    Create a new branch from an existing base branch.

    Args:
        owner: str
        repo: str
        base_branch: str (e.g., "main")
        new_branch: str (e.g., "audit/job-123")

    Returns:
        dict: {"ok": True, ...} or {"ok": False, "error": "..."}
    """
    try:
        # 1) get base branch SHA
        ref_url = f"{GITHUB_API}/repos/{owner}/{repo}/git/ref/heads/{base_branch}"
        r = requests.get(ref_url, headers=gh_headers(), timeout=20)
        if r.status_code != 200:
            return {"ok": False, "error": f"github_create_branch error: HTTP {r.status_code}: {r.text}"}
        base_sha = (r.json() or {}).get("object", {}).get("sha")

        # 2) create new ref
        create_url = f"{GITHUB_API}/repos/{owner}/{repo}/git/refs"
        payload = {"ref": f"refs/heads/{new_branch}", "sha": base_sha}
        c = requests.post(create_url, headers=gh_headers(), json=payload, timeout=20)

        if c.status_code not in (200, 201):
            # If already exists, treat as ok
            if c.status_code == 422 and "Reference already exists" in c.text:
                return {"ok": True, "branch": new_branch, "created": False}
            return {"ok": False, "error": f"github_create_branch error: HTTP {c.status_code}: {c.text}"}

        return {"ok": True, "branch": new_branch, "created": True}
    except Exception as e:
        return {"ok": False, "error": f"github_create_branch error: {type(e).__name__}: {e}"}


@tool
def github_create_pull_request(
    owner: str,
    repo: str,
    head_branch: str,
    base_branch: str,
    title: str,
    body: str = "",
) -> dict:
    """
    Create a pull request.

    Args:
        owner: str
        repo: str
        head_branch: str (branch with changes)
        base_branch: str (target branch, e.g., "main")
        title: str
        body: str (optional)

    Returns:
        dict
    """
    try:
        url = f"{GITHUB_API}/repos/{owner}/{repo}/pulls"
        payload = {"title": title, "head": head_branch, "base": base_branch, "body": body}
        r = requests.post(url, headers=gh_headers(), json=payload, timeout=20)
        if r.status_code not in (200, 201):
            return {"ok": False, "error": f"github_create_pull_request error: HTTP {r.status_code}: {r.text}"}
        data = r.json()
        return {"ok": True, "number": data.get("number"), "url": data.get("html_url")}
    except Exception as e:
        return {"ok": False, "error": f"github_create_pull_request error: {type(e).__name__}: {e}"}