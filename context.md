# BowlSense AI — Context

**Goal:** Real CV web app analyzing cricket bowling video (no fake data; show `Unavailable` when not measurable).

**Stack:** Python 3.11, FastAPI, Pydantic v2, SQLAlchemy + SQLite, OpenCV, MediaPipe Pose (complexity=2, 33 lm), NumPy, SciPy | React (Vite), Tailwind, Recharts, `<canvas>` overlay.

**Key rules**
- Visibility < 0.5 on required landmarks → metric `Unavailable (Low Confidence)`.
- Legality = preliminary 2D screening, NOT ICC. Injury = not medical diagnosis.
- Speed km/h only if Side-on + calibration + valid ball track.
- Frontend draws skeleton from JSON (no server re-encode).
- Phase frames editable → metrics recomputed.

**Workflow:** Turn 1 = design only (DESIGN.md). Then Milestones 1–4. Wait for approval between steps.
**User prefs:** short answers, low tokens, VS Code open, update progress.md each step.

**Key docs:** `DESIGN.md` (architecture, formulas, API contract), `progress.md` (status, deviations, validation).
**Status (2026-11-20):** M1–M4 complete. Run: `.claude/launch.json` (backend :8000 — restart manually after edits; frontend :5173).
**Data:** `archive/` = 40 broadcast videos + JSON (GT release frames, bowler boxes); `samples/` = cut test clips.
