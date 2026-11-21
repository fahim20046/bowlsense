"""Pydantic data contract shared with the frontend (see DESIGN.md §6)."""
from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field

Arm = Literal["left", "right"]
Perspective = Literal["side_on", "front_on", "rear"]
Status = Literal["ok", "unavailable_low_confidence", "unavailable_perspective", "unavailable_not_detected"]
Reliability = Literal["high", "reduced", "low"]
PhaseName = Literal["run_up", "gather", "bfc", "ffc", "msr", "br", "follow_through"]
PHASE_ORDER: list[str] = ["run_up", "gather", "bfc", "ffc", "msr", "br", "follow_through"]
UNAVAILABLE = "Unavailable"


class Metric(BaseModel):
    key: str
    label: str
    value: Optional[float] = None
    unit: str
    status: Status
    confidence: float = 0.0
    reliability: Reliability
    phase: Optional[PhaseName] = None
    frame: Optional[int] = None


# ---- sessions ----
class SessionCreated(BaseModel):
    session_id: str
    status: Literal["queued"] = "queued"


class SessionStatus(BaseModel):
    session_id: str
    status: Literal["queued", "processing", "done", "failed"]
    progress: float
    stage: Optional[str] = None
    error: Optional[str] = None


class SessionSummary(BaseModel):
    session_id: str
    created_at: datetime
    bowler_name: Optional[str]
    bowling_arm: Arm
    perspective: Perspective
    status: str
    technique_score: Optional[float] = None
    legality_class: Optional[str] = None


# ---- pose ----
class VideoMeta(BaseModel):
    fps: float
    width: int
    height: int
    total_frames: int
    duration_s: float


class QualityReport(BaseModel):
    score: float
    resolution_ok: bool
    fps_ok: bool
    blur_variance: float
    sharp_ok: bool
    mean_visibility: float
    detection_rate: float
    warnings: list[str] = []


class PoseFrame(BaseModel):
    i: int
    t: float
    lm: Optional[list[tuple[float, float, float]]] = None   # 33 x (x_px, y_px, vis); image coords (y down)
    angles: dict[str, Optional[float]] = {}


class PoseData(BaseModel):
    meta: VideoMeta
    frames: list[PoseFrame]
    connections: list[tuple[int, int]]


# ---- phases ----
class PhaseMark(BaseModel):
    name: PhaseName
    frame: Optional[int] = None
    t: Optional[float] = None
    confidence: float = 0.0
    source: Literal["auto", "manual"] = "auto"


class PhaseUpdate(BaseModel):
    phases: dict[PhaseName, Optional[int]]


# ---- analysis ----
class BiomechanicsReport(BaseModel):
    upper_body: list[Metric]
    lower_body: list[Metric]
    posture: list[Metric]
    phase_table: dict[str, dict[str, Optional[float]]]


class ElbowPoint(BaseModel):
    frame: int
    t: float
    angle: Optional[float]


class ManualElbowPoint(BaseModel):
    """User-digitised bowling arm on one frame (image px)."""
    frame: int
    shoulder: tuple[float, float]
    elbow: tuple[float, float]
    wrist: tuple[float, float]


class ManualElbow(BaseModel):
    points: list[ManualElbowPoint]


class ManualLegality(BaseModel):
    points: list[ElbowPoint]                      # (frame, t, angle from clicks), sorted by frame
    horizontal_frame: int
    br_frame: int
    min_angle: float
    angle_at_br: float
    net_extension: float
    error_margin: float
    classification: str
    notes: list[str] = []
    inputs: list[ManualElbowPoint] = []          # raw clicks, so the UI can show/edit them


