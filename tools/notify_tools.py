import html
import requests
import os

from langchain.tools import tool

@tool
def telegram_send(args: dict) -> dict:
    """
    Send a message via Telegram bot.
    Args:
        args: {
            "text": str
        }
    Returns:
        dict: {"ok": True, ...} or {"ok": False, "error": "..."}
    """
    try:
        token = os.environ.get("TELEGRAM_BOT_TOKEN")
        chat_id = os.environ.get("TELEGRAM_CHAT_ID")

        if not token or not chat_id:
            return {
                "ok": False,
                "error": "telegram_send error: EnvironmentError: Missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID",
            }

        text = args.get("text")
        if not text:
            return {
                "ok": False,
                "error": "telegram_send error: ValueError: 'text' is required",
            }

        url = f"https://api.telegram.org/bot{token}/sendMessage"

        parse_mode = "HTML"
        safe_text = f"<pre>{html.escape(text)}</pre>"

        r = requests.post(
            url,
            json={
                "chat_id": chat_id,
                "text": safe_text,
                "parse_mode": parse_mode,
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