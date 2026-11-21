"""Train + evaluate the release-frame detector on the extracted archive deliveries.

Split by VIDEO (archive/data_split.csv): train -> fit, val -> choose settings, test -> final report.
Compares the trained model with the rule-based detector (phase_detector.detect_br) on identical pose data.
Saves backend/models/release_model.joblib and training/release_metrics.json.

Run from backend/:  .venv\\Scripts\\python -m training.train_release_model
"""
import json
import sys
import warnings
from pathlib import Path

import joblib
import numpy as np
from sklearn.ensemble import HistGradientBoostingClassifier

warnings.filterwarnings("ignore")
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
from app.ml.features import frame_features  # noqa: E402
from app.ml.release_model import MODEL_PATH  # noqa: E402
from app.modules import kinematics as K, phase_detector as P  # noqa: E402

DATA = Path(__file__).resolve().parent / "data"
POS_RADIUS = 1          # frames within ±1 of the annotated release are positives


def load():
    items = []
    for f in sorted(DATA.glob("*.npz")):
        z = np.load(f, allow_pickle=True)
        img = z["img"]
        if np.isfinite(img[:, 0, 0]).mean() < 0.2:               # bowler barely visible -> unusable
            continue
        k = K.build(img, z["world"], float(z["fps"]), int(z["height"]), str(z["arm"]), str(z["view"]))
        X, names = frame_features(k)
        rel = int(z["release_idx"])
        y = (np.abs(np.arange(len(X)) - rel) <= POS_RADIUS).astype(int)
        items.append(dict(name=f.stem, split=str(z["split"]), k=k, X=X, y=y, rel=rel, fps=float(z["fps"]),
                          view=str(z["view"]), names=names))
    return items


def predict_frame(model, it):
    p = model.predict_proba(it["X"])[:, 1]
    p[~np.isfinite(it["k"].P[:, 23, 0])] = 0
    p = np.convolve(p, np.ones(3) / 3, mode="same")
    return int(np.argmax(p))


def summarize(errs):
    e = np.abs(np.array([x for x in errs if x is not None], float))
    n_total = len(errs)
    if not len(e):
        return {"found": 0, "n": n_total}
    return {"n": n_total, "found": int(len(e)), "median_abs_err_frames": float(np.median(e)),
            "within_2": float(np.mean(e <= 2) * len(e) / n_total), "within_3": float(np.mean(e <= 3) * len(e) / n_total),
            "within_6": float(np.mean(e <= 6) * len(e) / n_total)}


def main():
    items = load()
    by = {s: [it for it in items if it["split"] == s] for s in ("train", "val", "test")}
    print({s: len(v) for s, v in by.items()}, "deliveries usable")
    Xtr = np.vstack([it["X"] for it in by["train"]]); ytr = np.concatenate([it["y"] for it in by["train"]])

    best, best_score = None, None
    for lr, leaf in [(0.05, 20), (0.1, 20), (0.05, 40)]:
        m = HistGradientBoostingClassifier(learning_rate=lr, max_iter=300, min_samples_leaf=leaf,
                                           class_weight="balanced", random_state=0)
        m.fit(Xtr, ytr)
        val_err = [abs(predict_frame(m, it) - it["rel"]) for it in by["val"]]
        sc = float(np.median(val_err)) if val_err else 0.0
        print(f"lr={lr} leaf={leaf}: val median |err| = {sc} frames")
        if best_score is None or sc < best_score:
            best, best_score = m, sc

    # final model: refit on train+val with the chosen settings, report on untouched test
    final = HistGradientBoostingClassifier(**{k: v for k, v in best.get_params().items()})
    trv = by["train"] + by["val"]
    final.fit(np.vstack([it["X"] for it in trv]), np.concatenate([it["y"] for it in trv]))

    ml_err, rule_err, rows = [], [], []
    for it in by["test"]:
        e_ml = predict_frame(final, it) - it["rel"]
        br_rule = P.detect_br_rule(it["k"])
        e_rule = None if br_rule is None else br_rule - it["rel"]
        ml_err.append(e_ml); rule_err.append(e_rule)
        rows.append((it["name"], it["view"], e_ml, e_rule))
    metrics = {"test_deliveries": len(by["test"]), "train_val_deliveries": len(trv),
               "trained_model": summarize(ml_err), "rule_based": summarize(rule_err),
               "positive_radius_frames": POS_RADIUS, "settings": {k: best.get_params()[k] for k in ("learning_rate", "min_samples_leaf")}}
    print(json.dumps(metrics, indent=2))
    for r in rows:
        print("  %-34s %-8s ML err %+4d   rule err %s" % (r[0], r[1], r[2], r[3]))
    MODEL_PATH.parent.mkdir(exist_ok=True)
    joblib.dump(final, MODEL_PATH)
    (Path(__file__).resolve().parent / "release_metrics.json").write_text(json.dumps(metrics, indent=2))
    print("saved", MODEL_PATH)


if __name__ == "__main__":
    main()
