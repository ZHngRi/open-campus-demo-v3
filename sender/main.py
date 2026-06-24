"""
OpenCap management backend - FastAPI

Start:
    uvicorn sender.main:app --reload --host 0.0.0.0 --port 8000
"""

import shutil
import threading
import time
import uuid
from datetime import datetime
from pathlib import Path
import zipfile
import requests

from fastapi import FastAPI, UploadFile, File
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from sender.json_store import (
    read_sessions, add_session, update_session, write_sessions,
    read_active, write_active,
)
from sender.marker_sender import send_session

app = FastAPI()

send_queue = []
send_results = []
send_thread = None
send_lock = threading.Lock()

MAX_RESULTS = 20

ROOT = Path(__file__).parent
DATA = ROOT / "data"
VIDEOS = DATA / "videos"
SESSIONS = DATA / "sessions"
STATIC = ROOT / "static"

# Static files
app.mount("/static", StaticFiles(directory=str(STATIC)), name="static")


DONE_STATUSES = {"done", "complete", "completed", "success", "ready"}
FAILED_STATUSES = {"error", "failed", "failure"}
PROCESSING_STATUSES = {
    "new", "created", "queued", "pending", "processing", "running",
    "recording", "uploading", "submitted",
}
RESULT_EXTENSIONS = {".trc", ".mot", ".osim", ".zip", ".json"}


def _find_session(store, session_id):
    for s in store.get("sessions", []):
        if s.get("session_id") == session_id:
            return s
    return None


def _parse_dt(value):
    if not value:
        return None
    try:
        text = str(value)
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        dt = datetime.fromisoformat(text)
        return dt.astimezone()
    except Exception:
        return None


def _remote_created_at(rs):
    return rs.get("created_at") or rs.get("createdAt") or rs.get("created")


def _remote_name(rs):
    session_name_keys = (
        "sessionName", "session_name", "sessionTitle", "session_title",
        "display_name", "displayName", "title",
    )
    for key in session_name_keys:
        value = rs.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()

    meta = rs.get("meta") or rs.get("metadata") or {}
    if isinstance(meta, dict):
        for key in session_name_keys + ("name",):
            value = meta.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()

    trials = rs.get("trials") or []
    if trials:
        trial = trials[0] or {}
        for key in session_name_keys + ("trial_name", "trialName", "name"):
            value = trial.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()

    value = rs.get("name")
    if isinstance(value, str) and value.strip():
        return value.strip()

    return "OpenCap " + str(rs.get("id", ""))[:8]


def _remote_status(rs):
    trials = rs.get("trials") or []
    if trials:
        latest_status = str((trials[0] or {}).get("status", "")).lower()
        if latest_status in DONE_STATUSES:
            return "done"
        if latest_status in FAILED_STATUSES:
            return "failed"
        if latest_status in PROCESSING_STATUSES:
            return "processing"

    statuses = []
    for key in ("status", "state", "processing_status", "processingStatus"):
        if rs.get(key):
            statuses.append(str(rs[key]).lower())

    if any(st in DONE_STATUSES for st in statuses):
        return "done"
    if any(st in FAILED_STATUSES for st in statuses):
        return "failed"
    if any(st in PROCESSING_STATUSES for st in statuses):
        return "processing"
    return "processing"


def _dir_has_result_files(result_dir):
    if not result_dir.exists():
        return False
    return any(
        f.is_file() and f.suffix.lower() in RESULT_EXTENSIONS
        for f in result_dir.rglob("*")
    )


def _result_dirs_for_session(session):
    if not session:
        return []

    candidates = []
    if session.get("result_dir"):
        candidates.append(Path(session["result_dir"]))
    if session.get("session_id"):
        candidates.append(SESSIONS / session["session_id"])
    if session.get("api_session_id"):
        candidates.append(SESSIONS / ("remote_" + session["api_session_id"][:8]))

    deduped = []
    seen = set()
    for result_dir in candidates:
        key = str(result_dir)
        if key not in seen:
            deduped.append(result_dir)
            seen.add(key)
    return deduped


