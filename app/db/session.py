from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

from app.core.config import settings

_engine: Engine | None = None


def get_engine() -> Engine | None:
    global _engine
    if _engine is not None:
        return _engine
    if not settings.database_url:
        return None
    _engine = create_engine(
        settings.database_url,
        pool_pre_ping=True,
        future=True,
        echo=settings.database_echo,
    )
    return _engine

