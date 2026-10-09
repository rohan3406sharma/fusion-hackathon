"""SQLite persistence for user-defined scenarios (SQLAlchemy). Built-in scenarios are seeded from data/scenarios.json."""
from __future__ import annotations

import json
from datetime import datetime, timezone

from sqlalchemy import Boolean, String, Text, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

from .config import get_settings


class Base(DeclarativeBase):
    pass


class ScenarioRow(Base):
    __tablename__ = "scenarios"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    spec_json: Mapped[str] = mapped_column(Text)
    builtin: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[str] = mapped_column(String(40))


_engine = None
_Session = None


def get_engine(url: str | None = None):
    global _engine, _Session
    if _engine is None or url is not None:
        url = url or get_settings().database_url
        kw = {"connect_args": {"check_same_thread": False}} if url.startswith("sqlite") else {}
        if url.endswith(":memory:") or url == "sqlite://":
            from sqlalchemy.pool import StaticPool
            kw["poolclass"] = StaticPool
        _engine = create_engine(url, **kw)
        _Session = sessionmaker(_engine, expire_on_commit=False)
    return _engine


def session() -> Session:
    get_engine()
    return _Session()


def init_db(builtin_scenarios: list[dict]) -> None:
    eng = get_engine()
    Base.metadata.create_all(eng)
    with session() as s:
        for sc in builtin_scenarios:
            sid = sc["id"]
            spec = {k: v for k, v in sc.items() if k not in ("id", "builtin", "synthetic")}
            row = s.get(ScenarioRow, sid)
            if row is None:
                s.add(ScenarioRow(id=sid, name=sc["name"], spec_json=json.dumps(spec), builtin=True,
                                  created_at=datetime.now(timezone.utc).isoformat()))
            elif row.builtin:
                row.spec_json, row.name = json.dumps(spec), sc["name"]
        s.commit()
