# Progress

| Step | Status | Notes |
|---|---|---|
| Turn 1: Design & contract (DESIGN.md) | ✅ 2026-11-20 | Approved |
| M1: Backend, upload, pose+smoothing, phases, core angles, SQLite, React player+canvas, basic report | ✅ Validated on archive footage (see below) | 5/5 tests pass; UI verified |
| M2: Legality timeline + injury screening + UI | ✅ 2026-11-20 | 8/8 tests; pages verified in browser |
| M3: Ball tracking + calibration + speed potential | ✅ 2026-11-20 | 13/13 tests (synthetic end-to-end speed ±3 km/h); UI verified |
| M4: Coaching engine + scoring + session comparison | ✅ 2026-11-20 | 17/17 tests; UI verified |

## M1 — what exists
- `backend/app`: `main.py` (API), `pipeline.py` (job runner, pose cache `pose_raw.npz`, recompute on phase edit), `db.py` (SQLAlchemy + Repo), `schemas.py` (contract), `core/geometry.py`, `core/smoothing.py`, `modules/` (video_processor, pose_estimator, kinematics, phase_detector, biomechanics_engine, report_generator).
- `frontend/src`: `App.jsx` (Overview + History), `pages/Upload.jsx`, `pages/Studio.jsx` (video + canvas skeleton/arcs, 0.25/0.5x, frame step, editable phase timeline), `pages/Report.jsx`.
- Endpoints live: health, sessions CRUD, video (Range), frames/{i}.jpg, pose, analysis, PUT phases.

## Deviations from DESIGN.md (intentional)
- mediapipe 1.2.3 has no `mp.solutions` → uses Tasks `PoseLandmarker` **heavy** model (= complexity 2), auto-downloaded to `backend/models/`.
- Non-H.264 uploads transcoded with bundled ffmpeg (`imageio-ffmpeg`, libx264, passthrough frames); analysis runs on the same file the browser plays → frame sync.
- Stature H = 90th pct of (thigh+shank+trunk)/0.779 (posture-invariant) instead of standing nose-heel height.
- Schemas in one `schemas.py`; db in one `db.py` (simpler than folders).

## M1 validation (archive/ = 40 broadcast videos, 720p, 30 fps, with GT release frames)
- Clips cut to `samples/` (release at clip frame 90): `rear_rightarm_fast.mp4`, `sideon_leftarm_spin.mp4`.
- Problem found: multi-person broadcast frames → MediaPipe locked onto umpire/batter.
  Fix: 2-pass pose — multi-person detect + track, then crop-tracking around bowler with other people masked,
  hip-continuity/scale identity gate. Optional **bowler click hint** at upload (UI preview + click).
- Rear clip + hint: bowler tracked 82% of frames; **BR detected at 88 vs GT 90** (2 frames @30 fps).
  BR rule changed to arm-vertical index `(W−S)_y/(|S−E|+|E−W|)` (gather vs release disambiguation).
- Fixed: Windows cp1252 write crash (UTF-8), NaN-propagating `np.unwrap`, Studio seek off-by-one, overlapping phase labels.
- Sagittal metrics tagged `low` in front/rear; trunk lean (front/rear) and lateral flexion/pelvic drop (side-on) → `Unavailable (Camera View)`.

## YOLO tracker upgrade (2026-11-20)
- `modules/person_tracker.py`: YOLO11n (imgsz 960) + ByteTrack → bowler track = most motion (incl. depth/scale change),
  static-prefix trim (umpire→bowler ID swap), fragment stitching. Click hint still optional.
