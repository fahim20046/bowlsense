"""Build the release-detector training set from the annotated archive.

For every annotated 'bowl release' event: take frames [release-90, release+45], run the same MediaPipe crop
pose used by the app on the ANNOTATED bowler box (clean labels; other annotated people greyed out), and save
img/world landmarks + metadata to training/data/<video>_<frame>.npz.

Run from backend/:  .venv\\Scripts\\python -m training.extract_release_data
Resumable: deliveries already extracted are skipped.
"""
import csv
import glob
import json
import os
import sys
import time
from pathlib import Path

import cv2
import mediapipe as mp
import numpy as np
from mediapipe.tasks.python import BaseOptions, vision

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
from app.modules.pose_estimator import _crop, ensure_model  # noqa: E402
from app.modules.person_tracker import is_repeat  # noqa: E402

ARCHIVE = ROOT / "archive"
OUT = Path(__file__).resolve().parent / "data"
BEFORE, AFTER = 90, 45
VIEW = {"away from camera": "rear", "towards camera": "front_on", "right-to-left": "side_on", "left-to-right": "side_on"}


def deliveries():
    split = {r["video_name"]: r["set_name"] for r in csv.DictReader(open(ARCHIVE / "data_split.csv"))}
    for jf in sorted(glob.glob(str(ARCHIVE / "data" / "*.json"))):
        name = Path(jf).stem
        d = json.load(open(jf))
        for fr, lst in d["event"].items():
            for e in lst:
                if e["event"] != "bowl release" or e["bowler_hand"] not in ("right-handed", "left-handed"):
                    continue
                sc = (d["scene"].get(fr) or [{}])[0]
                yield dict(video=name, release=int(fr), split=split.get(name, "train"),
                           arm="right" if e["bowler_hand"].startswith("right") else "left",
                           view=VIEW.get(sc.get("bowl_direction"), "rear"),
                           bowling_type=e.get("bowling_type", ""), persons=d["person"])


def gt_boxes(persons, f0, f1):
    """Annotated bowler box per frame (interpolated over short gaps) + other people's boxes."""
    bowler, others = {}, {}
    for f in range(f0, f1):
        ppl = persons.get(str(f), [])
        b = [p["box"][:4] for p in ppl if p["role"] == "bowler"]
        if b:
            bowler[f] = b[0]
        others[f] = [p["box"][:4] for p in ppl if p["role"] != "bowler"]
    fs = sorted(bowler)
    for a, c in zip(fs, fs[1:]):
        if 1 < c - a <= 8:
            for f in range(a + 1, c):
                w = (f - a) / (c - a)
                bowler[f] = list((1 - w) * np.array(bowler[a]) + w * np.array(bowler[c]))
    return bowler, others


def main():
    OUT.mkdir(exist_ok=True)
    opts = vision.PoseLandmarkerOptions(base_options=BaseOptions(model_asset_path=str(ensure_model())),
                                        running_mode=vision.RunningMode.IMAGE, num_poses=1,
                                        min_pose_detection_confidence=0.3, min_pose_presence_confidence=0.3)
    items = list(deliveries())
    print(f"{len(items)} annotated deliveries", flush=True)
    t0 = time.time()
    with vision.PoseLandmarker.create_from_options(opts) as lmk:
        for i, it in enumerate(items):
            out = OUT / f"{it['video']}_{it['release']}.npz"
            if out.exists():
                continue
            f0 = max(0, it["release"] - BEFORE)
            f1 = it["release"] + AFTER + 1
            bowler, others = gt_boxes(it["persons"], f0, f1)
            cap = cv2.VideoCapture(str(ARCHIVE / "videos" / f"{it['video']}.mp4"))
            fps = cap.get(cv2.CAP_PROP_FPS)
            cap.set(cv2.CAP_PROP_POS_FRAMES, f0)
            n = f1 - f0
            img, world = np.full((n, 33, 3), np.nan), np.full((n, 33, 3), np.nan)
            height = int(cap.get(4))
            prev = None
            for j in range(n):
                ok, frame = cap.read()
                if not ok:
                    break
                small = cv2.cvtColor(cv2.resize(frame, (160, 90)), cv2.COLOR_BGR2GRAY)
                if prev is not None and j > 0 and is_repeat(prev, small):
                    img[j], world[j] = img[j - 1], world[j - 1]
                    prev = small
                    continue
                prev = small
                f = f0 + j
                if f not in bowler:
                    continue
                crop, X0, Y0, s = _crop(frame, bowler[f], others.get(f, []))
                res = lmk.detect(mp.Image(image_format=mp.ImageFormat.SRGB, data=cv2.cvtColor(crop, cv2.COLOR_BGR2RGB)))
                if res.pose_landmarks:
                    img[j] = [[X0 + p.x * s, Y0 + p.y * s, p.visibility] for p in res.pose_landmarks[0]]
                    world[j] = [[p.x, p.y, p.z] for p in res.pose_world_landmarks[0]]
            cap.release()
            img[..., 2] = np.nan_to_num(img[..., 2], nan=0.0)
            np.savez_compressed(out, img=img, world=world, release_idx=it["release"] - f0, fps=fps, height=height,
                                arm=it["arm"], view=it["view"], split=it["split"], bowling_type=it["bowling_type"])
            done = i + 1
            eta = (time.time() - t0) / max(1, sum(1 for _ in OUT.glob("*.npz"))) * (len(items) - done)
            print(f"[{done}/{len(items)}] {out.name} tracked {np.isfinite(img[:, 0, 0]).mean():.2f}  eta {eta / 60:.0f} min", flush=True)


if __name__ == "__main__":
    main()
