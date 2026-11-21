from app.modules import coaching_engine as ce
from app.modules import performance_scorer as ps
from app.schemas import BiomechanicsReport, InjuryReport, LegalityResult, Metric


def _m(key, value, unit="deg", status="ok"):
    return Metric(key=key, label=key, value=value, unit=unit, status=status, confidence=0.9, reliability="high", frame=10)


def test_band_shapes():
    assert ps.band(-20, 0)(-10) == 0.5 and ps.band(-20, 0)(5) == 1.0
    assert ps.band(10, 3)(3) == 1.0 and ps.band(10, 3)(10) == 0.0          # lower is better
    assert ps.band(0, 30, 45, 75)(60) == 0.5


def test_score_excludes_unavailable_and_flags_partial():
    bio = BiomechanicsReport(upper_body=[], lower_body=[_m("front_knee_ffc", 175), _m("front_knee_delta", -20)],
                             posture=[_m("trunk_lean_br", None, status="unavailable_perspective")], phase_table={})
    s, subs, _ = ps.score(bio, LegalityResult())
    assert s.total is None and s.available_weight == 20          # < 40 weight available -> no total
    fl = next(c for c in s.components if c.key == "front_leg")
    assert fl.score == 50.0 and subs["trunk_lean_br"] is None


def test_low_reliability_metric_excluded():
    m = _m("release_height_br", 0.5, "ratio").model_copy(update={"reliability": "low"})
    bio = BiomechanicsReport(upper_body=[m], lower_body=[], posture=[], phase_table={})
    s, subs, _ = ps.score(bio, LegalityResult())
    assert subs["release_height_br"] is None
    assert any("excluded" in b for c in s.components for b in c.based_on)


def test_score_total_weighted():
    bio = BiomechanicsReport(upper_body=[_m("release_height_br", 1.2, "ratio")],
                             lower_body=[_m("front_knee_ffc", 175), _m("front_knee_delta", 0)],
                             posture=[_m("head_stability", 10, "pct_height")], phase_table={})
    s, _, _ = ps.score(bio, LegalityResult())
    # front_leg 100 (w20), arm 100 (w15, 1 of 3 available), head 0 (w10) -> 3500/45
    assert s.total == round(3500 / 45, 1) and s.partial


def test_coaching_prioritises_weakest_and_reports_fact():
    bio = BiomechanicsReport(upper_body=[], lower_body=[_m("front_knee_ffc", 175), _m("front_knee_delta", -18)],
                             posture=[_m("head_stability", 9, "pct_height")], phase_table={})
    _, subs, metrics = ps.score(bio, LegalityResult())
    perf = ce.coach(subs, metrics, InjuryReport())
    assert perf.insights[0].metric_key == "front_knee_delta"       # weight 10 × 0.9 shortfall beats head 10 × 0.86
    assert "-18" in perf.insights[0].fact and "frame 10" in perf.insights[0].fact
    assert perf.strengths == ["Firm front leg at front-foot contact"]
