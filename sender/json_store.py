"""会话和配置的 JSON 文件读写。"""

import json
from pathlib import Path

DATA = Path(__file__).parent / "data"
SESSIONS_FILE = DATA / "sessions.json"
ACTIVE_FILE = DATA / "active_config.json"


def read_sessions():
    return json.loads(SESSIONS_FILE.read_text())


def write_sessions(data):
    SESSIONS_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False))


def add_session(session):
    store = read_sessions()
    store["sessions"].append(session)
    write_sessions(store)


def update_session(session_id, updates):
    store = read_sessions()
    for s in store["sessions"]:
        if s["session_id"] == session_id:
            s.update(updates)
            break
    write_sessions(store)


def read_active():
    return json.loads(ACTIVE_FILE.read_text())


def write_active(config):
    ACTIVE_FILE.write_text(json.dumps(config, indent=2, ensure_ascii=False))
