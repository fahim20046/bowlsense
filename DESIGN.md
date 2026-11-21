# BowlSense AI — Design & Contract (Turn 1)

## 1. Architecture

```
React (Vite) ──HTTP/JSON──► FastAPI ──► Job runner (thread pool)
  <video> + <canvas>            │         video_processor → pose_estimator → phase_detector
  Recharts dashboards           │         → biomechanics_engine → legality_screener
                                │         → injury_screener → ball_tracker → performance_scorer
                                │         → coaching_engine → report_generator
                                ▼
                         SQLite (SQLAlchemy)  +  /storage/{session_id}/ (video, pose.json, report.json)
```
- Upload → session row `status=queued` → background job → `processing (progress %)` → `done | failed`.
- Pose is computed **once** and cached (`pose.json`). Phase edits / calibration only re-run downstream modules (fast, no MediaPipe).
- Frontend plays the **original** video (HTTP Range streaming) and draws the skeleton from JSON on `<canvas>`, synced via `requestVideoFrameCallback` (fallback `timeupdate`): `frame = round(mediaTime × fps)`.
- DB layer only through `db/repository.py` → switch to PostgreSQL by changing `DATABASE_URL`.

## 2. CV & Signal-Processing Method

**2.1 Quality check (video_processor)**
| Check | Method | Flag if |
|---|---|---|
| Resolution | metadata | < 640×360 |
| FPS | `CAP_PROP_FPS` | < 50 (warn: release blur, speed accuracy) ; < 25 reject speed |
| Blur | variance of Laplacian on 20 sampled frames (median) | < 100 |
| Visibility | mean visibility of 13 key landmarks | < 0.6 |
| Corrupt | `cap.read()` fails / 0 frames | reject (HTTP 422) |

Video quality score (0–100) = 30·res + 25·fps + 25·sharpness + 20·visibility (each sub-score clipped 0–1 vs target).

**2.2 Pose (pose_estimator)** — MediaPipe Pose `model_complexity=2, smooth_landmarks=False, min_detection_confidence=0.5`. Per frame store 33 × (x_px, y_px, visibility) + 33 × world (x,y,z m). Pixel coords = normalized × (W,H) (avoids aspect distortion).

**2.3 Smoothing**
1. Mask points with visibility < 0.5 → NaN.
2. Linearly interpolate gaps ≤ 3 frames; longer gaps stay NaN.
3. Savitzky–Golay per coordinate: window = odd(max(5, 0.10·fps)), polyorder = 3. Velocities via `savgol_filter(deriv=1)/Δt`.
4. Option: Butterworth 4th-order low-pass `filtfilt`, cutoff 12 Hz (limited to 0.8·Nyquist).
Note: smoothing can blunt peak elbow extension at release → legality uses a narrower window (5 frames) on the bowling arm.

**2.4 Phase detection (phase_detector)** — FA = front foot = opposite side to bowling arm.
- Direction of travel **d** = sign/unit of mean mid-hip velocity over first 30% of frames.
- Foot contact candidates: local maxima of ankle y (lowest image point) where |v_heel| + |v_foot_index| < 0.15·H_px/s.
- **BR** = argmin wrist_y (highest wrist) in last 60% of video, refined to frame of peak wrist angular speed about shoulder within ±3 frames.
- **FFC** = last front-foot contact before BR. **BFC** = last back-foot contact before FFC.
- **Gather** = argmin mid-hip y (peak of bound) in [BFC − 0.6 s, BFC].
- **MSR** = argmax |dψ_shoulder/dt| (shoulder transverse angular velocity) in [FFC, BR].
- **Run-up** = [0, Gather); **Follow-through** = (BR, end].
- Each phase returns `{frame, confidence, source: auto|manual}`. Order validated: Gather < BFC < FFC ≤ MSR ≤ BR. Failure → `frame=null` and dependent metrics `Unavailable`.

