"""Screening thresholds (DESIGN.md §7.2, §7.4). Literature-guided screening heuristics, NOT validated
clinical cut-offs. Sources informing the values: ICC Regulations (15° elbow extension); Portus et al. 2004
and Ranson et al. 2008 (lateral flexion / counter-rotation, lumbar stress in fast bowlers); Elliott 1992
(mixed action, shoulder counter-rotation > ~30°)."""

ICC_ELBOW_LIMIT = 15.0          # degrees of net elbow extension, arm-horizontal -> release
HORIZONTAL_LOOKBACK_S = 0.7     # search window for the arm-horizontal frame: this many seconds before release
UPPER_ARM_HORIZONTAL = 80.0    # deg from hanging-down: upper arm considered horizontal on the upswing
LEGALITY_MARGIN = {"side_on": 5.0, "front_on": 8.0, "rear": 8.0}
LEGALITY_MARGIN_LOW_VIS = 3.0   # added if mean arm visibility < 0.7
LEGALITY_MARGIN_LOW_FPS = 3.0   # added if fps < 100
MANUAL_MARGIN = 4.0             # manual digitising error (side-on, click precision ~±2–4°)
SEGMENT_RATIO = (0.65, 1.35)   # arm segment length vs bowler median; outside -> foreshortened/glitch, excluded
MAX_SEGMENT_FRAC = 1.6         # > 1.6× anthropometric length = landmark glitch
MIN_SEGMENT_FRAC_FRONT = 0.75  # front/rear: arm must look ≥ 75% of full length (0.70 gave a false Illegal on a legal bowler)
MIN_SEGMENT_FRAC = 0.55      # arm segment must be ≥ 55% of its anthropometric length (else foreshortened/wrong)
MIN_ELBOW_FRAMES = 3           # never classify from fewer clean elbow frames between arm-horizontal and release

# region, metric_key, label, (moderate, high), direction, use_abs, explanation
INJURY_RULES = [
    ("lower_back", "trunk_lateral_br", "Trunk lateral flexion at release", (30, 40), ">", True,
     "Large side-bend at release concentrates load on the lumbar spine (associated with stress injuries in fast bowlers)."),
    ("lower_back", "counter_rotation", "Shoulder counter-rotation BFC→FFC", (20, 30), ">", True,
     "Twisting the shoulders away from the target then back adds lumbar torsion (mixed-action pattern)."),
    ("lower_back", "separation_bfc", "Hip-shoulder separation at BFC", (20, 30), ">", True,
     "Hips and shoulders pointing in different directions at back-foot contact suggests a mixed action."),
    ("shoulder", "shoulder_angle_ffc", "Bowling shoulder angle at FFC (late arm)", (45, 20), "<", False,
     "Arm still low at front-foot contact means it must accelerate later and harder through release."),
    ("elbow", "elbow_ext_velocity", "Peak elbow extension speed (arm horizontal→BR)", (1000, 1500), ">", False,
     "Very rapid elbow extension increases valgus/extension load on the elbow."),
    ("front_knee", "front_knee_delta", "Front knee Δ FFC→BR (negative = collapse)", (-10, -20), "<", False,
     "Front knee bending after landing absorbs force poorly and loads the knee in flexion."),
    ("front_knee", "front_knee_ffc", "Front knee angle at FFC (locked/hyperextended)", (178, 185), ">", False,
     "Landing on a locked or hyperextended knee transmits high impact forces."),
    ("ankle", "foot_align_ffc", "Front foot angle vs pitch at FFC", (30, 45), ">", True,
     "A front foot turned across the pitch increases ankle and knee twisting load."),
    ("hip", "pelvic_drop_ffc", "Pelvic drop / hip tilt at FFC", (8, 12), ">", True,
     "Hip dropping on landing suggests weak hip control and adds load on hip and lower back."),
]

LEGALITY_DISCLAIMER = (
    "2D video estimate: Legal if net elbow extension < 15°, Illegal if ≥ 15° (side-on video is most accurate). "
    "Educational project — not an official ICC assessment.")
INJURY_DISCLAIMER = (
    "Not a medical diagnosis and not a validated injury-prediction model; it does not compute injury "
    "probability. Flags highlight observable movement patterns associated with higher mechanical stress. "
    "Review results with a qualified sports physiotherapist or biomechanist.")