- `pose_estimator.py` rewritten: MediaPipe on upscaled bowler crop, other people greyed out, hips-in-box identity check.
- Pose on GT bowler (no click): rear clip **96%** (was ~0% auto / 82% with click); side-on clip 63% (bowler's entry lost to ID swap).
- BR rule: centre of the wrist motion-blur gap right after arm-up (30 fps hides the wrist at release). Rear +6 f, side-on −5 f.

- **Batch eval, 10 random annotated deliveries (no click)**: pose on GT bowler mean **38%** (0–95%);
  BR found 4/10, median |error| **21 frames**. The 2-clip results did not generalize: auto bowler selection
  and the blur-gap BR rule are unreliable on 30 fps multi-person broadcast footage.
  Script: scratchpad `batch_eval.py N`.

## M2 — legality + injury screening
- `thresholds.py`: ICC 15°, view/fps/visibility error margins, 9 injury rules (region, metric, moderate/high, rationale), disclaimers.
- `modules/legality_screener.py`: arm-horizontal frame (upper-arm elevation ≥ 80°) → min elbow → BR (±1 frame fallback);
  Δθ vs 15 ± margin (5° side-on / 8° other, +3 low vis, +3 fps<100). Requires ≥50% confident frames, else Unavailable.
- `modules/injury_screener.py`: Low/Moderate/High per rule with exact measured value + thresholds; Unavailable with reason.
- Biomechanics: plausibility ranges (e.g. lateral flexion ±75°, counter-rotation ≤ 90°) → implausible = Unavailable (Low Confidence).
- Frontend `pages/Screening.jsx`: Legality (badge, numbers, Recharts elbow timeline with FFC/arm-horizontal/BR markers), Injury (SVG body map + flag table). Overview shows both.
- Archive samples: legality = Unavailable on all 3 (30 fps blur hides elbow at release) — correct "no fake data" behaviour.
- Dev note: uvicorn `--reload` stalls on Windows → restart backend manually after backend edits.

## M3 — ball speed + speed potential
- `modules/ball_tracker.py`: 3-frame differencing on DISTINCT frames (duplicate-frame aware), bowler body masked
  (except bowling hand), size filter from stature, seed near release hand, fps-scaled 40–170 km/h gate for 2nd point,
  side-on direction constraint, alpha-beta association; accept ≥5 detections and x(t) linearity R² ≥ 0.95.
- `modules/speed_analyzer.py`: km/h only if side-on + calibration + accepted track (median of first steps projected on
  pitch axis, plausibility 40–170). Manual timing fallback (any view): calibrated distance if side-on, else
  17.68 − 0.8 m (flagged approx). Speed-potential (separate): run-up momentum, front-knee Δ, separation, release height → Low/Moderate/High (≥2 components).
- API: `PUT /sessions/{id}/calibration` (null clears), `POST /sessions/{id}/speed/manual` (empty clears) → return AnalysisReport. DB auto-migration adds new columns.
- Quality: duplicate-frame ratio → effective fps warning (archive: rear ≈ 17–26 fps effective).
- Frontend `pages/Speed.jsx`: measured speed / Unavailable reason, potential bars, release point, calibration by 2 clicks on a frame, manual timing. Studio draws ball detections (yellow).
- Archive clips: measured speed Unavailable on all (rear view / tracker R² 0.23 rejected) — correct behaviour.

## M4 — scoring, coaching, comparison
- `modules/performance_scorer.py`: 8 weighted components (20/15/15/15/10/10/10/5), 14 sub-scores with explicit
  target bands; unavailable excluded, weights renormalised; partial < 60% weight, no total < 40%. Each component lists
  "metric: value → sub-score (target …)".
- `modules/coaching_engine.py`: rule table per metric → Measured Fact (value + frame + target) → Impact → Cue → Drill;
  priority = weight × shortfall; top-3 strengths/improvements; High injury flags appended with physio referral.
- API: `GET /api/compare?a=&b=` (rows with B−A deltas), `GET /api/trends?metrics=csv&bowler_name=`. Session row stores technique_score.
- Frontend `pages/Coaching.jsx`: ScoreCard (expandable rubric), Coaching tab, Compare table + Recharts trend in History. Overview shows score + top-3 recommendations.
- Samples: side-on 70.5 (70% weight), rear 76.0 (partial, 45%), rear-2 None (35%).

## Real practice clip test (Pexels #37317947, free license) — `samples/pexels/`
- Right-arm, rear view, nets, 30 fps, 1080×1920, handheld camera following the bowler.
- Tracking: bowler 100% of frames, mean visibility 0.82. BR auto = 225 (visually correct: arm vertical 221–226).
- Gather/BFC/FFC auto WRONG (190 for FFC while airborne): moving camera breaks image-space foot-stillness.
  Corrected via phase edit (gather 196, BFC 207, FFC 216) — the intended workflow.
- Exposed 2 overclaims, now fixed: (1) legality classified from rear view ("Potential concern", Δ 42.5°, a
  foreshortening artefact) → classification now side-on only, other views show values "for reference only";
  (2) low-reliability metrics (e.g. release height 0.56 from rear) drove score/coaching/speed-potential → now excluded.
- Result after fixes: legality Unavailable (view), injury Moderate lower-back (counter-rotation 27.8°) and front knee
  (Δ −12.2°), score None (only 30% rubric weight reliable from rear) — honest output for a rear clip.

## User clip "archar" (front-on slow-motion, uploaded as Side-on) — fixes (2026-11-20)
- Root cause of many Unavailables: wrong view selected. Added `kinematics.estimate_view` (hip travel > 0.8 stature
  → side-on; else shoulder order → front/rear): correct on all 6 stored sessions. Mismatch warning + Overview
  "Camera view & bowling arm" card + `PUT /sessions/{id}/settings` (re-analyse without re-upload).
- BR rule now = frame of highest bowling wrist above head (head → shoulder-mid + 0.18 H if cropped), then ≤ 0.07 s
  into a blur gap. Check: user clip 343 ✓ (ball visible leaving hand 346), Pexels 221 ✓, rear sample 89 ✓ (GT 90),
  rear 96 (+6), side-on spin 102 (+12).
- BR-phase metrics use nearest confident frame within ±2 when the release frame is blurred.
- Head stability valid in any view; new rubric part "Landing alignment" (pelvic drop, foot angle; w10; runup/follow → 5).
  Elbow extension-speed stress flag only from side-on.
- Result: 34/42 metrics measured, score 70.4 (50% weight), legality Unavailable (front view — correct).
- Note: slow-motion footage plays slower than real time, so per-second values (angular speed, momentum) are scaled down.

## Side-on archive test (20221112_4139153 @ 16177, left-arm spin) — `samples/sideon_leftarm_spin_2.mp4`
- Only 21 side-on deliveries in the archive (mostly this match). BR auto 89 vs GT 90 ✓; FFC 84.
- Exposed a false "Potential legality concern" (Δ 46.8°) caused by one glitched frame (forearm 14 px = collapsed).
  Fix: arm-segment-length consistency (0.65–1.35 × bowler median) + ≥ 3 clean frames, else Unavailable.
  Now: legality Unavailable (15 glitch frames excluded at 30 fps), score 64.9 (65% weight); strengths firm front leg,
  forward trunk flexion; front knee 182° at FFC → Moderate (locked knee).

## Manual elbow verification (legality) — 2026-11-20
- `PUT /sessions/{id}/legality/manual` {points:[{frame, shoulder, elbow, wrist}]} (≥ 2 frames; null clears).
  Δθ = θ(last frame) − min θ(digitised frames); margin 4° (+3 if fps < 100); classification side-on only.
- LegalityResult: `suggested_frames` (arm-horizontal, mid, release), `manual`, `final_classification`,
  `final_source` (manual preferred). DB `legality_class` + scoring use the final/manual value.
- Frontend `components/ManualElbow.jsx` on the Legality tab: zoomed crop around the auto elbow, click S→E→W,
  live angle, ±1 frame stepping, zoom, saved-frame list, compute/clear; chart overlays manual points (pink).
- Tests: manual angle geometry + verdict rules (19/19). API flow verified (compute, 400 on 1 frame, clear).
  Browser: tool renders on the side-on session; full click flow not yet exercised by me (user was using the pane).

## User side-on slow-motion clip (session 240098ab) — 2026-11-20
- View auto-detected side-on ✓; 35/42 metrics; score 77.1; first automatic verdict appeared ("No obvious concern", Δ 6.8°).
- Visual check: arm horizontal 944 ✓, but real release ≈ 964–966; tracking lost 956+ (bowler overlaps the
  non-striker/umpire), so BR 953 was the last visible frame → the clean verdict was premature.
- Fix: legality requires continuous tracking ≥ 0.15 s after BR (≥ 2 missing frames → "Release not confirmed",
  Unavailable, pointer to manual verification). Now Unavailable for this clip. BFC 930 / FFC 931 wrong (visual ≈ 910 / 930).
- Next improvement candidate: keep tracking through bowler–umpire overlap at release (occlusion handling).

## Legality rule simplified (user request, 2026-11-20)
- Verdict now binary: net elbow extension < 15° → **Legal**, ≥ 15° → **Illegal** (auto and manual); margin shown
  for info only. Kept: side-on requirement, arm-segment glitch filter, ≥ 3 clean frames. Truncated release no
  longer blocks — verdict uses visible frames + "Partial" note. Disclaimer shortened (educational, not ICC).
- User side-on clip 240098ab → Legal (6.8°, partial: tracking lost after frame 953).

- Follow-up (user request): verdicts now also from front/rear views, with "lower accuracy" note (bend can be hidden →
  tends to Legal). Frame rule relaxed to ≥ 3 clean frames. New anthropometric floor: upper arm ≥ 0.55×0.186 H,
  forearm ≥ 0.55×0.146 H, else frame excluded (stopped the spinner's false "Illegal 46.8°").
  Verdicts: archer front-on Legal (0°), user side-on Legal (6.8°), archive spinner Unavailable.

## Multi-person noise + elbow visual (2026-11-20)
- `kinematics.drop_identity_jumps`: frames whose hip centre deviates > 1 torso length from the ±7-frame rolling
  median, or torso size ratio outside 0.6–1.6, are removed (skeleton jumped to umpire/batter). Warning lists count. Test added (20/20).
- Glitch filter fixed: median-over-clip arm reference removed (run-up foreshortening rejected good release frames);
  now anthropometric 0.55–1.6 × expected segment length only. Newest clip c9ee9fa6 → Legal 11.9° (but view is front-on
  and release hand leaves the frame top ≈ f185–190; BR 209 = follow-through). "bumrah" clip: players ~60 px → unusable.
  Archive spinner still false Illegal 32.3° (arm/non-striker overlap) — don't demo it.
- New `components/VirtualSkeleton.jsx` (clean skeleton, bowling arm highlighted, elbow angle, dashed straight-arm
  reference + bend wedge) and `components/ExtensionVisual.jsx` on Legality: most-bent vs release, Δ gauge vs 15°,
  step-through player. Studio sidebar shows the virtual skeleton of the current frame. LegalityResult adds min_frame, br_used.

## UI fixes (2026-11-20)
- Manual elbow crop now centred on the shoulder with half-size = 1.15 × arm reach (union of ±15 tracked frames),
  so the hand stays in view in any arm position (verified at frame 958 where it used to be cut off).
- Biomechanics tables: description + typical range per metric (`src/metricInfo.js`, coaching guidance) and
  in range / outside tags.
- Selected-state fix: 0.25x/0.5x/1x and suggested-frame buttons used two clashing bg classes; now exclusive
  classes + aria-pressed.

## Bowler selection, L/R mirroring, re-track (2026-11-20)
- Bowler score = coverage × relative size × (1 + 0.3·travel + 2·depth): the main, large, persistent person wins
  (image motion alone failed when the camera pans — "dale" picked a background person). dale coverage 18% → 98%
  from frame 0; 0ea3f49a start 490 → 143 (frames before are a black intro).
- `POST /sessions/{id}/reprocess` + History "Re-track" button; backend re-queues jobs left queued/processing at startup.
- Release search window = from 25% of the TRACKED span (not 30% of the clip). Side-on (selected AND detected):
  either wrist may be the raised arm; frame-by-frame left/right relabelling from the release outward by elbow+wrist
  continuity (`phase_detector.fix_arm_label_swap`), warning lists the frames.
- Manual tool: AI points shown as labelled S/E/W rings + "Use AI points" prefill (points were correct, just invisible).
- Results: 240098ab Legal 2.7° (BR 959 vs real ~965), 0ea3f49a Legal 0.0° score 64.6, dale Legal 6.9°
  (front-on clip uploaded as side-on — guard keeps side-on corrections off), Sample Spin BR 90 = GT.
- Known: archive spinner 4397a622 still false Illegal 32.3° (arm overlaps non-striker); no unit test yet for the relabelling.

## Speed, trained release detector, view auto-correct, redesign (2026-11-20)
- Speed: frame-skipping tried and rejected (coverage 86% -> 40%). Kept: repeated-frame reuse in YOLO and MediaPipe
  passes (`person_tracker.is_repeat`). Measured: 240098ab 108 s, dale 91 s (old YOLO stage alone: 90 s on dale).
- Trained release-frame detector: `training/extract_release_data.py` (278 annotated releases, pose on GT bowler box),
  `app/ml/features.py` (69 scale/fps-free features + temporal context), `training/train_release_model.py`
  (HistGradientBoosting, split by video; NOTE the archive split has no 'val' videos -> default settings),
  `training/evaluate_release.py` -> `training/release_metrics.json`. Test (78 deliveries): rule within ±2 f 29%,
  model-only 59% (median 1 f), hybrid used in app (rule locates, model refines ±0.5 s) 54%. Model-only failed on
  long user clips (trained on 4.5 s windows), so the app uses the hybrid. Model file: backend/models/release_model.joblib.
- Camera view auto-corrected to the detected view unless the user sets it in Overview (`view_locked`).
- Front/rear legality: arm segments must be ≥ 75% of anthropometric length (0.70 gave a false Illegal on Dale Steyn).
  Verdicts: 240098ab Legal 5.5° (BR 958), dale Legal 12.9°, c9ee9fa6 Legal 10.7°, archar Unavailable (use manual).
- Manual tool: automatic S/E/W points shown only on the two calculation frames (most bent, release).
- New visual identity ("cricket scorebook"): cream paper, ink-bordered scorecards with offset shadow, ball-red header
  band + seam logo, ink tab bar, Barlow Condensed scoreboard type, IBM Plex Sans body. Implemented by re-mapping the
  Tailwind slate/emerald/amber/rose/sky/fuchsia scales in `src/index.css` (@theme), plus new header/Card/Kpi/Seam.

## Legality always predicts (user request, 2026-11-20)
- Tiered elbow-frame filter instead of refusing: high (vis ≥ .5, view-specific arm length ≥ .55 side / .75 front),
  medium (≥ .55 any view), low (vis ≥ .3, length .35–2.0, only gross glitches). First tier with ≥ 3 frames (low: 2)
  gives the 15° verdict; `LegalityResult.confidence_level` + UI chip. Arm-horizontal not found -> window = 0.2 s
  before release. Unavailable only if no release or no measurable elbow at all.
- Results: user clips all Legal (39764cc6 archer 0.0° medium; side-on 5.5° high; dale 12.9° high). Low-confidence
  verdicts on poor archive/Pexels clips can read Illegal (e.g. Pexels 35.1°) — shown with the red low-confidence chip.

## Net extension = 0 and front-arm bug (2026-11-20)
- 0.0° results are formula-correct: arm already straight (≈172–178°) at horizontal, measured angle drifts down to
  release (foreshortening), so the most-bent frame IS the release. Report now explains this in the notes.
- Bug found: side-on "either wrist" release rule picked the FRONT arm held high at the gather (0ea3f49a BR 518,
  false Illegal 15.0°). Fix: release must be high AND fast (raised arm's angular speed ≥ 50% of the max among raised
  frames). 0ea3f49a -> BR 566, Legal 4.0°. Label-swap window extended to 1.0 s before release.
- Not validated: no confirmed illegal (thrown) deliveries are available, so detection of real throws is untested.
  Suggested validation: record a deliberate bent-then-straightened arm side-on in slow motion.

## Illegal-action test: user video "Chucking Arm Correction" (2026-11-20)
- samples/user/chucking_vs_legal.mp4 (edited short, 30 fps, REAR view). Split: chuck_before_illegal.mp4 (frames
  0–136) and chuck_now_legal.mp4 (375–533). Sessions b9c97d72 (before) / e1d73780 (now).
- Result: the app CANNOT validate this video. Before: rear view, small bowler, motion-blur gap with no pose exactly at
  release (frames 101–109); measured 2D/3D elbow around release is noisy, no clear straightening; auto verdict
  "Legal 0° (low confidence)" — a false negative vs the video's label. Now: zoomed edit cuts the bowler off at the
  frame edge; tracker locked onto a background player; no release -> Unavailable.
- Fix kept: arm-horizontal search = fixed 0.7 s before release (not FFC-relative; a wrong FFC truncated the window).
- Open issue: stature H is global; in rear/front clips the bowler's size changes a lot, so arm-length checks
  (fraction of 0.186H / 0.146H) misjudge far frames. Needs a per-frame local scale (e.g. rolling torso length).
- Valid test still needed: a SIDE-ON, high-fps clip with a deliberate throw vs a straight-arm delivery.

## Legality validated on expert-labelled data (2026-11-20)
- Dataset: github.com/Debopom/Illegal-Bowling-Action-Detection (MIT; paper arXiv 2610.07223) -> samples/legality_dataset/
  36 labelled clips (21 legal, 15 illegal), 4K 30 fps, single bowler, side/front/back views; labels in bowling-result.ods.
- Script: `backend/training/evaluate_legality.py` (same pipeline as an upload; pose cached in training/legality_cache/;
  results in training/legality_results.json).
- Bug found + fixed: legality window started at the FIRST upper-arm-above-horizontal frame, i.e. the gather/loading
  swing (bent elbow) -> fake 35–55° on legal bowlers. Now = LAST upward crossing of horizontal before release (ICC).
- Result after fix: **33/36 correct (91.7%)**; illegal caught 14/15 (93.3%); legal passed 19/21 (90.5%).
  Errors: clip 6 legal->Illegal 15.9° (borderline), clip 9 legal->Illegal 26.0° (front view), clip 36 illegal->Legal 5.8°
  (front view). Clip 30 correct but Δ=141.4° (implausible magnitude -> landmark glitch inside the window).
- Caveat: the fix was found while inspecting clip 1 of this same set; it is a rule correction (ICC definition), not a
  tuned threshold, but a fully independent test set would be stronger. Paper's own system: 91.96% accuracy.

## Demo + validation page + git (2026-11-20)
- Demo sessions in History (expert-labelled dataset clips): "DEMO illegal action" (#19, Illegal 32.7°),
  "DEMO illegal action 2" (#31, Illegal 34.1°), "DEMO legal action" (#1, Legal 0.0°), "DEMO legal action 2" (#11, Legal 3.8°).
- `GET /api/validation` + `frontend/src/pages/Validation.jsx` (header "Validation" button): accuracy tiles, confusion
  matrix, per-clip table, release-detector comparison, data sources + caveats.
- Git repo initialised (branch main, local identity for this repo only), first commit 790d003. .gitignore excludes
  videos/datasets (archive/, samples/), storage/, venv, node_modules, auto-downloaded weights, training caches.

## Tracking jumped to batsman at release (2026-11-21)
- Session 0eec8486 (wide side-on, 1661 frames): ByteTrack swapped IDs when the bowler ran past the batsman (~540–600);
  skeleton then stayed on the standing batsman. Fix `person_tracker.resolve_overlap_swaps`: after each box overlap
  (IoU > 0.25) keep the candidate that continues the bowler's pre-overlap constant-velocity motion; inside the
  overlap pick per frame the box nearer the prediction. Test added (23/23).
- After re-track: skeleton on the bowler 568→715; release detected 715 vs visual ≈ 709–711 (~5 frames late, 50 fps);
  verdict Legal. Other copies of this clip (0ea3f49a, a9ff15d6) still hold old tracking — use History "Re-track".

## Docs
- README rewritten (2026-11-20): full install incl. torch CPU + ultralytics `--no-deps`, run, tests, recording tips.
  requirements.txt no longer lists torch (installed via README step).

## Known limits / TODO
- Foot-contact detection assumes a static camera; handheld/panning footage needs manual BFC/FFC (camera-motion compensation = future work).
- Score bands are coaching heuristics (documented in code), not validated norms.
- Ball tracker doesn't mask other people (only bowler) — false candidates in busy scenes; linearity gate rejects them.
- Shoulder "late arm" and elbow-velocity thresholds are screening heuristics, not literature-validated cut-offs.
- Rear/front view: BFC/FFC from foot-stillness is weak (foot moves in depth) → detected 85/87, too close; user can edit.
- Side-on broadcast clip: bowler overlaps non-striker at crease → tracking breaks. Robust fix = person detector + tracker (e.g. YOLO + ByteTrack, adds PyTorch).
- Archive footage is 30 fps → release blur; elbow at BR unreliable (rear view 131°).
- Variable-frame-rate phone videos may drift canvas sync slightly.

## Log
- 2026-11-20: Turn 1 design. M1 code + tests; Node LTS installed via winget.
- 2026-11-20: M1 validated on archive clips; bowler tracking + hint + BR fix.
