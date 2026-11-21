from app.modules import injury_screener as inj
from app.modules import legality_screener as leg
from app.schemas import BiomechanicsReport, Metric


def test_legality_classes():
    assert leg.classify(8.0, 5) == "Legal"
    assert leg.classify(14.9, 5) == "Legal"
    assert leg.classify(15.0, 5) == "Illegal"
    assert leg.classify(46.0) == "Illegal"


def test_error_margin():
    assert leg.error_margin("side_on", 0.9, 240) == 5
    assert leg.error_margin("rear", 0.6, 30) == 14


def _arm(frame, angle_deg):
    """Shoulder above elbow, wrist placed so the elbow angle is exactly angle_deg."""
    from app.schemas import ManualElbowPoint
    import math
    a = math.radians(angle_deg)
    return ManualElbowPoint(frame=frame, shoulder=(100, 0), elbow=(100, 100),
                            wrist=(100 + 100 * math.sin(a), 100 - 100 * math.cos(a)))


def test_manual_angle_and_verdicts():
    assert abs(leg.manual_angle(_arm(1, 150)) - 150) < 0.01
    # 30 fps -> margin 4 + 3 = 7: Δ = 172 − 165 = 7 -> within ±7 of 15? 7 < 8 -> no obvious concern
    ok = leg.manual_screen([_arm(10, 165), _arm(12, 168), _arm(15, 172)], "side_on", 30)
    assert ok.net_extension == 7 and ok.error_margin == 7 and ok.classification == "Legal"
    bad = leg.manual_screen([_arm(15, 175), _arm(10, 145)], "side_on", 240)       # unsorted input
    assert bad.horizontal_frame == 10 and bad.net_extension == 30 and bad.classification == "Illegal"
    rear = leg.manual_screen([_arm(10, 165), _arm(15, 170)], "rear", 240)
    assert rear.classification == "Legal" and any("lower accuracy" in n for n in rear.notes)


def _m(key, value, status="ok"):
    return Metric(key=key, label=key, value=value, unit="deg", status=status, confidence=0.9, reliability="high")


def test_injury_levels_and_unavailable():
    bio = BiomechanicsReport(upper_body=[_m("shoulder_angle_ffc", 15)], lower_body=[_m("front_knee_delta", -12)],
                             posture=[_m("trunk_lateral_br", -42), _m("counter_rotation", None, "unavailable_perspective")],
                             phase_table={})
    rep = inj.screen(bio, 900.0)
    by = {f.trigger_metric: f for f in rep.flags}
    assert by["Trunk lateral flexion at release"].level == "High concern"
    assert by["Trunk lateral flexion at release"].measured == 42          # abs value reported
    assert by["Front knee Δ FFC→BR (negative = collapse)"].level == "Moderate concern"
    assert by["Bowling shoulder angle at FFC (late arm)"].level == "High concern"
    assert by["Peak elbow extension speed (arm horizontal→BR)"].level == "Low concern"
    assert by["Shoulder counter-rotation BFC→FFC"].level == "Unavailable"
    assert by["Shoulder counter-rotation BFC→FFC"].measured is None        # never invent a value
    assert "Not a medical diagnosis" in rep.disclaimer
