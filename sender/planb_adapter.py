"""Isolated subprocess adapter for the local OpenCap Monocular Plan B pipeline."""

import os
import subprocess
import time
from pathlib import Path


PLANB_ROOT = Path("/home/zhr/opencap/opencap-monocular-planb")
PLANB_RUNNER = PLANB_ROOT / "run_planb.sh"
PLANB_VALIDATOR = PLANB_ROOT / "src" / "opencap-monocular" / "validate_trc_mot.py"
CONDA = Path("/home/zhr/anaconda3/bin/conda")
CONDA_ENV = "opencap-mono-planb"
DEFAULT_DEVICE_MODEL = "iPhone14,5"


def planb_parameters():
    """Reuse the sender's existing subject defaults and keep the camera default central."""
    from sender.opencap_client import SUBJECT_HEIGHT, SUBJECT_MASS, SUBJECT_SEX
    return {
        "height_m": float(SUBJECT_HEIGHT),
        "mass_kg": float(SUBJECT_MASS),
        "sex": str(SUBJECT_SEX),
        "device_model": DEFAULT_DEVICE_MODEL,
    }


def _require_file(path: Path, label: str):
    if not path.is_file() or path.stat().st_size == 0:
        raise FileNotFoundError(f"{label} is missing or empty: {path}")


def validate_trc_mot(trc_path, mot_path, env=None):
    """Run Plan B's validator with explicit paths; never search for result files."""
    trc = Path(trc_path).resolve()
    mot = Path(mot_path).resolve()
    _require_file(trc, "TRC")
    _require_file(mot, "MOT")
    _require_file(PLANB_VALIDATOR, "Plan B validator")
    _require_file(CONDA, "Conda executable")
    validation = subprocess.run(
        [
            str(CONDA), "run", "-n", CONDA_ENV, "python", str(PLANB_VALIDATOR),
            "--trc", str(trc), "--mot", str(mot),
        ],
        cwd=str(PLANB_ROOT), env=env, capture_output=True, text=True, check=False,
    )
    result = {
        "validation_exit_code": validation.returncode,
        "validation_stdout": validation.stdout,
        "validation_stderr": validation.stderr,
    }
    if validation.returncode != 0 or "VALIDATION=PASS" not in validation.stdout:
        raise RuntimeError("TRC/MOT validation failed", result)
    return result


def run_planb(video_path, task_dir, on_started=None):
    """Run and validate Plan B for one already-saved, uniquely-owned video.

    `task_dir` belongs to one sender session.  Its `planb_output` directory is passed
    to the Plan B runner, so identical upload names cannot share any Plan B output.
    """
    video = Path(video_path).resolve()
    task = Path(task_dir).resolve()
    _require_file(video, "Plan B input video")
    _require_file(PLANB_RUNNER, "Plan B runner")
    _require_file(PLANB_VALIDATOR, "Plan B validator")
    _require_file(CONDA, "Conda executable")

    output_root = task / "planb_output"
    output_root.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    env["PLANB_OUTPUT_DIR"] = str(output_root)
    parameters = planb_parameters()
    env["PLANB_HEIGHT_M"] = str(parameters["height_m"])
    env["PLANB_MASS_KG"] = str(parameters["mass_kg"])
    env["PLANB_SEX"] = parameters["sex"]
    env["PLANB_DEVICE_MODEL"] = parameters["device_model"]
    started_at = time.time()
    process = subprocess.Popen(
        ["bash", str(PLANB_RUNNER), str(video)],
        cwd=str(PLANB_ROOT),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    if on_started:
        on_started(process.pid, output_root)
    stdout, stderr = process.communicate()
    finished_at = time.time()

    trc = output_root / video.stem / f"{video.stem}.trc"
    mot = output_root / video.stem / f"{video.stem}.mot"
    result = {
        "started_at": started_at,
        "finished_at": finished_at,
        "duration_seconds": round(finished_at - started_at, 3),
        "pid": process.pid,
        "exit_code": process.returncode,
        "log_path": str(task / "planb_process.log"),
        "output_root": str(output_root),
        "trc_path": str(trc),
        "mot_path": str(mot),
        "parameters": parameters,
    }
    Path(result["log_path"]).write_text(
        "[stdout]\n" + stdout + "\n[stderr]\n" + stderr,
        encoding="utf-8",
    )
    if process.returncode != 0:
        raise RuntimeError(f"Plan B runner exited {process.returncode}", result)
    _require_file(trc, "Plan B TRC")
    _require_file(mot, "Plan B IK MOT")

    try:
        result.update(validate_trc_mot(trc, mot, env))
    except RuntimeError as exc:
        result.update(exc.args[1])
        raise RuntimeError("Plan B TRC/MOT validation failed", result) from exc
    return result
