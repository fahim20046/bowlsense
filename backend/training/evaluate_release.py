"""Evaluate release detection on the held-out TEST deliveries: rule only vs model only vs hybrid (as used by
the app: rule locates, model refines within ±0.5 s). Writes training/release_metrics.json.

Run from backend/:  .venv\\Scripts\\python -m training.evaluate_release
"""
import json
from pathlib import Path

import numpy as np

from app.ml import release_model
from app.modules import phase_detector as P
from training.train_release_model import load, summarize


def main():
    test = [it for it in load() if it["split"] == "test"]
    errs = {"rule_only": [], "model_only": [], "hybrid_app": []}
    for it in test:
        k = it["k"]
        rule = P.detect_br_rule(k)
        p = release_model.release_probabilities(k)
        errs["rule_only"].append(None if rule is None else rule - it["rel"])
        errs["model_only"].append(int(np.argmax(p)) - it["rel"])
        errs["hybrid_app"].append(None if (b := P.detect_br(k)) is None else b - it["rel"])
    out = {"test_deliveries": len(test), **{k: summarize(v) for k, v in errs.items()}}
    print(json.dumps(out, indent=2))
    (Path(__file__).resolve().parent / "release_metrics.json").write_text(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