def _result_dir_for_session(session):
    candidates = _result_dirs_for_session(session)
    for result_dir in candidates:
        if _dir_has_result_files(result_dir):
            return result_dir
    for result_dir in candidates:
        if result_dir.exists():
            return result_dir
    return SESSIONS / session["session_id"]


def _has_result_files(session):
    result_dir = _result_dir_for_session(session)
    return _dir_has_result_files(result_dir)


def _repair_local_result_statuses(store):
    repaired = 0
    for session in store.get("sessions", []):
        result_dir = _result_dir_for_session(session)
        if not _dir_has_result_files(result_dir):
            continue

        result_dir_text = str(result_dir)
        if session.get("result_dir") != result_dir_text:
            session["result_dir"] = result_dir_text
            repaired += 1

        if session.get("api_session_id") and session.get("status") != "done":
            session["status"] = "done"
            repaired += 1

        if session.get("download_status") != "done":
            session["download_status"] = "done"
            session["note"] = "Local result files detected"
            repaired += 1

    return repaired


def _restore_orphan_uploads(store):
    sessions = store.setdefault("sessions", [])
    known_ids = {s.get("session_id") for s in sessions}
    added = 0

    if not VIDEOS.exists():
        return added

    for video_dir in sorted(VIDEOS.iterdir()):
        if not video_dir.is_dir() or video_dir.name in known_ids:
            continue

        video_files = [
            f for f in video_dir.iterdir()
            if f.is_file() and f.suffix.lower() in {".mp4", ".mov"}
        ]
        if not video_files:
            continue

        video_path = video_files[0]
        sessions.append({
            "session_id": video_dir.name,
            "name": video_path.name,
            "video_path": str(video_path),
            "result_dir": str(SESSIONS / video_dir.name),
            "status": "uploaded",
            "created_at": datetime.fromtimestamp(video_path.stat().st_mtime).isoformat(),
            "note": "Automatically restored local upload",
        })
        known_ids.add(video_dir.name)
        added += 1

    return added


def _matching_local_without_api(store, rs, used_ids):
    remote_dt = _parse_dt(_remote_created_at(rs))
    if not remote_dt:
        return None

    best = None
    best_delta = None
    for s in store.get("sessions", []):
        if s.get("session_id") in used_ids or s.get("api_session_id"):
            continue
        if s.get("status") not in {"processing", "failed"}:
            continue
        local_dt = _parse_dt(s.get("created_at"))
        if not local_dt:
            continue
        delta = abs((remote_dt - local_dt).total_seconds())
        if delta <= 3600 and (best_delta is None or delta < best_delta):
            best = s
            best_delta = delta
    return best


def _dedupe_sessions_by_api_id(store):
    sessions = store.get("sessions", [])
    by_api_id = {}
    removed = 0

    def score(s):
        return (
            4 if _has_result_files(s) else 0,
            2 if s.get("video_path") else 0,
            1 if not str(s.get("session_id", "")).startswith("remote_") else 0,
        )

    for s in sessions:
        api_sid = s.get("api_session_id")
        if not api_sid:
            continue
        current = by_api_id.get(api_sid)
        if current is None or score(s) > score(current):
            by_api_id[api_sid] = s

    kept = []
    for s in sessions:
        api_sid = s.get("api_session_id")
        if api_sid and by_api_id.get(api_sid) is not s:
            winner = by_api_id[api_sid]
            if not winner.get("video_path") and s.get("video_path"):
                winner["video_path"] = s["video_path"]
            removed += 1
            continue
        kept.append(s)

    store["sessions"] = kept
    return removed


