# open-campus-demo-v3

Monocular motion capture pipeline: upload video → OpenCap cloud API → real-time IK visualization.
test
## Requirements

- Python 3.8+
- OpenSim 4.5 (`conda install -c opensim-org opensim=4.5`)
- simbody-visualizer in PATH (platform-specific)

## Project Structure

```
├── sender/                        # Sender side (Linux)
│   ├── opencap_monocular_demo.py  # Upload video → download .trc/.mot/.osim
│   ├── send_to_mac.py             # Parse .trc → send marker frames over TCP
│   ├── video/                     # Input video files
│   │   └── single_leg_hop_turn_around_walk_scaled.mp4
│   └── outputs/                   # Downloaded OpenCap session results
├── receiver/                      # Receiver side (Windows)
│   ├── receive_and_play.py        # TCP listen → IK solve → visualize
│   ├── marker_receiver.py         # TCP server class
│   ├── marker_packet.py           # Data packet dataclass
│   ├── opensim_marker_reference1.py  # OpenSim MarkersReference builder
│   ├── config.py                  # Receiver configuration
│   └── received_data/             # Pre-downloaded OpenSim model
│       └── OpenSimData/
│           ├── model.osim
│           └── Geometry/
└── .gitignore
```

## Usage

### Full Pipeline

**Sender (this machine):**
```bash
cd sender
python send_to_mac.py --full    # Runs API demo + sends marker data
```

**Receiver (Windows machine):**
```bash
cd receiver
python receive_and_play.py    # Listens on 0.0.0.0:5005
```

### Sender-only

```bash
# Just get OpenCap results (no TCP send)
cd sender
python opencap_monocular_demo.py

# Send existing results
cd sender
python send_to_mac.py          # Auto-finds latest .trc in outputs/
python send_to_mac.py path/to/file.trc
```

### Receiver-only

```bash
cd receiver
python receive_and_play.py                        # Default: 0.0.0.0:5005
python receive_and_play.py 100.111.140.103        # Specify sender IP
python receive_and_play.py 0.0.0.0 5005           # Specify host and port
python receive_and_play.py --keep-open            # Keep window open after playback
```
