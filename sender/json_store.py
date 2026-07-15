"""会话和配置的 JSON 文件读写。"""

import json
import os
import threading
from pathlib import Path

DATA = Path(__file__).parent / "data"
SESSIONS_FILE = DATA / "sessions.json"
ACTIVE_FILE = DATA / "active_config.json"
STORE_LOCK = threading.RLock()


def read_sessions():
    with STORE_LOCK:
        return json.loads(SESSIONS_FILE.read_text())


def write_sessions(data):
    with STORE_LOCK:
        temp = SESSIONS_FILE.with_suffix(".tmp")
        temp.write_text(json.dumps(data, indent=2, ensure_ascii=False))
        os.replace(temp, SESSIONS_FILE)


def add_session(session):
    with STORE_LOCK:
        store = json.loads(SESSIONS_FILE.read_text())
        store["sessions"].append(session)
        write_sessions(store)


def update_session(session_id, updates):
    def _update(session):
        session.update(updates)
    mutate_session(session_id, _update)


def mutate_session(session_id, mutator):
    """Atomically update one session and return its updated dictionary."""
    with STORE_LOCK:
        store = json.loads(SESSIONS_FILE.read_text())
        for session in store["sessions"]:
            if session["session_id"] == session_id:
                mutator(session)
                write_sessions(store)
                return dict(session)
    return None


def read_active():
    with STORE_LOCK:
        return json.loads(ACTIVE_FILE.read_text())


def write_active(config):
    with STORE_LOCK:
        temp = ACTIVE_FILE.with_suffix(".tmp")
        temp.write_text(json.dumps(config, indent=2, ensure_ascii=False))
        os.replace(temp, ACTIVE_FILE)
