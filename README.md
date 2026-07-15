# open-campus-demo-v3

OpenCap + OpenSim real-time demo. The project provides a small web backend for
uploading monocular videos to OpenCap, downloading the generated OpenSim
results, and sending `.trc` / `.mot` files to a Windows OpenSim receiver for
visual playback.

## What This Project Does

1. Upload a `.mp4` or `.mov` video from the browser.
2. Submit the video to the OpenCap cloud API for monocular processing.
3. Download generated OpenSim results, including marker `.trc`, motion `.mot`,
   and model `.osim` files.
4. Send selected result files over TCP:
   - `.trc` to the IK receiver on port `5005`
   - `.mot` to the Static Optimization receiver on port `5006`
5. Play the received data in Simbody Visualizer through OpenSim.

## Root Files

```text
README.md                    Project deployment and usage guide
environment-opensim452.yml   Conda environment exported from opensim452
opensim.log                  Local OpenSim runtime log
```

The generated deployment environment is exported from:

```text
C:\others\software\canda\envs\opensim452
```

Use it in another project or machine with:

```powershell
conda env create -f environment-opensim452.yml
conda activate opensim452
```

If an environment with the same name already exists, choose one of these:

```powershell
conda env update -n opensim452 -f environment-opensim452.yml
```

or edit the `name:` field in `environment-opensim452.yml` before creating a new
environment.

## Project Structure

```text
sender/
  main.py              FastAPI backend and web entrypoint
  opencap_client.py    OpenCap API login, upload, processing, and download
  marker_sender.py     TCP file sender for .trc and .mot files
  json_store.py        JSON persistence for sessions and active file settings
  static/index.html    Browser management page
  data/                Local runtime data, uploads, tokens, and downloaded sessions

receiver/
  ik_receiver.py                  Receives .trc files on TCP :5005
  ik_player.py                    Runs OpenSim Inverse Kinematics playback
  so_receiver.py                  Receives .mot files on TCP :5006
  static_optimization_player.py   Runs Static Optimization and playback
  config.py                       Receiver model, geometry, IK, and SO settings
  received_data/OpenSimData/      Model and Geometry used by the receiver
  receiver_data/                  Runtime receive directory
  test_so/                        Static Optimization test data and output
```

## Environment

The exported `environment-opensim452.yml` includes the runtime packages used by
this project, including:

- Python `3.12`
- OpenSim `4.5.2`
- FastAPI / Uvicorn
- Requests
- OpenCV
- Simbody / OpenSim visualization dependencies

On Windows, make sure `simbody-visualizer.exe` is available from the active
conda environment. The receiver code attempts to add the environment `bin` and
`Library\bin` folders to `PATH` automatically.

## First-Time OpenCap Login

The sender backend uses a cached OpenCap token. Run this once in a terminal
where the project root is the current directory:

```powershell
conda activate opensim452
python -c "from sender.opencap_client import login_interactive; login_interactive()"
```

Enter the email OTP when prompted. The token is saved under `sender/data/` and
is reused by the web backend.

## Start The Sender Backend

From the project root:

```powershell
conda activate opensim452
uvicorn sender.main:app --reload --host 0.0.0.0 --port 8056
```

Open the management page in a browser:

```text
http://127.0.0.1:8056/
```

For another machine on the same network, replace `127.0.0.1` with the sender
machine IP.

## Start The Receiver

Run IK and Static Optimization receivers in separate terminals on the Windows
receiver machine.

IK receiver:

```powershell
conda activate opensim452
cd receiver
python ik_receiver.py 0.0.0.0 5005
```

Static Optimization receiver:

```powershell
conda activate opensim452
cd receiver
python so_receiver.py 0.0.0.0 5006
```

The sender UI should be configured with the receiver host/IP and the matching
ports:

- IK / TRC port: `5005`
- SO / MOT port: `5006`

## Native Desktop Demo

`receiver/demo_host.py` is the Windows desktop host for the same sender backend
and the two existing OpenSim receiver processes. Its left side is built entirely
from PySide6 widgets (there is no browser or WebView): it connects to the
FastAPI service, uploads `.mp4`/`.mov` videos, manages sessions, selects backend
reported `.trc`/`.mot` paths, saves `/active-file`, and invokes the existing
`/send-active-file` queue. The TCP protocol remains in `sender/marker_sender.py`.