**2.5 Ball tracking (ball_tracker, M3)** — MOG2 background subtraction + 3-frame differencing in ROI seeded at release wrist and extended along **d**; contours filtered by area (scaled to H_px), circularity > 0.6; constant-velocity Kalman filter for association; accept track if ≥ 5 detections and line-fit R² ≥ 0.95.

## 3. 2D Monocular Limitations

| Metric group | Side-on | Front-on | Rear |
|---|---|---|---|
| Knee/elbow flexion, trunk forward lean, release height, arm path | **High** | Reduced | Reduced |
| Trunk lateral flexion, pelvic drop, foot alignment, crossover | Low | **High** | **High** |
| Shoulder/hip transverse rotation, separation, counter-rotation | Low (world-z estimate) | Reduced | Reduced |
| Ball speed | **Only view allowed** | Unavailable | Unavailable |

- Transverse angles use MediaPipe **world landmarks (estimated depth)** → always tagged `perspective_reliability: "low"/"reduced"`.
- Foreshortening: segments out of image plane appear shorter → angles biased toward 180°. Legality adds an error margin (Sec 6.4).
- Assumes static camera, single bowler, full body in frame, camera roughly perpendicular (side-on) or along pitch (front/rear).
- Motion blur at release (fps < 50) lowers wrist/elbow visibility → metrics drop to `Unavailable (Low Confidence)`.

## 4. Folder Structure

```
project cricket/
├─ context.md  progress.md  DESIGN.md  README.md
├─ backend/
│  ├─ requirements.txt   .env.example
│  └─ app/
│     ├─ main.py  config.py  thresholds.py
│     ├─ api/  routes_sessions.py  routes_analysis.py  routes_compare.py
│     ├─ schemas/  common.py  pose.py  analysis.py  session.py
│     ├─ db/  database.py  models.py  repository.py
│     ├─ core/  geometry.py  smoothing.py  landmarks.py
│     ├─ modules/
│     │   video_upload.py  video_processor.py  pose_estimator.py  phase_detector.py
│     │   biomechanics_engine.py  legality_screener.py  injury_screener.py
│     │   ball_tracker.py  performance_scorer.py  coaching_engine.py  report_generator.py
│     ├─ services/pipeline.py  (orchestrates modules, job status)
│     └─ tests/  (unit tests for geometry, phases, screening)
├─ frontend/
│  ├─ package.json  vite.config.js  tailwind.config.js
│  └─ src/
│     ├─ api/client.js  types.js
│     ├─ components/ VideoStudio/ (Player, SkeletonCanvas, PhaseTimeline, Controls)
│     │   MetricCard  ConfidenceBadge  Disclaimer  BodyMap  UnavailableValue
│     ├─ pages/ Upload Overview Studio Report Speed Injury History Compare
│     └─ App.jsx  main.jsx
└─ storage/  (gitignored: {session_id}/video.mp4, pose.json, report.json)
```

## 5. API Endpoints (prefix `/api`)

| Method | Path | Body / Query | Returns |
|---|---|---|---|
| GET | `/health` | – | `{status}` |
| POST | `/sessions` | multipart: `file`, `bowling_arm`, `perspective`, `bowler_name?` | `SessionCreated` (202) |
| GET | `/sessions` | `bowler_name?` | `SessionSummary[]` |
| GET | `/sessions/{id}` | – | `SessionStatus` |
| DELETE | `/sessions/{id}` | – | 204 |
| GET | `/sessions/{id}/video` | Range header | video stream |
| GET | `/sessions/{id}/frames/{idx}.jpg` | – | JPEG (calibration reference) |
| GET | `/sessions/{id}/pose` | – | `PoseData` |
| GET | `/sessions/{id}/analysis` | – | `AnalysisReport` |
| PUT | `/sessions/{id}/phases` | `PhaseUpdate` | `AnalysisReport` (recomputed) |
| PUT | `/sessions/{id}/calibration` | `Calibration` | `AnalysisReport` |
| POST | `/sessions/{id}/speed/manual` | `ManualTiming` | `SpeedResult` |
| GET | `/compare` | `a`, `b` | `ComparisonResult` |
| GET | `/trends` | `bowler_name`, `metrics=csv` | `TrendSeries[]` |

