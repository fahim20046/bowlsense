"""Deterministic rule-based coaching translation (no LLM): Measured Fact → Biomechanical Impact → Actionable Cue.
Only metrics with status 'ok' can fire. Priority = rubric weight × shortfall from the target band."""
from ..schemas import CoachingInsight, InjuryReport, Metric, Performance
from .performance_scorer import COMPONENTS, SUB

# key: (impact if outside target, cue, drill, strength text)
RULES = {
    "front_knee_ffc": ("A soft front knee at landing leaks the run-up energy instead of converting it into upper-body rotation.",
                       "Land on a firm, almost straight front leg — 'hit a wall' with the front foot.",
                       "Front-leg brace drill: 3-step approach, land and hold a straight front leg for 2 s.",
                       "Firm front leg at front-foot contact"),
    "front_knee_delta": ("The front knee bending after landing (collapse) reduces the whip over the braced leg and loads the knee.",
                         "Keep the front knee firm from landing until the ball has gone.",
                         "Wall-brace: bowl from a short run, front foot against a marker, no knee give.",
                         "Front leg braces (no collapse) through release"),
    "separation_ffc": ("Hip-shoulder separation stores elastic energy; outside 30–45° the trunk either can't stretch or over-twists.",
                       "Lead with the hips toward the target while the shoulders stay closed a fraction longer.",
                       "Medicine-ball rotational throws from a side-on stance.",
                       "Good hip-shoulder separation at front-foot contact"),
    "counter_rotation": ("Rotating the shoulders away from the target between back- and front-foot contact adds lumbar torsion (mixed action).",
                         "Keep the shoulders and hips aligned in the same direction from back-foot contact.",
                         "Mirror work: gather and back-foot contact with hips and shoulders both side-on (or both open).",
                         "Low shoulder counter-rotation"),
    "trunk_lean_br": ("Forward trunk flexion at release transfers momentum into the ball; too little or too much changes release height and control.",
                      "Drive the chest down over the front knee through release.",
                      "Kneeling bowling: release over a braced front knee, chest finishing over it.",
                      "Strong forward trunk flexion at release"),
    "trunk_lateral_br": ("Excessive side-bend at release is linked with lumbar stress in fast bowlers.",
                         "Stay taller at release — head over the front foot, not falling away.",
                         "Bowl along a line on the pitch with the head kept above it at release.",
                         "Upright trunk (low side-bend) at release"),
    "release_height_br": ("A low release point flattens the trajectory and reduces bounce.",
                          "Reach up tall at release — 'bowl over the top of a tall stack of chairs'.",
                          "Target-over-barrier drill: release clearing a raised cone line.",
                          "High release point"),
    "front_arm_elev_ffc": ("A low front arm at landing weakens the counter-pull that accelerates upper-body rotation.",
                           "Get the front arm high and pointing at the target as the front foot lands.",
                           "Front-arm 'reach and pull' shadow bowling, 10 reps.",
                           "High front arm at front-foot contact"),
    "front_arm_pulldown": ("A weak front-arm pull-down slows trunk rotation through release.",
                           "Pull the front arm down and tuck it in hard as the bowling arm comes over.",
                           "Resistance-band front-arm pull-downs.",
                           "Strong front-arm pull-down"),
    "head_stability": ("Head movement between back-foot contact and release disturbs balance and accuracy.",
                       "Keep the eyes level and still on the target from back-foot contact.",
                       "Bowl with a cap marker: the peak stays level through the delivery stride.",
                       "Stable head through the delivery"),
    "runup_momentum": ("Lower approach speed at back-foot contact limits the energy available for the delivery.",
                       "Build rhythm and speed gradually into the crease, no deceleration before the jump.",
                       "Run-up rhythm drill with marker cones and accelerating strides.",
                       "Good run-up momentum into the crease"),
    "back_knee_drive": ("Limited back-leg drive reduces forward momentum into the front-foot landing.",
                        "Push off the back foot toward the target.",
                        "Skip-and-drive drill from the gather.",
                        "Strong back-leg drive"),
    "balance_offset": ("Falling away after release suggests momentum isn't flowing toward the target.",
                       "Follow through straight toward the target and finish balanced.",
                       "Follow-through 'walk off the line' drill.",
                       "Balanced follow-through"),
    "pelvic_drop_ffc": ("A hip dropping on front-foot landing shows weak hip control and adds load on the hip and lower back.",
                        "Land with level hips — squeeze the glute of the front leg as the foot lands.",
                        "Single-leg landing holds on the front leg, 3 × 8 each side.",
                        "Level hips at front-foot landing"),
    "foot_align_ffc": ("A front foot turned across the pitch twists the ankle and knee under load and blocks hip rotation.",
                       "Land with the front toes pointing at the target / fine leg.",
                       "Foot-placement drill: land the front foot on a taped target line, toes aligned.",
                       "Front foot well aligned on landing"),
    "elbow_net_extension": ("Elbow straightening during the delivery is the parameter assessed under the ICC 15° rule.",
                            "Keep the bowling arm straight from horizontal to release; seek a qualified biomechanist if concerned.",
                            None,
                            "Small elbow extension (straight-arm action)"),
}
_W = {k: w / len(keys) for _, _, w, keys in COMPONENTS for k in keys}


def _fact(m: Metric, target: str) -> str:
    unit = {"deg": "°", "ratio": "", "pct_height": "% of height", "height_per_s": " heights/s"}.get(m.unit, "")
    where = f" (frame {m.frame})" if m.frame is not None else ""
    return f"{m.label}: {m.value:g}{unit}{where}; target {target}."


def coach(subs: dict, metrics: dict[str, Metric], injury: InjuryReport) -> Performance:
    weak, strong = [], []
    for key, s in subs.items():
        if s is None or key not in RULES:
            continue
        if s < 0.6:
            weak.append((_W[key] * (1 - s), key))
        elif s >= 0.85:
            strong.append((_W[key] * s, key))
    weak.sort(reverse=True)
    strong.sort(reverse=True)

    insights = []
    for pri, (_, key) in enumerate(weak[:6], start=1):
        impact, cue, drill, _ = RULES[key]
        insights.append(CoachingInsight(priority=pri, fact=_fact(metrics[key], SUB[key][2]), impact=impact, cue=cue,
                                        drill=drill, metric_key=key))
    for f in injury.flags:      # high stress flags always surface, after technique items
        if f.level == "High concern":
            insights.append(CoachingInsight(
                priority=len(insights) + 1, metric_key=f.trigger_metric,
                fact=f"{f.trigger_metric}: {f.measured}{'°/s' if f.unit == 'deg_s' else '°'} (High concern threshold {f.threshold_high}).",
                impact=f.explanation, cue="Review this movement pattern with a qualified physiotherapist or biomechanist.",
                drill=None))
    return Performance(strengths=[RULES[k][3] for _, k in strong[:3]],
                       improvements=[metrics[k].label for _, k in weak[:3]], insights=insights)
