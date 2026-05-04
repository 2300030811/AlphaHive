"""
AlphaHive — Database Layer
==========================
Async SQLAlchemy setup with PostgreSQL for signal history,
swarm agent decisions, and watchlist management.

Tables:
  1. signals          — Final synthesized signals per stock
  2. swarm_decisions  — Individual agent decisions (Round 1 + 2)
  3. watchlist_stocks — User watchlist (initialized with Nifty 50)

For educational purposes only. Not investment advice.
AlphaHive is not SEBI-registered. All trading decisions are your own.
"""

import os
import uuid
import logging
from datetime import datetime, timezone

from dotenv import load_dotenv
from sqlalchemy import (
    Column, String, Float, Integer, Boolean, Text, DateTime,
    ForeignKey, JSON, Index, text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    create_async_engine,
    async_sessionmaker,
)
from sqlalchemy.orm import DeclarativeBase, relationship

load_dotenv()
logger = logging.getLogger("alphahive.database")

# ---------------------------------------------------------------------------
# Database URL — from .env
# ---------------------------------------------------------------------------
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://user:password@localhost/alphahive",
)

# For SQLite fallback during development (no PostgreSQL needed for Week 1)
# If DATABASE_URL starts with "sqlite", swap the driver.
if DATABASE_URL.startswith("sqlite"):
    engine = create_async_engine(DATABASE_URL, echo=False)
else:
    engine = create_async_engine(
        DATABASE_URL,
        echo=False,
        pool_size=10,
        max_overflow=20,
        pool_pre_ping=True,
    )

async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


# ---------------------------------------------------------------------------
# Base class
# ---------------------------------------------------------------------------
class Base(DeclarativeBase):
    """Declarative base for all AlphaHive models."""
    pass


# ---------------------------------------------------------------------------
# Table 1: signals
# ---------------------------------------------------------------------------
class Signal(Base):
    """
    Stores the final synthesized AlphaHive signal for a stock.
    Each row = one complete analysis run (swarm + specialist + debate).
    """
    __tablename__ = "signals"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ticker = Column(String(20), nullable=False, index=True)
    company = Column(String(100), nullable=False)
    sector = Column(String(50), nullable=False)
    timestamp = Column(DateTime(timezone=True), nullable=False, index=True)

    # Final synthesized signal
    final_call = Column(String(10), nullable=False)           # BULLISH / BEARISH / NEUTRAL
    bullish_probability = Column(Float, nullable=False)
    risk_level = Column(String(10), nullable=False)           # LOW / MEDIUM / HIGH
    confidence = Column(String(10), nullable=False)           # LOW / MEDIUM / HIGH

    # Plain English explanation (the product soul)
    explanation_line1 = Column(Text, nullable=True)
    explanation_line2 = Column(Text, nullable=True)
    explanation_line3 = Column(Text, nullable=True)

    # Complete raw signal JSON (AlphaHiveSignal from AGENTS.md)
    raw_signal_json = Column(JSON, nullable=True)

    # Timestamps
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    swarm_decisions = relationship("SwarmDecision", back_populates="signal", cascade="all, delete-orphan")

    # Composite index for fast lookups by ticker + time
    __table_args__ = (
        Index("ix_signals_ticker_timestamp", "ticker", "timestamp"),
    )

    def __repr__(self) -> str:
        return f"<Signal {self.ticker} {self.final_call} {self.bullish_probability}%>"


# ---------------------------------------------------------------------------
# Table 2: swarm_decisions
# ---------------------------------------------------------------------------
class SwarmDecision(Base):
    """
    Stores individual agent decisions from the 80-agent swarm.
    Two rows per agent per analysis run (Round 1 + Round 2).
    This is what makes AlphaHive's crowd behavior explainable.
    """
    __tablename__ = "swarm_decisions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    signal_id = Column(
        UUID(as_uuid=True),
        ForeignKey("signals.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Agent identity
    agent_name = Column(String(50), nullable=False)           # e.g. "Panic_Seller_1"
    agent_type = Column(String(20), nullable=False)           # retail / institutional / algo / news_reactor

    # Decision
    round_number = Column(Integer, nullable=False)            # 1 or 2
    action = Column(String(10), nullable=False)               # buy / sell / hold
    confidence = Column(Float, nullable=False)                # 0.0 - 1.0
    reasoning = Column(Text, nullable=True)                   # Why the agent decided this

    # Timestamps
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    signal = relationship("Signal", back_populates="swarm_decisions")

    # Index for fast query by signal + round
    __table_args__ = (
        Index("ix_swarm_signal_round", "signal_id", "round_number"),
    )

    def __repr__(self) -> str:
        return f"<SwarmDecision {self.agent_name} R{self.round_number} {self.action}>"


# ---------------------------------------------------------------------------
# Table 3: watchlist_stocks
# ---------------------------------------------------------------------------
class WatchlistStock(Base):
    """
    Stores the user's watchlist of stocks to monitor.
    Pre-populated with Nifty 50 stocks.
    """
    __tablename__ = "watchlist_stocks"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ticker = Column(String(20), nullable=False, unique=True)
    company = Column(String(100), nullable=False)
    sector = Column(String(50), nullable=False)
    is_active = Column(Boolean, nullable=False, default=True)
    added_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    def __repr__(self) -> str:
        return f"<WatchlistStock {self.ticker} active={self.is_active}>"


# ---------------------------------------------------------------------------
# Database lifecycle functions
# ---------------------------------------------------------------------------
async def create_all() -> None:
    """Create all tables in the database. Idempotent — safe to call repeatedly."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database tables created successfully")


async def drop_all() -> None:
    """Drop all tables. Use with caution — only for development resets."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    logger.warning("All database tables dropped")


async def get_db() -> AsyncSession:
    """
    FastAPI dependency — yields an async database session.
    
    Usage in FastAPI:
        @app.get("/example")
        async def example(db: AsyncSession = Depends(get_db)):
            ...
    """
    async with async_session() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def check_connection() -> bool:
    """Test database connectivity. Returns True if connected, False otherwise."""
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception as e:
        logger.error(f"Database connection failed: {e}")
        return False
