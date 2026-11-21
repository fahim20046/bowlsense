# BowlSense AI – Cricket Bowling Intelligence System

Upload a bowling video → pose tracking, 7 delivery phases, biomechanics, elbow-legality screening,
injury-stress screening, ball speed, technique score and coaching. Design: `DESIGN.md`. Status: `progress.md`.

## Requirements
- Python 3.11+ (tested on 3.14, Windows 11)
- Node.js 20+ (tested on Node LTS)
- ~2 GB disk (PyTorch CPU + models)

## 1. Backend setup (run from `backend/`)
```
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python -m pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu
.venv\Scripts\python -m pip install --no-deps ultralytics
.venv\Scripts\python -m pip install matplotlib pyyaml requests pillow psutil polars ultralytics-thop lap
```
Why the extra steps: `ultralytics` normally pulls `opencv-python`, which overwrites the `opencv-python-headless`
used here and breaks `cv2`. Install it with `--no-deps`, then its other dependencies separately.
On macOS/Linux use `.venv/bin/python` instead of `.venv\Scripts\python`.

Check the install:
```
.venv\Scripts\python -c "import cv2, mediapipe, torch, ultralytics; print('ok')"
```

Models download automatically on the first analysis into `backend/models/`:
`pose_landmarker_heavy.task` (MediaPipe) and `yolo11n.pt` (Ultralytics).

## 2. Run the backend
```
.venv\Scripts\python -m uvicorn app.main:app --port 8000
```
Restart it after changing backend code (`--reload` stalls on Windows with the background worker).
API docs: http://127.0.0.1:8000/docs

## 3. Frontend (run from `frontend/`)
```
npm install
npm run dev
```
Open http://localhost:5173 (proxies `/api` to port 8000).

## 4. Tests (run from `backend/`)
```
.venv\Scripts\python -m pytest -q app/tests
```

## Recording tips (best results)
- **Side-on** camera, perpendicular to the pitch, on a tripod (static).
- One bowler in frame, full body visible, good light.
- Phone slow-motion **120–240 fps**; 30 fps blurs the release.
- For ball speed: in the Speed tab, click both popping creases (17.68 m apart) to calibrate.
- Other people in frame: click the bowler on the upload preview.
- Handheld/moving camera: check BFC/FFC markers in Video Studio and correct them if needed.

## Data
- `storage/` – SQLite DB + per-session files (created automatically; safe to delete to reset).
- `samples/` – test clips (archive cuts + Pexels free-license clip).
- `archive/` – broadcast dataset with annotations (used for validation only).