def _download_results(api_sid, session_id):
    from sender.opencap_client import _token, BASE

    token = _token()
    headers = {"Authorization": f"Token {token}"}
    store = read_sessions()
    session = _find_session(store, session_id)
    if not session:
        return

    result_dir = _result_dir_for_session(session)
    result_dir.mkdir(parents=True, exist_ok=True)
    if _has_result_files(session):
        update_session(session_id, {
            "status": "done",
            "download_status": "done",
            "result_dir": str(result_dir),
            "note": "Local result files detected",
        })
        return

    try:
        r = requests.get(f"{BASE}/sessions/{api_sid}/async-download/",
                         headers=headers, timeout=20)
        r.raise_for_status()
        task_id = r.json()["task_id"]

        url = None
        for _ in range(60):
            r = requests.get(f"{BASE}/logs/{task_id}/on-ready/",
                             headers=headers, timeout=20)
            if r.text.strip():
                data = r.json()
                url = data.get("url") or data.get("media")
                if url:
                    break
            time.sleep(5)

        if not url:
            raise RuntimeError("OpenCap async-download did not return a download URL")

        r = requests.get(url, timeout=120)
        r.raise_for_status()
        zip_path = result_dir / "result.zip"
        zip_path.write_bytes(r.content)
        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(result_dir)
        zip_path.unlink(missing_ok=True)
        update_session(session_id, {
            "status": "done",
            "download_status": "done",
            "result_dir": str(result_dir),
            "note": "Synced from OpenCap and downloaded results",
        })
    except Exception as e:
        store = read_sessions()
        session = _find_session(store, session_id)
        if session and _has_result_files(session):
            update_session(session_id, {
                "status": "done",
                "download_status": "done",
                "result_dir": str(_result_dir_for_session(session)),
                "note": "Local result files detected",
            })
            return
        update_session(session_id, {
            "download_status": "failed",
            "note": f"Result download failed: {str(e)[:160]}",
        })


def _remote_with_details(headers, rs):
    from sender.opencap_client import BASE

    if (rs.get("trials") or []) or not rs.get("trials_count"):
        return rs

    try:
        api_sid = rs.get("id")
        r = requests.get(f"{BASE}/sessions/{api_sid}/", headers=headers, timeout=20)
        r.raise_for_status()
        detailed = r.json()
        merged = dict(rs)
        merged.update(detailed)
        return merged
    except Exception:
        return rs


def _sync_remote_sessions(download_missing=True):
    from sender.opencap_client import _token, BASE

    token = _token()
    headers = {"Authorization": f"Token {token}"}
    r = requests.get(f"{BASE}/sessions/valid/", headers=headers, timeout=20)
    r.raise_for_status()
    remote_sessions = r.json()

    store = read_sessions()
    restored_uploads = _restore_orphan_uploads(store)
    by_api_id = {
        s.get("api_session_id"): s
        for s in store.get("sessions", [])
        if s.get("api_session_id")
    }
    by_session_id = {
        s.get("session_id"): s
        for s in store.get("sessions", [])
        if s.get("session_id")
    }

    added = 0
    updated = 0
    matched = 0
    fetched_details = 0
    used_local_ids = set()

    for rs in remote_sessions:
        before_detail_has_trials = bool(rs.get("trials"))
        rs = _remote_with_details(headers, rs)
        if not before_detail_has_trials and rs.get("trials"):
            fetched_details += 1

        api_sid = rs.get("id")
        if not api_sid:
            continue

        session = by_api_id.get(api_sid)
        if not session:
            remote_sid = "remote_" + api_sid[:8]
            session = by_session_id.get(remote_sid)

        if not session:
            session = _matching_local_without_api(store, rs, used_local_ids)
            if session:
                matched += 1
                used_local_ids.add(session["session_id"])

        if not session:
            base_sid = "remote_" + api_sid[:8]
            remote_sid = base_sid
            n = 2
            while remote_sid in by_session_id:
                remote_sid = f"{base_sid}_{n}"
                n += 1
            session = {
                "session_id": remote_sid,
                "video_path": "",
                "result_dir": str(SESSIONS / remote_sid),
                "created_at": _remote_created_at(rs) or datetime.now().isoformat(),
                "note": "Pulled from OpenCap",
            }
            store.setdefault("sessions", []).append(session)
            by_session_id[remote_sid] = session
            added += 1

        updates = {
            "name": _remote_name(rs),
            "status": _remote_status(rs),
            "api_session_id": api_sid,
            "created_at": _remote_created_at(rs) or session.get("created_at", ""),
            "remote_trial_status": (
                (rs.get("trials") or [{}])[0].get("status")
                if rs.get("trials") else rs.get("status", "")
            ),
        }

        local_match = _matching_local_without_api(store, rs, used_local_ids)
        if local_match and local_match is not session:
            local_match.update(updates)
            local_match.setdefault("video_path", "")
            local_match.setdefault("result_dir", str(SESSIONS / local_match["session_id"]))
            local_match.setdefault("note", "Merged with OpenCap record")
            used_local_ids.add(local_match["session_id"])
            matched += 1

        before = dict(session)
        session.update(updates)
        session.setdefault("video_path", "")
        session.setdefault("result_dir", str(SESSIONS / session["session_id"]))
        session.setdefault("note", "Pulled from OpenCap")
        by_api_id[api_sid] = session
        if before != session:
            updated += 1

    removed_duplicates = _dedupe_sessions_by_api_id(store)
    repaired_results = _repair_local_result_statuses(store)
    write_sessions(store)

    downloading = 0
    if download_missing:
        for s in read_sessions().get("sessions", []):
            if s.get("api_session_id") and s.get("status") == "done":
                if _has_result_files(s):
                    if s.get("download_status") != "done":
                        update_session(s["session_id"], {
                            "download_status": "done",
                            "result_dir": str(_result_dir_for_session(s)),
                            "note": "Local result files detected",
                        })
                        repaired_results += 1
                    continue
                if s.get("download_status") != "downloading":
                    update_session(s["session_id"], {
                        "download_status": "downloading",
                        "note": "Downloading OpenCap results",
                    })
                    threading.Thread(
                        target=_download_results,
                        args=(s["api_session_id"], s["session_id"]),
                        daemon=True,
                    ).start()
                    downloading += 1

    return {
        "added": added,
        "updated": updated,
        "matched": matched,
        "fetched_details": fetched_details,
        "removed_duplicates": removed_duplicates,
        "restored_uploads": restored_uploads,
        "repaired_results": repaired_results,
        "downloading": downloading,
        "total": len(read_sessions().get("sessions", [])),
    }


