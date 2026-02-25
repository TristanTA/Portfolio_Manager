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
    
@tool
def telegram_get_response(
    since_update_id: int = 0,
    timeout_seconds: int = 1800,
    poll_interval_seconds: int = 300,
    require_chat_id: bool = True,
) -> dict:
    """
    Poll Telegram for a response message.

    Args:
        since_update_id: int (only return updates with update_id > since_update_id)
        timeout_seconds: int (max time to wait before giving up; default 1800 = 30 min)
        poll_interval_seconds: int (seconds between polls; default 300 = 5 min)
        require_chat_id: bool (if True, only accept messages from TELEGRAM_CHAT_ID)

    Returns:
        dict:
          - on success: {"ok": True, "update_id": int, "text": str, "chat_id": str}
          - on timeout: {"ok": False, "timeout": True, "last_update_id": int}
          - on error:   {"ok": False, "error": "..."}
    """
    try:
        token = os.environ.get("TELEGRAM_BOT_TOKEN")
        chat_id_env = os.environ.get("TELEGRAM_CHAT_ID")

        if not token:
            return {"ok": False, "error": "telegram_get_response error: Missing TELEGRAM_BOT_TOKEN"}

        if require_chat_id and not chat_id_env:
            return {"ok": False, "error": "telegram_get_response error: Missing TELEGRAM_CHAT_ID"}

        url = f"https://api.telegram.org/bot{token}/getUpdates"
        deadline = time.time() + max(1, int(timeout_seconds))

        last_update_id = int(since_update_id)

        while time.time() < deadline:
            # Telegram uses "offset" as the next update_id to return
            offset = last_update_id + 1 if last_update_id else None

            params = {"timeout": 0}
            if offset is not None:
                params["offset"] = offset

            r = requests.get(url, params=params, timeout=20)
            if r.status_code != 200:
                return {
                    "ok": False,
                    "error": f"telegram_get_response error: Telegram API failed ({r.status_code}): {r.text}",
                }

            payload = r.json()
            results = payload.get("result", [])

            # Process updates in order; return the first matching text message
            for upd in results:
                uid = upd.get("update_id")
                if isinstance(uid, int) and uid > last_update_id:
                    last_update_id = uid

                msg = upd.get("message") or upd.get("edited_message") or {}
                text = msg.get("text")
                chat = msg.get("chat") or {}
                chat_id = str(chat.get("id", ""))

                if not text:
                    continue

                if require_chat_id and chat_id_env and chat_id != str(chat_id_env):
                    continue

                return {"ok": True, "update_id": last_update_id, "text": text, "chat_id": chat_id}

            time.sleep(max(1, int(poll_interval_seconds)))

        return {"ok": False, "timeout": True, "last_update_id": last_update_id}

    except Exception as e:
        return {"ok": False, "error": f"telegram_get_response error: {type(e).__name__}: {e}"}