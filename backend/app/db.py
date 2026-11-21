"""SQLAlchemy models + repository. Swap DATABASE_URL for PostgreSQL."""
import json
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import DateTime, Float, String, Text, create_engine, select
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

from .config import DATABASE_URL

_kw = {"connect_args": {"check_same_thread": False}} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, **_kw)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


class BowlingSession(Base):
    __tablename__ = "sessions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
    bowler_name: Mapped[Optional[str]] = mapped_column(String(120))
    bowling_arm: Mapped[str] = mapped_column(String(8))
    perspective: Mapped[str] = mapped_column(String(10))
    filename: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(12), default="queued")
    progress: Mapped[float] = mapped_column(Float, default=0.0)
    stage: Mapped[Optional[str]] = mapped_column(String(60))
    error: Mapped[Optional[str]] = mapped_column(Text)
    technique_score: Mapped[Optional[float]] = mapped_column(Float)
    legality_class: Mapped[Optional[str]] = mapped_column(String(60))
    manual_phases: Mapped[Optional[str]] = mapped_column(Text)   # JSON {phase: frame}
    calibration: Mapped[Optional[str]] = mapped_column(Text)     # JSON (M3)
    bowler_hint: Mapped[Optional[str]] = mapped_column(Text)     # JSON [time_s, x_norm, y_norm]
    manual_timing: Mapped[Optional[str]] = mapped_column(Text)   # JSON ManualTiming (M3)
    manual_elbow: Mapped[Optional[str]] = mapped_column(Text)    # JSON ManualElbow (digitised arm)
    view_locked: Mapped[Optional[str]] = mapped_column(String(8))  # "1" = user chose the view explicitly


Base.metadata.create_all(engine)


def _migrate():
    """Lightweight additive migration: add columns introduced after the table was created."""
    from sqlalchemy import inspect, text
    have = {c["name"] for c in inspect(engine).get_columns("sessions")}
    with engine.begin() as con:
        for col in BowlingSession.__table__.columns:
            if col.name not in have:
                con.execute(text(f'ALTER TABLE sessions ADD COLUMN {col.name} {col.type.compile(engine.dialect)}'))


_migrate()


class Repo:
    """Thin repository so routes/pipeline never touch SQL directly."""

    def __init__(self):
        self.db = SessionLocal()

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.db.close()

    def get(self, sid: str) -> Optional[BowlingSession]:
        return self.db.get(BowlingSession, sid)

    def add(self, s: BowlingSession):
        self.db.add(s)
        self.db.commit()

    def update(self, sid: str, **fields):
        s = self.get(sid)
        if s:
            for k, v in fields.items():
                setattr(s, k, v)
            self.db.commit()
        return s

    def list(self, bowler_name: Optional[str] = None):
        q = select(BowlingSession).order_by(BowlingSession.created_at.desc())
        if bowler_name:
            q = q.where(BowlingSession.bowler_name == bowler_name)
        return list(self.db.scalars(q))

    def delete(self, sid: str):
        s = self.get(sid)
        if s:
            self.db.delete(s)
            self.db.commit()

    @staticmethod
    def phases_of(s: BowlingSession) -> dict:
        return json.loads(s.manual_phases) if s.manual_phases else {}