# ============================================================
# Page
# ============================================================

@app.get("/")
def index():
    return FileResponse(str(STATIC / "index.html"))


# ============================================================
# Upload video
# ============================================================

@app.post("/videos/upload")
def upload_video(file: UploadFile = File(...)):
    session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    video_dir = VIDEOS / session_id
    video_dir.mkdir(parents=True, exist_ok=True)

    video_path = video_dir / "input.mp4"
    with open(video_path, "wb") as f:
        shutil.copyfileobj(file.file, f)

    add_session({
        "session_id": session_id,
        "name": file.filename or "unknown",
        "video_path": str(video_path),
        "result_dir": str(SESSIONS / session_id),
        "status": "uploaded",
        "created_at": datetime.now().isoformat(),
        "note": "",
    })

    return {"session_id": session_id}


# ============================================================
# Call OpenCap
# ============================================================

@app.delete("/sessions/{session_id}")
def delete_session(session_id: str):
    import shutil
    from sender.opencap_client import _token, BASE

    # If the session has an api_session_id, delete the remote OpenCap record too.
    store = read_sessions()
    session_record = None
    for s in store["sessions"]:
        if s["session_id"] == session_id:
            session_record = s
            break

    if session_record and session_record.get("api_session_id"):
        try:
            token = _token()
            api_sid = session_record["api_session_id"]
            headers = {"Authorization": f"Token {token}"}
            requests.post(f"{BASE}/sessions/{api_sid}/trash/", headers=headers)
        except Exception:
            pass  # Remote deletion failure should not block local deletion.

    # Delete local data.
    session_dir = SESSIONS / session_id
    if session_dir.exists():
        shutil.rmtree(session_dir)
    video_dir = VIDEOS / session_id
    if video_dir.exists():
        shutil.rmtree(video_dir)

    store["sessions"] = [s for s in store["sessions"] if s["session_id"] != session_id]
    write_sessions(store)

    active = read_active()
    if active.get("session_id") == session_id:
        write_active({"session_id": "", "file_path": "", "file_type": "",
                       "send_mode": "marker", "receiver_host": active.get("receiver_host", ""),
                       "receiver_port": active.get("receiver_port", 5005)})

    return {"deleted": session_id}


