import json
import os

ARCHIVE_FILE = os.getenv("ARCHIVE_FILE", "archive.json")

def load_archive():
    if not os.path.exists(ARCHIVE_FILE):
        return []
    try:
        with open(ARCHIVE_FILE, "r", encoding="utf-8") as f:
            content = f.read().strip()
            if not content:
                return []
            return json.loads(content)
    except json.JSONDecodeError:
        print(f"Warning: {ARCHIVE_FILE} contains invalid JSON. Starting fresh.")
        return []

def save_archive(messages):
    os.makedirs(os.path.dirname(ARCHIVE_FILE) or ".", exist_ok=True)
    with open(ARCHIVE_FILE, "w", encoding="utf-8") as f:
        json.dump(messages, f, ensure_ascii=False, indent=2)
