"""Database schema and persistence (SQLite locally, Postgres/Supabase in the cloud)."""

from __future__ import annotations

import os
from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    create_engine,
    func,
    insert,
    select,
    text,
    update,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.engine import Engine

from .evaluate import Evaluation
from .models import Heating, Listing, Market, Ownership

metadata = MetaData()
JsonType = JSON().with_variant(JSONB(), "postgresql")

listings = Table(
    "listings",
    metadata,
    Column("id", String, primary_key=True),
    Column("source", String, nullable=False),
    Column("source_id", String, nullable=False),
    Column("url", Text, nullable=False),
    Column("title", Text),
    Column("price", Float),
    Column("area", Float),
    Column("price_per_m2", Float),
    Column("rooms", Integer),
    Column("floor", Integer),
    Column("floors_total", Integer),
    Column("build_year", Integer),
    Column("market", String),
    Column("has_balcony", Boolean),
    Column("has_elevator", Boolean),
    Column("heating", String),
    Column("ownership", String),
    Column("completion_date", String),
    Column("district", String),
    Column("location_text", Text),
    Column("lat", Float),
    Column("lon", Float),
    Column("coords_approximate", Boolean, nullable=False, default=False),
    Column("description", Text),
    Column("images", JsonType),
    Column("is_private_owner", Boolean),
    Column("agency", Text),
    Column("published_at", DateTime(timezone=True)),
    Column("details_fetched", Boolean, nullable=False, default=False),
    Column("verdict", String, index=True),
    Column("score", Integer),
    Column("evaluation", JsonType),
    Column("group_id", String, index=True),
    Column("first_seen_at", DateTime(timezone=True), nullable=False),
    Column("last_seen_at", DateTime(timezone=True), nullable=False),
    Column("active", Boolean, nullable=False, default=True),
    Column("notified_at", DateTime(timezone=True)),
    Column("notified_price", Float),
    Column("raw", JsonType),
)

price_history = Table(
    "price_history",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("listing_id", String, ForeignKey("listings.id", ondelete="CASCADE"), index=True),
    Column("price", Float, nullable=False),
    Column("seen_at", DateTime(timezone=True), nullable=False),
)

settings = Table(
    "settings",
    metadata,
    Column("key", String, primary_key=True),
    Column("value", JsonType),
    Column("updated_at", DateTime(timezone=True), nullable=False),
)

runs = Table(
    "runs",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("started_at", DateTime(timezone=True), nullable=False),
    Column("finished_at", DateTime(timezone=True)),
    Column("stats", JsonType),
)

LISTING_FIELDS = [
    "source",
    "source_id",
    "url",
    "title",
    "price",
    "area",
    "rooms",
    "floor",
    "floors_total",
    "build_year",
    "market",
    "has_balcony",
    "has_elevator",
    "heating",
    "ownership",
    "completion_date",
    "district",
    "location_text",
    "lat",
    "lon",
    "description",
    "images",
    "is_private_owner",
    "agency",
    "published_at",
    "details_fetched",
    "coords_approximate",
    "raw",
]


def now() -> datetime:
    return datetime.now(UTC)


def make_engine(url: str | None = None) -> Engine:
    url = url or os.environ.get("DATABASE_URL") or "sqlite:///homeseeker.db"
    if url.startswith("postgres://"):
        url = "postgresql://" + url.removeprefix("postgres://")
    if url.startswith("postgresql://"):
        url = "postgresql+psycopg://" + url.removeprefix("postgresql://")
    connect_args: dict[str, Any] = {}
    if url.startswith("postgresql"):
        # Supabase poolers do not support server-side prepared statements.
        connect_args["prepare_threshold"] = None
    return create_engine(url, connect_args=connect_args, future=True)


def init_db(engine: Engine) -> None:
    metadata.create_all(engine)
    if engine.dialect.name == "postgresql":
        # Supabase exposes the public schema over its REST API: lock tables down by
        # default; the web app gets explicit policies later.
        with engine.begin() as conn:
            for table in metadata.sorted_tables:
                conn.execute(text(f'alter table "{table.name}" enable row level security'))


def _to_row(listing: Listing) -> dict[str, Any]:
    row = {f: getattr(listing, f) for f in LISTING_FIELDS}
    for key in ("market", "heating", "ownership"):
        row[key] = row[key].value if row[key] else None
    if isinstance(row["completion_date"], date):
        row["completion_date"] = row["completion_date"].isoformat()
    row["price_per_m2"] = listing.price_per_m2
    return row