Install the additional desktop package into the existing environment:

```powershell
conda activate opensim452
conda install -c conda-forge pyside6
```

`psutil` is used for exact Visualizer PID and port-owner checks and is now
declared in `environment-opensim452.yml` (it was already importable in the
current exported environment). Start the FastAPI sender first, then run:

```powershell
conda activate opensim452
python -u receiver/demo_host.py
```

Enter the full Sender Server URL, for example `http://127.0.0.1:8056`, then
click **Connect**. The toolbar switches IK/SO between side-by-side and
top-and-bottom layouts, hides the control panel, enters full screen, retries an
embedding, or restarts one receiver. Splitter positions, geometry, server URL,
ports, layout, and control visibility are stored in
`receiver/demo_host_config.json`.

At startup the host snapshots `simbody-visualizer.exe` PIDs, starts IK alone,
waits for its exact `[ik] listening on ...` receiver log, and only accepts one
new PID with one visible top-level HWND. It embeds that HWND, then repeats the
same procedure for SO after `[so] listening on ...`. It uses `EnumWindows`,
`GetWindowThreadProcessId`, `GetWindowLongPtrW`, `SetWindowLongPtrW`,
`SetParent`, `SetWindowPos`, and `ShowWindow`, with explicit 64-bit ctypes
signatures. It never kills all Python or Simbody processes; shutdown only closes
the recorded HWNDs and the `QProcess` instances it started.

The host sets Per-Monitor-V2 DPI awareness before Qt starts. Test embedded GLUT
windows at 100% and at 125%/150% display scale. Windows can impose limitations
when an embedded child and host move across monitors with different DPI modes;
keep the host and both Visualizers on one monitor if scaling artifacts appear.
If a port is already occupied, the host shows the owning PID and does not kill
it. If embedding fails, use **Retry Embed** after resolving the reported PID or
HWND ambiguity. Confirm firewall access to TCP `5005` and `5006` when the sender
runs on a different machine.

## Typical Workflow

1. Start `ik_receiver.py` and/or `so_receiver.py` on the receiver machine.
2. Start the sender backend with Uvicorn.
3. Open the browser UI.
4. Upload a video.
5. Click the OpenCap processing action for the session.
6. Refresh/sync until the session is complete and result files are downloaded.
7. Select the `.trc` and/or `.mot` result file as active.
8. Send the active file to the receiver.

## Useful API Endpoints

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/` | Browser management page |
| `POST` | `/videos/upload` | Upload a `.mp4` or `.mov` video |
| `POST` | `/sessions/{id}/process-opencap` | Submit one session to OpenCap |
| `GET` | `/sessions` | List local sessions |
| `DELETE` | `/sessions/{id}` | Delete local session and remote OpenCap record when available |
| `POST` | `/sessions/pull-remote` | Pull sessions from OpenCap and download missing results |
| `POST` | `/sessions/sync-all` | Sync all remote statuses and downloads |
| `GET` | `/sessions/{id}/files` | List result files for one session |
| `GET` / `POST` | `/active-file` | Read or update selected send target/files |
| `POST` | `/send-active-file` | Queue active `.trc` / `.mot` send |
| `GET` | `/send-queue` | Inspect pending and finished send jobs |

## Notes For Deploying To Another Project

- Copy `environment-opensim452.yml` into the target project and create/update
  the conda environment from it.
- Keep the receiver model paths in `receiver/config.py` aligned with the target
  project's `OpenSimData` location.
- Do not commit local OpenCap tokens, uploaded videos, downloaded sessions, or
  generated OpenSim output files.
- If the receiver cannot open the visualizer, confirm that OpenSim is installed
  from the same conda environment and that `simbody-visualizer.exe` is reachable.

## Troubleshooting

- No OpenCap token: run the first-time login command again.
- Sender cannot connect to receiver: check firewall, receiver IP, and ports
  `5005` / `5006`.
- Receiver opens but no model appears: verify `receiver/received_data/OpenSimData`
  contains `model.osim` and `Geometry/`.
- Static Optimization is slow: adjust `SO_STEP_INTERVAL` or `SO_MAX_FRAMES` in
  `receiver/config.py` during debugging.
