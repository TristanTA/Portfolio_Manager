import json
import os

from langchain.tools import tool

@tool
def memory_load(args: dict) -> dict:
    """
    Load memory JSON from disk. If it does not exist, create a default structure.
    Args:
        args: {
            "path": str
        }
    Returns:
        dict: {"ok": True, ...} or {"ok": False, "error": "..."}
    """
    try:
        path = args.get("path")
        if not path:
            return {"ok": False, "error": "memory_load error: ValueError: 'path' is required"}

        if not os.path.exists(path):
            base = {"version": 1, "runs": [], "items": []}
            os.makedirs(os.path.dirname(path), exist_ok=True)

            with open(path, "w", encoding="utf-8") as f:
                json.dump(base, f, indent=2)

            return {"ok": True, "path": path, "data": base}

        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        return {"ok": True, "path": path, "data": data}

    except Exception as e:
        return {"ok": False, "error": f"memory_load error: {type(e).__name__}: {e}"}

@tool
def memory_save(args: dict) -> dict:
    """
    Save memory JSON to disk.
    Args:
        args: {
            "path": str,
            "data": dict
        }
    Returns:
        dict: {"ok": True, ...} or {"ok": False, "error": "..."}
    """
    try:
        path = args.get("path")
        data = args.get("data")

        if not path:
            return {"ok": False, "error": "memory_save error: ValueError: 'path' is required"}

        os.makedirs(os.path.dirname(path), exist_ok=True)

        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

        return {"ok": True, "path": path, "saved": True}

    except Exception as e:
        return {"ok": False, "error": f"memory_save error: {type(e).__name__}: {e}"}