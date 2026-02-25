import os
import time
import requests
import jwt  # pyjwt

GITHUB_API = "https://api.github.com"


def _get_env(name: str) -> str:
    v = os.getenv(name)
    if not v:
        raise RuntimeError(f"Missing env var: {name}")
    return v


def _github_app_jwt() -> str:
    app_id = _get_env("GH_APP_ID")
    private_key = _get_env("GH_APP_PRIVATE_KEY").replace("\\n", "\n")

    now = int(time.time())
    payload = {
        "iat": now - 60,
        "exp": now + 9 * 60,  # < 10 minutes
        "iss": app_id,
    }
    token = jwt.encode(payload, private_key, algorithm="RS256")
    return token.decode("utf-8") if isinstance(token, bytes) else token


def github_app_get_installation_token() -> str:
    installation_id = _get_env("GH_INSTALLATION_ID")
    app_jwt = _github_app_jwt()

    url = f"{GITHUB_API}/app/installations/{installation_id}/access_tokens"
    headers = {
        "Authorization": f"Bearer {app_jwt}",
        "Accept": "application/vnd.github+json",
    }
    r = requests.post(url, headers=headers, timeout=20)
    if r.status_code not in (200, 201):
        raise RuntimeError(f"Install token error: {r.status_code} {r.text}")
    return r.json()["token"]


def gh_headers():
    token = github_app_get_installation_token()
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
    }