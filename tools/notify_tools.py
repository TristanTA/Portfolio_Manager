import html
import requests
import os
import time 

from langchain.tools import tool


@tool
def telegram_send(text: str) -> dict:
    """
    Send a message via Telegram bot.
    Args:
        text: str
    Returns:
        dict
    """
    print("[Tools] Notifying User of:", text)
    try:
        token = os.environ.get("TELEGRAM_BOT_TOKEN")
        chat_id = os.environ.get("TELEGRAM_CHAT_ID")

        if not token or not chat_id:
            return {
                "ok": False,
                "error": "telegram_send error: Missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID",
            }

        if not text:
            return {
                "ok": False,
                "error": "telegram_send error: 'text' is required",
            }

        url = f"https://api.telegram.org/bot{token}/sendMessage"

        safe_text = f"<pre>{html.escape(text)}</pre>"

        r = requests.post(
            url,
            json={
                "chat_id": chat_id,
                "text": safe_text,
                "parse_mode": "HTML",
            },
            timeout=20,
        )

        if r.status_code != 200:
            return {
                "ok": False,
                "error": f"telegram_send error: Telegram API failed ({r.status_code}): {r.text}",
            }

        return {"ok": True, "sent": True}

    except Exception as e:
        return {"ok": False, "error": f"telegram_send error: {type(e).__name__}: {e}"}

def _read_last_update_id(path: str = "memory/update_id.txt") -> int:
    try:
        if not os.path.exists(path):
            return 0
        with open(path, "r", encoding="utf-8") as f:
            s = f.read().strip()
        return int(s) if s else 0
    except Exception:
        return 0


def _write_last_update_id(last_update_id: int, path: str = "memory/update_id.txt") -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(str(int(last_update_id)))


def _get_latest_update_id_from_telegram() -> int:
    try:
        token = os.environ.get("TELEGRAM_BOT_TOKEN")
        if not token:
            return 0

        url = f"https://api.telegram.org/bot{token}/getUpdates"
        r = requests.get(url, params={"timeout": 0}, timeout=20)
        if r.status_code != 200:
            return 0

        results = (r.json() or {}).get("result", [])
        latest = 0
        for upd in results:
            uid = upd.get("update_id")
            if isinstance(uid, int) and uid > latest:
                latest = uid
        return latest
    except Exception:
        return 0
    

@tool
def telegram_get_response(
    timeout_seconds: int = 18000,
    poll_interval_seconds: int = 300,
    require_chat_id: bool = True,
) -> dict:
    """
    Poll Telegram for a response message, remembering the last processed update_id in memory/update_id.txt.

    Args:
        timeout_seconds: int (max time to wait; default 1800)
        poll_interval_seconds: int (seconds between polls; default 300)
        require_chat_id: bool (if True, only accept messages from TELEGRAM_CHAT_ID)

    Returns:
        dict:
          - success: {"ok": True, "update_id": int, "text": str, "chat_id": str}
          - timeout: {"ok": False, "timeout": True, "last_update_id": int}
          - error:   {"ok": False, "error": "..."}
    """
    print("[Tools] Awaiting Telegram Response . . .")
    try:
        token = os.environ.get("TELEGRAM_BOT_TOKEN")
        chat_id_env = os.environ.get("TELEGRAM_CHAT_ID")

        if not token:
            return {"ok": False, "error": "telegram_get_response error: Missing TELEGRAM_BOT_TOKEN"}
        if require_chat_id and not chat_id_env:
            return {"ok": False, "error": "telegram_get_response error: Missing TELEGRAM_CHAT_ID"}

        url = f"https://api.telegram.org/bot{token}/getUpdates"
        deadline = time.time() + max(1, int(timeout_seconds))

        baseline = _get_latest_update_id_from_telegram()
        last_update_id = baseline
        offset = last_update_id + 1 if last_update_id else None

        while time.time() < deadline:
            params = {"timeout": 0}
            if offset is not None:
                params["offset"] = offset

            r = requests.get(url, params=params, timeout=20)
            if r.status_code != 200:
                return {"ok": False, "error": f"telegram_get_response error: HTTP {r.status_code}: {r.text}"}

            results = (r.json() or {}).get("result", [])

            for upd in results:
                uid = upd.get("update_id")
                if isinstance(uid, int) and uid > last_update_id:
                    last_update_id = uid
                    offset = last_update_id + 1  # advance offset

                msg = upd.get("message") or upd.get("edited_message") or {}
                text = msg.get("text")
                chat = msg.get("chat") or {}
                chat_id = str(chat.get("id", ""))

                if not text:
                    continue
                if require_chat_id and chat_id_env and chat_id != str(chat_id_env):
                    continue

                _write_last_update_id(last_update_id)
                print("[Tools] Message Received.")
                return {"ok": True, "update_id": last_update_id, "text": text, "chat_id": chat_id}

            time.sleep(max(1, int(poll_interval_seconds)))

        _write_last_update_id(last_update_id)
        print(f"[Tools] Telegram Timeout - No Response within {timeout_seconds / 60} minutes.")
        return {"ok": False, "timeout": True, "last_update_id": last_update_id}

    except Exception as e:
        return {"ok": False, "error": f"telegram_get_response error: {type(e).__name__}: {e}"}