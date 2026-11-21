import numpy as np

from app.core import geometry as g
from app.ml import release_model
from app.ml.features import OFFSETS, frame_features
from app.modules.kinematics import Kin


def _kin(n=40):
    P = np.full((n, 33, 2), np.nan)
    for f in range(n):
        x = 100 + 4 * f
        P[f, [23, 24]] = [[x - 5, 100], [x + 5, 100]]
        P[f, [11, 12]] = [[x - 10, 160], [x + 10, 160]]
        P[f, [13, 14]] = [[x - 12, 130], [x + 12, 190]]
        P[f, [15, 16]] = [[x - 14, 110], [x + 14, 220 + f]]     # right wrist rising above the head
        P[f, 0] = [x, 185]
        P[f, [27, 28]] = [[x - 5, 20], [x + 5, 20]]
    vis = np.ones((n, 33))
    return Kin(P=P, vis=vis, W=np.zeros((n, 33, 3)), fps=30.0, arm="right", perspective="side_on", H=200.0,
               dx=1.0, ids=g.side("right"))


def test_feature_matrix_shape_and_context():
    X, names = frame_features(_kin())
    assert X.shape[0] == 40 and X.shape[1] == len(names)
    assert any(nm.endswith(f"@{OFFSETS[0]:+d}") for nm in names)
    i = names.index("r_wr_head")
    assert np.nanargmax(X[:, i]) == 39                         # raised wrist highest at the last frame


def test_no_model_file_falls_back(monkeypatch, tmp_path):
    release_model._load.cache_clear()
    monkeypatch.setattr(release_model, "MODEL_PATH", tmp_path / "missing.joblib")
    assert release_model.predict_release(_kin()) == (None, 0.0)
    release_model._load.cache_clear()