@app.post("/sessions/{session_id}/sync-status")
def sync_status(session_id: str):
    """Sync one session's status from OpenCap."""
    from sender.opencap_client import _token, BASE

    store = read_sessions()
    session_record = None
    for s in store["sessions"]:
        if s["session_id"] == session_id:
            session_record = s
            break

    if not session_record or not session_record.get("api_session_id"):
        return {"status": session_record["status"] if session_record else "unknown"}

    try:
        token = _token()
        api_sid = session_record["api_session_id"]
        headers = {"Authorization": f"Token {token}"}
        r = requests.get(f"{BASE}/sessions/{api_sid}/", headers=headers, timeout=20)
        r.raise_for_status()
        data = r.json()
        status = _remote_status(data)
        updates = {
            "name": _remote_name(data),
            "status": status,
            "created_at": _remote_created_at(data) or session_record.get("created_at", ""),
        }
        update_session(session_id, updates)
        current = {**session_record, **updates}
        if status == "done":
            if _has_result_files(current):
                update_session(session_id, {
                    "download_status": "done",
                    "result_dir": str(_result_dir_for_session(current)),
                    "note": "Local result files detected",
                })
            else:
                update_session(session_id, {
                    "download_status": "downloading",
                    "note": "Downloading OpenCap results",
                })
                threading.Thread(
                    target=_download_results,
                    args=(api_sid, session_id),
                    daemon=True,
                ).start()
        return {"status": status}
    except Exception:
        pass

    return {"status": session_record.get("status", "unknown")}


@app.get("/sessions/debug-remote")
def debug_remote():
    """Debug endpoint: return raw OpenCap data."""
    from sender.opencap_client import _token, BASE
    token = _token()
    headers = {"Authorization": f"Token {token}"}
    r = requests.get(f"{BASE}/sessions/", headers=headers, timeout=15)
    data = r.json()
    # Return only a summary.
    sessions = []
    for s in data[:10]:
        trials = s.get("trials", [])
        sessions.append({
            "id": s["id"][:20],
            "isMono": s.get("isMono"),
            "created_at": s.get("created_at", "")[:19],
            "trial_count": len(trials),
            "trial_status": trials[0]["status"] if trials else "none",
        })
    return {"total": len(data), "first_10": sessions}


@app.post("/sessions/pull-remote")
def pull_remote():
    """Pull all sessions from OpenCap and auto-download missing local results."""
    return _sync_remote_sessions(download_missing=True)


@app.post("/sessions/sync-all")
def sync_all():
    """Refresh all session statuses from OpenCap."""
    return _sync_remote_sessions(download_missing=True)


@app.post("/sessions/{session_id}/process-opencap")
def process_opencap(session_id: str):
    video_path = VIDEOS / session_id / "input.mp4"
    if not video_path.exists():
        return JSONResponse({"error": f"Video file not found: {video_path}"}, 404)

    update_session(session_id, {"status": "processing", "note": "Submitted to OpenCap API"})

    def _run():
        from sender.opencap_client import process_session
        try:
            def _save_api_session_id(api_sid):
                update_session(session_id, {"api_session_id": api_sid})

            api_sid = process_session(
                session_id,
                on_api_session_created=_save_api_session_id,
            )
            update_session(session_id, {"status": "done", "api_session_id": api_sid})
        except Exception as e:
            update_session(session_id, {"status": "failed", "note": str(e)[:200]})

    threading.Thread(target=_run, daemon=True).start()
    return {"session_id": session_id, "status": "processing"}


# ============================================================
# List sessions
# ============================================================

@app.get("/sessions")
def list_sessions():
    store = read_sessions()
    changed = _restore_orphan_uploads(store)
    changed += _repair_local_result_statuses(store)
    if changed:
        write_sessions(store)
    return store