Errors: `{detail: str, code: str}` — codes `INVALID_FILE`, `CORRUPT_VIDEO`, `NOT_READY`, `NOT_FOUND`, `NO_BOWLER_DETECTED`.

## 6. Data Contract (Pydantic v2; frontend mirrors in `types.js`)

```python
Arm = Literal["left", "right"]
Perspective = Literal["side_on", "front_on", "rear"]
Status = Literal["ok", "unavailable_low_confidence", "unavailable_perspective", "unavailable_not_detected"]
Reliability = Literal["high", "reduced", "low"]
PhaseName = Literal["run_up","gather","bfc","ffc","msr","br","follow_through"]

class Metric(BaseModel):
    key: str                      # e.g. "front_knee_angle"
    label: str
    value: float | None           # None ⇔ status != "ok"
    unit: Literal["deg","ratio","pct_height","m_s","km_h","height_per_s","frames"]
    status: Status
    confidence: float             # mean visibility of landmarks used (0–1)
    reliability: Reliability      # from perspective table (Sec 3)
    phase: PhaseName | None
    frame: int | None

class SessionCreated(BaseModel): session_id: str; status: Literal["queued"]
class SessionStatus(BaseModel):
    session_id: str; status: Literal["queued","processing","done","failed"]
    progress: float; stage: str | None; error: str | None
class SessionSummary(BaseModel):
    session_id: str; created_at: datetime; bowler_name: str | None
    bowling_arm: Arm; perspective: Perspective; status: str
    technique_score: float | None; legality_class: str | None

# ---- Pose ----
class VideoMeta(BaseModel):
    fps: float; width: int; height: int; total_frames: int; duration_s: float
class QualityReport(BaseModel):
    score: float; resolution_ok: bool; fps_ok: bool; blur_variance: float
    sharp_ok: bool; mean_visibility: float; warnings: list[str]
class PoseFrame(BaseModel):
    i: int; t: float
    lm: list[tuple[float, float, float]] | None   # 33 × (x_px, y_px, vis), smoothed; None = no detection
    angles: dict[str, float | None]               # per-frame: elbow_bowl, knee_front, knee_back, trunk_lean, ...
class PoseData(BaseModel):
    meta: VideoMeta; frames: list[PoseFrame]; connections: list[tuple[int,int]]

# ---- Phases ----
class PhaseMark(BaseModel):
    name: PhaseName; frame: int | None; t: float | None
    confidence: float; source: Literal["auto","manual"]
class PhaseUpdate(BaseModel): phases: dict[PhaseName, int]   # partial allowed

# ---- Analysis ----
class BiomechanicsReport(BaseModel):
    upper_body: list[Metric]; lower_body: list[Metric]; posture: list[Metric]
    phase_table: dict[PhaseName, dict[str, float | None]]   # metric_key → value at phase

class ElbowPoint(BaseModel): frame: int; t: float; angle: float | None
class LegalityResult(BaseModel):
    classification: Literal["No obvious concern detected","Further assessment recommended",
                            "Potential legality concern","Unavailable"]
    horizontal_frame: int | None; br_frame: int | None
    angle_at_horizontal: float | None; min_angle: float | None; angle_at_br: float | None
    net_extension: float | None; threshold: float = 15.0; error_margin: float
    timeline: list[ElbowPoint]; notes: list[str]; disclaimer: str

class StressFlag(BaseModel):
    region: Literal["lower_back","shoulder","elbow","front_knee","ankle","hip"]
    level: Literal["Low concern","Moderate concern","High concern","Unavailable"]
    trigger_metric: str; measured: float | None; unit: str
    threshold_moderate: float; threshold_high: float; explanation: str
class InjuryReport(BaseModel): flags: list[StressFlag]; disclaimer: str

class Calibration(BaseModel):
    frame: int; p1: tuple[float,float]; p2: tuple[float,float]   # pixel coords of popping creases
    distance_m: float = 17.68
class ManualTiming(BaseModel): release_frame: int; arrival_frame: int
class SpeedResult(BaseModel):
    measured_kmh: float | None
    method: Literal["ball_tracking","manual_timing","none"]
    status: Literal["ok","unavailable_perspective","unavailable_no_calibration",
                    "unavailable_tracking_failed"]
    detections: int; fit_r2: float | None; track: list[tuple[int,float,float]]; notes: list[str]
class SpeedPotential(BaseModel):
    level: Literal["Low","Moderate","High","Unavailable"]
    components: list[Metric]; note: str   # "Not a speed measurement"

class ScoreComponent(BaseModel):
    key: str; label: str; weight: float; score: float | None; based_on: list[str]
class TechniqueScore(BaseModel):
    total: float | None; partial: bool; available_weight: float; components: list[ScoreComponent]
class CoachingInsight(BaseModel):
    priority: int; fact: str; impact: str; cue: str; drill: str | None; metric_key: str
class Performance(BaseModel):
    strengths: list[str]; improvements: list[str]; insights: list[CoachingInsight]

class AnalysisReport(BaseModel):
    session_id: str; bowling_arm: Arm; perspective: Perspective
    meta: VideoMeta; quality: QualityReport; phases: list[PhaseMark]
    biomechanics: BiomechanicsReport; legality: LegalityResult; injury: InjuryReport
    speed: SpeedResult; speed_potential: SpeedPotential
    score: TechniqueScore; performance: Performance; warnings: list[str]

class ComparisonResult(BaseModel):
    a: AnalysisReport; b: AnalysisReport; deltas: dict[str, float | None]
class TrendSeries(BaseModel):
    metric_key: str; points: list[tuple[datetime, str, float | None]]  # (date, session_id, value)
```
Fields owned by later milestones return `status/level/classification = "Unavailable"` until implemented — never placeholder numbers.

