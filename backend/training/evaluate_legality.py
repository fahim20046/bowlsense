"""Evaluate the app's automatic legality verdict against expert labels.

Dataset: Debopom/Illegal-Bowling-Action-Detection (MIT), 36 labelled clips in samples/legality_dataset/
(bowling-result.ods: video -> legal/illegal). Each clip goes through the SAME pipeline as an upload:
person tracking + pose -> kinematics (auto camera view) -> phases/release -> legality.
Pose is cached in training/legality_cache/ so re-runs after code changes are fast (use --no-cache to redo pose).

Run from backend/:  .venv\\Scripts\\python -m training.evaluate_legality
Writes training/legality_results.json and prints a confusion matrix.
"""
import json
import os
import re
import sys
import time
import warnings
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

import numpy as np

warnings.filterwarnings("ignore")
os.environ.setdefault("GLOG_minloglevel", "3")
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
from app.modules import kinematics as K, report_generator as R, video_processor as VP  # noqa: E402
from app.modules.pose_estimator import run_pose  # noqa: E402
from app.schemas import QualityReport  # noqa: E402

DATA = ROOT / "samples" / "legality_dataset"
CACHE = Path(__file__).resolve().parent / "legality_cache"
OUT = Path(__file__).resolve().parent / "legality_results.json"


def labels() -> dict[int, str]:
    ns = {"table": "urn:oasis:names:tc:opendocument:xmlns:table:1.0", "text": "urn:oasis:names:tc:opendocument:xmlns:text:1.0"}
    root = ET.fromstring(zipfile.ZipFile(DATA / "bowling-result.ods").read("content.xml"))
    out = {}
    for row in root.iter("{%s}table-row" % ns["table"]):
        cells = [" ".join("".join(p.itertext()) for p in c.findall("text:p", ns)) for c in row.findall("table:table-cell", ns)]
        if len(cells) >= 2 and cells[0].strip().isdigit():
            out[int(cells[0])] = cells[1].strip().lower()
    return out


def analyse(i: int, use_cache: bool):
    video = DATA / f"{i}.mp4"
    CACHE.mkdir(exist_ok=True)
    cache = CACHE / f"{i}.npz"
    meta = VP.probe(video)
    if use_cache and cache.exists():
        z = np.load(cache)
        img, world = z["img"], z["world"]
    else:
        img, world, _ = run_pose(video, None, "right", None)
        np.savez_compressed(cache, img=img, world=world)
    det = ~np.isnan(img[:, 0, 0])
    q = QualityReport(score=0, resolution_ok=True, fps_ok=meta.fps >= 50, blur_variance=0, sharp_ok=True,
                      mean_visibility=float(img[det][:, :, 2].mean()) if det.any() else 0, detection_rate=float(det.mean()))
    k = K.build(img, world, meta.fps, meta.height, "right", "side_on")
    view = K.estimate_view(k)
    if view:                                           # same auto-correction as the app (no user lock here)
        k.perspective = view
    rep, _ = R.analyse(f"ds{i}", k, meta, q, {}, video)
    L = rep.legality
    return {"video": i, "view": k.perspective, "tracked": round(float(det.mean()), 2),
            "br": next(p.frame for p in rep.phases if p.name == "br"), "frames": meta.total_frames,
            "verdict": L.final_classification, "net_extension": L.net_extension, "confidence": L.confidence_level,
            "min_angle": L.min_angle, "angle_at_br": L.angle_at_br}


def main():
    use_cache = "--no-cache" not in sys.argv
    lab = labels()
    rows = []
    for i in sorted(lab):
        t = time.time()
        try:
            r = analyse(i, use_cache)
        except Exception as e:  # noqa: BLE001
            r = {"video": i, "verdict": "Error", "error": str(e)[:200]}
        r["label"] = lab[i]
        rows.append(r)
        print(f"{i:2d} {lab[i]:8s} -> {r['verdict']:11s} d={r.get('net_extension')} conf={r.get('confidence')} "
              f"view={r.get('view')} tracked={r.get('tracked')} ({time.time() - t:.0f}s)", flush=True)

    # summary: illegal = positive class
    def cnt(lbl, verdict):
        return sum(1 for r in rows if r["label"] == lbl and r["verdict"] == verdict)
    tp, fn = cnt("illegal", "Illegal"), cnt("illegal", "Legal")
    tn, fp = cnt("legal", "Legal"), cnt("legal", "Illegal")
    unav = sum(1 for r in rows if r["verdict"] not in ("Legal", "Illegal"))
    decided = tp + fn + tn + fp
    summary = {"clips": len(rows), "decided": decided, "unavailable_or_error": unav,
               "TP_illegal_caught": tp, "FN_illegal_missed": fn, "TN_legal_ok": tn, "FP_legal_flagged": fp,
               "accuracy_on_decided": round((tp + tn) / decided, 3) if decided else None,
               "illegal_recall": round(tp / (tp + fn), 3) if tp + fn else None,
               "legal_specificity": round(tn / (tn + fp), 3) if tn + fp else None}
    OUT.write_text(json.dumps({"summary": summary, "rows": rows}, indent=2))
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
