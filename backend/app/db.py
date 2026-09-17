"""SQLite data layer: connection handling and schema for the places database."""

import json
from pathlib import Path

from sqlalchemy import JSON, Boolean, Float, Integer, String, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "wishtrip.db"

engine = create_engine(f"sqlite:///{DB_PATH}", connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


class Place(Base):
    __tablename__ = "places"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, index=True)
    lat: Mapped[float] = mapped_column(Float)
    lon: Mapped[float] = mapped_column(Float)
    zone: Mapped[str] = mapped_column(String, index=True)
    category: Mapped[str] = mapped_column(String, index=True)
    subcategory: Mapped[str | None] = mapped_column(String, nullable=True)
    visit_duration_minutes: Mapped[int] = mapped_column(Integer)
    price_level: Mapped[int] = mapped_column(Integer)  # 0 free, 1 budget, 2 mid, 3 premium
    rating: Mapped[float | None] = mapped_column(Float, nullable=True)
    opening_hours: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    hours_unknown: Mapped[bool] = mapped_column(Boolean, default=True)
    tags: Mapped[list] = mapped_column(JSON, default=list)
    suitability: Mapped[list] = mapped_column(JSON, default=list)
    kids_ok: Mapped[bool] = mapped_column(Boolean, default=True)
    seniors_ok: Mapped[bool] = mapped_column(Boolean, default=True)
    dietary_tags: Mapped[list] = mapped_column(JSON, default=list)
    seasonally_closed_months: Mapped[list] = mapped_column(JSON, default=list)
    description: Mapped[str | None] = mapped_column(String, nullable=True)
    source: Mapped[dict] = mapped_column(JSON, default=dict)

    def to_record(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "lat": self.lat,
            "lon": self.lon,
            "zone": self.zone,
            "category": self.category,
            "subcategory": self.subcategory,
            "visit_duration_minutes": self.visit_duration_minutes,
            "price_level": self.price_level,
            "rating": self.rating,
            "opening_hours": json.loads(json.dumps(self.opening_hours or {})),
            "hours_unknown": self.hours_unknown,
            "tags": list(self.tags or []),
            "suitability": list(self.suitability or []),
            "kids_ok": self.kids_ok,
            "seniors_ok": self.seniors_ok,
            "dietary_tags": list(self.dietary_tags or []),
            "seasonally_closed_months": list(self.seasonally_closed_months or []),
            "description": self.description,
            "source": dict(self.source or {}),
        }


def init_db() -> None:
    Base.metadata.create_all(engine)


def load_all_places() -> list[dict]:
    """Load every place as a plain dict. The planner works on dicts, not ORM objects."""
    with SessionLocal() as session:
        return [place.to_record() for place in session.query(Place).all()]