def row_to_listing(row: Any) -> Listing:
    m = row._mapping
    data = {f: m[f] for f in LISTING_FIELDS}
    data["market"] = Market(m["market"]) if m["market"] else None
    data["heating"] = Heating(m["heating"]) if m["heating"] else None
    data["ownership"] = Ownership(m["ownership"]) if m["ownership"] else None
    data["completion_date"] = (
        date.fromisoformat(m["completion_date"]) if m["completion_date"] else None
    )
    data["images"] = m["images"] or []
    data["raw"] = m["raw"] or {}
    return Listing(**data)


class Store:
    def __init__(self, engine: Engine):
        self.engine = engine

    # --- settings
    def get_setting(self, key: str, default: Any = None) -> Any:
        with self.engine.connect() as conn:
            row = conn.execute(select(settings.c.value).where(settings.c.key == key)).first()
        return row[0] if row else default

    def set_setting(self, key: str, value: Any) -> None:
        with self.engine.begin() as conn:
            exists = conn.execute(select(settings.c.key).where(settings.c.key == key)).first()
            stmt = (
                update(settings).where(settings.c.key == key)
                if exists
                else insert(settings).values(key=key)
            )
            conn.execute(stmt.values(value=value, updated_at=now()))

    # --- listings
    def get(self, listing_id: str) -> Any | None:
        with self.engine.connect() as conn:
            return conn.execute(select(listings).where(listings.c.id == listing_id)).first()

    def count(self) -> int:
        with self.engine.connect() as conn:
            return conn.execute(select(func.count()).select_from(listings)).scalar_one()

    def active_candidates(self) -> list[Any]:
        """Active non-rejected listings, used for de-duplication."""
        with self.engine.connect() as conn:
            return conn.execute(
                select(listings).where(
                    listings.c.active.is_(True), listings.c.verdict != "rejected"
                )
            ).fetchall()

    def upsert(self, listing: Listing, evaluation: Evaluation, group_id: str | None) -> str:
        """Insert or update a listing. Returns 'new', 'price_changed' or 'updated'."""
        ts = now()
        row = _to_row(listing)
        row.update(
            verdict=evaluation.verdict.value,
            score=evaluation.score,
            evaluation=evaluation.to_dict(),
            group_id=group_id,
            last_seen_at=ts,
            active=True,
        )
        with self.engine.begin() as conn:
            old = conn.execute(select(listings.c.price).where(listings.c.id == listing.id)).first()
            if old is None:
                conn.execute(insert(listings).values(id=listing.id, first_seen_at=ts, **row))
                status = "new"
            else:
                conn.execute(update(listings).where(listings.c.id == listing.id).values(**row))
                status = "price_changed" if listing.price and old[0] != listing.price else "updated"
            if listing.price and status != "updated":
                conn.execute(
                    insert(price_history).values(
                        listing_id=listing.id, price=listing.price, seen_at=ts
                    )
                )
        return status

    def touch(self, listing_id: str) -> None:
        with self.engine.begin() as conn:
            conn.execute(
                update(listings)
                .where(listings.c.id == listing_id)
                .values(last_seen_at=now(), active=True)
            )

    def pending_notifications(self, verdicts: list[str]) -> list[Any]:
        """Active listings with a notifiable verdict that were never notified, best first."""
        with self.engine.connect() as conn:
            return conn.execute(
                select(listings)
                .where(
                    listings.c.active.is_(True),
                    listings.c.notified_at.is_(None),
                    listings.c.verdict.in_(verdicts),
                )
                .order_by(listings.c.score.desc())
            ).fetchall()

    def mark_notified(self, listing_id: str, price: float | None) -> None:
        with self.engine.begin() as conn:
            conn.execute(
                update(listings)
                .where(listings.c.id == listing_id)
                .values(notified_at=now(), notified_price=price)
            )

    def group_notified(self, group_id: str) -> bool:
        with self.engine.connect() as conn:
            return (
                conn.execute(
                    select(listings.c.id).where(
                        listings.c.group_id == group_id, listings.c.notified_at.is_not(None)
                    )
                ).first()
                is not None
            )

    def deactivate_stale(self, sources: list[str], older_than: datetime) -> int:
        with self.engine.begin() as conn:
            res = conn.execute(
                update(listings)
                .where(
                    listings.c.source.in_(sources),
                    listings.c.active.is_(True),
                    listings.c.last_seen_at < older_than,
                )
                .values(active=False)
            )
        return res.rowcount or 0

    # --- runs
    def start_run(self) -> int:
        with self.engine.begin() as conn:
            return conn.execute(insert(runs).values(started_at=now())).inserted_primary_key[0]

    def finish_run(self, run_id: int, stats: dict) -> None:
        with self.engine.begin() as conn:
            conn.execute(
                update(runs).where(runs.c.id == run_id).values(finished_at=now(), stats=stats)
            )
