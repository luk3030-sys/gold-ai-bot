import json, os, time
from pathlib import Path

DATA_DIR = Path(os.getenv("DATA_DIR", "/tmp/gold_ai_bot"))
DATA_DIR.mkdir(parents=True, exist_ok=True)
HISTORY_FILE = DATA_DIR / "history.json"
STATE_FILE = DATA_DIR / "state.json"

def _read(path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default

def _write(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

def load_history(limit=50):
    h = _read(HISTORY_FILE, [])
    return h[-limit:]

def add_history(item):
    h = _read(HISTORY_FILE, [])
    item = dict(item)
    item["timestamp"] = int(time.time())
    h.append(item)
    _write(HISTORY_FILE, h[-500:])

def load_state():
    return _read(STATE_FILE, {})

def save_state(state):
    _write(STATE_FILE, state)