class LegalityResult(BaseModel):
    classification: str = UNAVAILABLE
    horizontal_frame: Optional[int] = None
    br_frame: Optional[int] = None
    angle_at_horizontal: Optional[float] = None
    min_angle: Optional[float] = None
    angle_at_br: Optional[float] = None
    net_extension: Optional[float] = None
    threshold: float = 15.0
    error_margin: Optional[float] = None
    timeline: list[ElbowPoint] = []
    notes: list[str] = []
    disclaimer: str = ""
    suggested_frames: list[int] = []              # frames to digitise manually (arm horizontal → release)
    confidence_level: Optional[Literal["high", "medium", "low"]] = None   # trust tier of the elbow frames used
    min_frame: Optional[int] = None               # frame of the most-flexed elbow (for the visual)
    br_used: Optional[int] = None                 # release frame actually used (nearest confident to BR)
    manual: Optional[ManualLegality] = None       # manually verified result, if the user digitised the arm
    final_classification: str = UNAVAILABLE       # manual if available, else automatic
    final_source: Literal["manual", "auto"] = "auto"


class StressFlag(BaseModel):
    region: str
    level: str
    trigger_metric: str
    measured: Optional[float]
    unit: str
    threshold_moderate: float
    threshold_high: float
    explanation: str


class InjuryReport(BaseModel):
    flags: list[StressFlag] = []
    disclaimer: str = ""
    implemented: bool = False


class Calibration(BaseModel):
    """Two clicks on the popping creases (image px): p1 = bowler's end, p2 = batter's end."""
    frame: int
    p1: tuple[float, float]
    p2: tuple[float, float]
    distance_m: float = 17.68


class ManualTiming(BaseModel):
    release_frame: int
    arrival_frame: int          # ball reaches the batter's popping crease


class SpeedResult(BaseModel):
    measured_kmh: Optional[float] = None            # ball-tracking speed (calibrated, side-on only)
    method: Literal["ball_tracking", "manual_timing", "none"] = "none"
    status: str = "unavailable_no_calibration"
    detections: int = 0
    fit_r2: Optional[float] = None
    track: list[tuple[int, float, float]] = []      # (frame, x_px, y_px) ball detections (image coords)
    manual_kmh: Optional[float] = None              # average speed from manual frame timing
    calibration: Optional[Calibration] = None
    manual: Optional[ManualTiming] = None
    notes: list[str] = []


class SpeedPotential(BaseModel):
    level: str = UNAVAILABLE
    components: list[Metric] = []
    scores: dict[str, Optional[float]] = {}         # component key -> 0..1 sub-score
    note: str = ("Biomechanical speed-potential indicator from technique features — NOT a speed measurement "
                 "and not derived from the ball.")


class ScoreComponent(BaseModel):
    key: str
    label: str
    weight: float
    score: Optional[float]
    based_on: list[str]


class TechniqueScore(BaseModel):
    total: Optional[float] = None
    partial: bool = True
    available_weight: float = 0.0
    components: list[ScoreComponent] = []


class CoachingInsight(BaseModel):
    priority: int
    fact: str
    impact: str
    cue: str
    drill: Optional[str] = None
    metric_key: str


class Performance(BaseModel):
    strengths: list[str] = []
    improvements: list[str] = []
    insights: list[CoachingInsight] = []


class ComparisonRow(BaseModel):
    key: str
    label: str
    unit: str
    a: Optional[float]
    b: Optional[float]
    delta: Optional[float]          # b - a (None if either unavailable)


class TrendPoint(BaseModel):
    session_id: str
    created_at: datetime
    value: Optional[float]


class TrendSeries(BaseModel):
    key: str
    label: str
    unit: str
    points: list[TrendPoint]


class AnalysisReport(BaseModel):
    session_id: str
    bowling_arm: Arm
    perspective: Perspective
    meta: VideoMeta
    quality: QualityReport
    phases: list[PhaseMark]
    biomechanics: BiomechanicsReport
    legality: LegalityResult = Field(default_factory=LegalityResult)
    injury: InjuryReport = Field(default_factory=InjuryReport)
    speed: SpeedResult = Field(default_factory=SpeedResult)
    speed_potential: SpeedPotential = Field(default_factory=SpeedPotential)
    score: TechniqueScore = Field(default_factory=TechniqueScore)
    performance: Performance = Field(default_factory=Performance)
    detected_perspective: Optional[Perspective] = None     # view estimated from the video (for mismatch warning)
    warnings: list[str] = []


class SessionSettings(BaseModel):
    perspective: Optional[Perspective] = None
    bowling_arm: Optional[Arm] = None