## 7. Formulas

**Notation.** Image coords p = (x, y), y flipped to up: p = (x_px, H − y_px). Landmark ids: shoulder S(11/12), elbow E(13/14), wrist W(15/16), hip P(23/24), knee K(25/26), ankle A(27/28), heel Hl(29/30), foot index F(31/32), nose N(0). Suffix _b = bowling side, _f = front leg side, _k = back leg. Mid-point M(a,b) = (a+b)/2.
Direction of travel **d** = (sign(v̄ₓ), 0); vertical **u** = (0,1).

**7.1 Joint angle (unsigned)**: `θ(a,b,c) = arccos( (a−b)·(c−b) / (|a−b|·|c−b|) )` ∈ [0°,180°].
**Signed angle** (for hyperextension, side-on): `θ_s = atan2( (a−b)×(c−b), (a−b)·(c−b) )` with 2D cross `u×v = uₓv_y − u_yvₓ`, sign normalized so normal flexion < 180° and hyperextension > 180°.
**Segment angle to reference r**: `φ(v, r) = arccos( v·r / (|v||r|) )`. **Line tilt**: `α = atan2(Δy, Δx)` wrapped to [−90°, 90°].

| # | Parameter | Formula | Phases |
|---|---|---|---|
| 1 | Bowling shoulder angle | θ(E_b, S_b, P_b) (upper arm vs trunk) | Gather, FFC, BR |
| 2 | Elbow angle | θ(S_b, E_b, W_b); flexion = 180 − θ | continuous |
| 3 | Release height | h = (y(W_b) − y_ground) / H_s ; y_ground = min y of heels at BR ; H_s = median over run-up of (y(N) − y(heel mid)) / 0.936 (nose ≈ 93.6% stature) | BR |
| 4 | Wrist position at release | horizontal offset (x(W_b) − x(A_f))·dₓ / H_s | BR |
| 5 | Front arm elevation | φ(E_nb − S_nb, −u) (0° = hanging, 180° = vertical up) | FFC, BR |
| 6 | Front arm pull-down | Δ elevation FFC→BR and wrist path y(W_nb) vs y(P_mid) at BR | FFC→BR |
| 7 | Shoulder alignment (2D tilt) | α(S_R − S_L) | BFC, FFC, BR |
| 8 | Shoulder transverse rotation | ψ_s = atan2(z_R − z_L, x_R − x_L) from world landmarks | BFC, FFC, BR |
| 9 | Hip alignment / rotation | α(P_R − P_L); ψ_h = atan2(Δz, Δx) of hips (world) | BFC, FFC, BR |
| 10 | Shoulder-hip separation | Sep = wrap180(ψ_s − ψ_h) | FFC (also BFC) |
| 11 | Shoulder counter-rotation | CR = max ψ_s in [BFC, FFC] − ψ_s(BFC) (toward closed) | BFC→FFC |
| 12 | Front knee angle | θ(P_f, K_f, A_f) (signed in side-on) | FFC, BR |
| 13 | Front knee Δ | Δk = θ_k(BR) − θ_k(FFC). Δk ≥ +5° extension (brace), \|Δk\| < 5° braced/constant, Δk ≤ −10° flexion (collapse) | FFC→BR |
| 14 | Back knee angle | θ(P_k, K_k, A_k); drive = max θ in [BFC, FFC] | BFC, drive |
| 15 | Front foot alignment | φ(F_f − Hl_f, d) (front/rear view: angle vs pitch axis in image) | FFC |
| 16 | Foot landing position | lateral offset (x(A_f) − x(A_k at BFC)) / H_s (front/rear view; crossover sign by arm) ; stride length \|A_f − A_k\|·dₓ / H_s (side-on) | FFC |
| 17 | Trunk forward lean | T = M(S) − M(P); lean = signed φ(T, u), positive toward d (side-on) | FFC, BR |
| 18 | Trunk lateral flexion | same as 17 but on frontal plane (front/rear view), positive away from bowling arm | FFC, BR |
| 19 | Pelvic drop | α(P_R − P_L) (front/rear) | FFC |
| 20 | Head stability | n'(t) = N(t) − M(P)(t) for t ∈ [BFC, BR]; σ_head = sqrt(var(n'ₓ)+var(n'_y)) / H_s × 100 (%height) | BFC→BR |
| 21 | Centre of mass | COM = Σ wᵢ·cᵢ ; head 0.081 (N), trunk 0.497 (M(S),M(P) mid), upper arms 0.056, forearms+hands 0.044, thighs 0.20, shanks+feet 0.122 (Dempster, segment midpoints) | all |
| 22 | Follow-through balance | v_COM decel = (v_COM,x(BR) − v_COM,x(BR+0.4s))/0.4 s ; balance offset = (x(COM) − x(base mid))/H_s at end | post-BR |
| 23 | Run-up momentum | v_hip = \|dM(P)ₓ/dt\| / H_s at BFC (heights/s) ; with calibration → m/s | BFC |
| 24 | Release angular speed | ω_arm = \|dφ(W_b − S_b)/dt\| peak near BR (deg/s) | BR |

Each metric confidence = min visibility of its landmarks at that frame (or mean over window). confidence < 0.5 → `unavailable_low_confidence`. Perspective "low" for a metric's group → still computed but tagged; metrics marked "N/A for view" (e.g. ball speed front-on) → `unavailable_perspective`.

**7.2 Legality screening**
- t_h = first frame in [FFC − 0.3 s, BR] where upper arm is horizontal: φ(E_b − S_b, d or −d) ≤ 10° rising (shoulder angle ≈ 90°).
- θ_min = min θ_elbow over [t_h, BR]; θ_BR = θ_elbow(BR).
- **Δθ = θ_BR − θ_min** (net extension; flexion→extension positive).
- Error margin m = 5° (side-on) | 8° (front/rear); +3° if mean arm visibility < 0.7; +3° if fps < 100.
- Class: Δθ < 15 − m → *No obvious concern detected*; 15 − m ≤ Δθ ≤ 15 + m → *Further assessment recommended*; Δθ > 15 + m → *Potential legality concern*; missing frames/low confidence → *Unavailable*.
- Disclaimer always shown (preliminary 2D screening, not ICC assessment; cannot certify legal/illegal).

**7.3 Speed**
- Calibration scale: s = 17.68 / \|p₂ − p₁\| (m/px); pitch axis ê = (p₂ − p₁)/\|p₂ − p₁\|.
- Per-step speed vᵢ = ((bᵢ₊₁ − bᵢ)·ê)·s / Δt ; **v = median(vᵢ) × 3.6 km/h** (first 6 post-release detections ≈ release speed).
- Only if perspective = side_on AND calibration AND ≥ 5 detections AND R² ≥ 0.95, else `Unavailable`.
- Manual fallback: v = D / ((f_arrival − f_release)/fps) × 3.6, D = ((p₂ − W_b(BR))·ê)·s (release point → far popping crease). Flagged "manual, avg speed".
- **Speed-potential** (separate, qualitative): z-normalized 0–1 sub-scores: run-up momentum (#23, target ≥ 1.6 H/s), front-knee Δ (#13, target ≥ 0°), separation (#10, target 30–45°), release height (#3, target ≥ 1.15) → mean → Low (< 0.4) / Moderate / High (≥ 0.7).

**7.4 Injury stress screening** (thresholds in `thresholds.py`, literature-guided; e.g. Portus 2004, Elliott 1992, Ranson 2008)
| Region | Trigger | Moderate | High |
|---|---|---|---|
| Lower back | Lateral trunk flexion at BR (#18) | > 30° | > 40° |
| Lower back | Shoulder counter-rotation (#11) | > 20° | > 30° |
| Lower back | Sep at BFC (mixed action) (#10) | > 20° | > 30° |
| Shoulder | Shoulder angle at BR (#1) | > 190° (signed) or arm late: shoulder angle at FFC < 90° | > 200° |
| Elbow | Signed elbow angle (hyperext.) | > 185° | > 192° |
| Elbow | Peak extension velocity near BR | > 1000°/s | > 1500°/s |
| Front knee | Δk collapse (#13) | < −10° | < −20° |
| Front knee | Knee angle at FFC (locked impact) | > 175° + fast COM decel | > 180° signed |
| Ankle | Foot alignment vs pitch (#15) | > 30° | > 45° |
| Hip | Pelvic drop at FFC (#19) | > 8° | > 12° |
Every flag returns measured value + thresholds. Disclaimer: not a medical diagnosis / not an injury-probability model; consult a physiotherapist or biomechanist.

**7.5 Technique score** — component sᵢ ∈ [0,100] by piecewise-linear target band (100 inside band, linear to 0 at band ± tolerance).
| Component | Weight | Based on |
|---|---|---|
| Front-leg brace | 20 | #12, #13 |
| Hip-shoulder mechanics | 15 | #10, #11 |
| Trunk posture | 15 | #17, #18 |
| Arm action & release height | 15 | #3, #5, #6 |
| Head stability | 10 | #20 |
| Run-up & gather | 10 | #23, #14 |
| Follow-through & balance | 10 | #22 |
| Elbow action margin | 5 | 7.2 Δθ |
`Total = Σ wᵢsᵢ / Σ wᵢ` over **available** components; `partial = Σw_available < 60` → shown with warning; `< 40` → total `None`.

**7.6 Coaching engine** — rule table: `(metric_key, condition, fact_template, impact, cue, drill)`. Fire rules → priority = component weight × deviation from band → top items as strengths (in-band, highest weight) / improvements (largest weighted deviation). Only metrics with status `ok` can fire.

---
**Awaiting approval → then Milestone 1.**