@app.get("/sessions/remote")
def list_remote_sessions():
    """Pull all sessions from OpenCap."""
    from sender.opencap_client import _token
    token = _token()
    r = requests.get(f"https://api.opencap.ai/sessions/",
                     headers={"Authorization": f"Token {token}"})
    return r.json()


# ============================================================
# View session files
# ============================================================

@app.get("/sessions/{session_id}/files")
def session_files(session_id: str):
    session = _find_session(read_sessions(), session_id)
    result_dir = _result_dir_for_session(session) if session else SESSIONS / session_id
    if not result_dir.exists():
        return JSONResponse({"error": "Session not found"}, 404)

    files = []
    for f in result_dir.rglob("*"):
        if f.is_dir():
            continue
        if f.suffix.lower() in RESULT_EXTENSIONS:
            files.append({
                "file_name": f.name,
                "file_path": str(f),
                "file_type": f.suffix[1:],
            })

    if session and files:
        updates = {}
        if session.get("status") != "done":
            updates["status"] = "done"
        if session.get("download_status") != "done":
            updates["download_status"] = "done"
            updates["note"] = "Local result files detected"
        if session.get("result_dir") != str(result_dir):
            updates["result_dir"] = str(result_dir)
        if updates:
            update_session(session_id, updates)

    return {"session_id": session_id, "files": sorted(files, key=lambda x: x["file_name"])}


# ============================================================
# Set / get active_file
# ============================================================

@app.get("/active-file")
def get_active():
    return read_active()


@app.post("/active-file")
def set_active(config: dict):
    write_active(config)
    return config


# ============================================================
# Send active file
# ============================================================

@app.post("/send-active-file")
def send_active():
    global send_thread

    config = read_active()
    host = config.get("receiver_host", "127.0.0.1")
    trc_port = int(config.get("receiver_port", 5005))
    mot_port = int(config.get("receiver_port_mot", 5006))
    trc_path = config.get("file_path", "")
    mot_path = config.get("file_path_so", "")

    if not trc_path and not mot_path:
        return JSONResponse({"error": "No IK or SO file is selected"}, 400)

    # Check file existence before sending.
    if trc_path and not Path(trc_path).exists():
        return {"ok": False, "error": f"TRC file not found: {trc_path}"}
    if mot_path and not Path(mot_path).exists():
        return {"ok": False, "error": f"MOT file not found: {mot_path}"}

    item = {
        "id": str(uuid.uuid4())[:8],
        "trc": trc_path,
        "mot": mot_path,
        "host": host,
        "trc_port": trc_port,
        "mot_port": mot_port,
        "status": "pending",
        "error": "",
    }
    send_queue.append(item)

    if send_thread is None or not send_thread.is_alive():
        send_thread = threading.Thread(target=_process_queue, daemon=True)
        send_thread.start()

    return {"queued": True, "id": item["id"]}


def _process_queue():
    global send_results
    while send_queue:
        item = send_queue[0]
        try:
            item["status"] = "sending"
            print("[send] host =", item["host"])
            print("[send] trc_port =", item["trc_port"])
            print("[send] mot_port =", item["mot_port"])
            print("[send] trc_path =", item["trc"])
            print("[send] mot_path =", item["mot"])

            send_session(item["trc"], item["mot"], item["host"],
                        item["trc_port"], item["mot_port"])
            item["status"] = "done"
            if item["trc"]:
                print("[send] TRC sent")
            if item["mot"]:
                print("[send] MOT sent")
        except Exception as e:
            item["status"] = "failed"
            item["error"] = str(e)
            print("[send] failed:", e)
        send_queue.pop(0)
        send_results.append(dict(item))
        if len(send_results) > MAX_RESULTS:
            send_results.pop(0)
        time.sleep(3)


@app.get("/send-queue")
def queue_status():
    return {
        "items": send_queue,
        "results": send_results,
        "sending": send_thread is not None and send_thread.is_alive(),
    }


@app.delete("/send-queue/{item_id}")
def remove_from_queue(item_id: str):
    for i, item in enumerate(send_queue):
        if item["id"] == item_id:
            send_queue.pop(i)
            return {"removed": item_id}
    return JSONResponse({"error": "not found"}, 404)
