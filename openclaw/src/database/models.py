"""
Database models for the Sportsbook/Arbitrage Hunter ingestion system.

Defines SQLAlchemy-style models and SQL schema for events and odds.
"""

import json
import sqlite3
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional


class MarketType(str, Enum):
    """Types of betting markets."""
    MONEYLINE = "moneyline"
    SPREAD = "spread"
    TOTAL = "total"
    BINARY = "binary"  # For prediction markets


class SourceType(str, Enum):
    """Types of data sources."""
    SPORTSBOOK = "sportsbook"
    PREDICTION_MARKET = "prediction_market"


@dataclass
class Event:
    """
    Represents a sporting event or prediction market event.
    
    Attributes:
        event_id: Unique identifier (UUID)
        sport: Sport category (NBA, NFL, Politics, etc.)
        teams: List of teams/participants
        start_time: Event start time (ISO8601)
        market_type: Type of market (moneyline, spread, total, binary)
        source: Original source of the event
        source_event_id: ID from the original source
        title: Human-readable event title
        category: Event category
        status: Event status (upcoming, live, completed, cancelled)
        created_at: When record was created
        updated_at: When record was last updated
        metadata: Additional JSON metadata
    """
    event_id: str
    sport: str
    teams: List[str]
    start_time: datetime
    market_type: str
    source: str
    source_event_id: str
    title: str
    category: Optional[str] = None
    status: str = "upcoming"
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    metadata: Optional[Dict[str, Any]] = None
    
    def __post_init__(self):
        """Convert teams to list if stored as JSON string."""
        if isinstance(self.teams, str):
            self.teams = json.loads(self.teams)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for database insertion."""
        return {
            "event_id": self.event_id,
            "sport": self.sport,
            "teams": json.dumps(self.teams) if self.teams else "[]",
            "start_time": self.start_time.isoformat() if isinstance(self.start_time, datetime) else self.start_time,
            "market_type": self.market_type,
            "source": self.source,
            "source_event_id": self.source_event_id,
            "title": self.title,
            "category": self.category,
            "status": self.status,
            "created_at": self.created_at.isoformat() if isinstance(self.created_at, datetime) else self.created_at,
            "updated_at": self.updated_at.isoformat() if isinstance(self.updated_at, datetime) else self.updated_at,
            "metadata": json.dumps(self.metadata) if self.metadata else None,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Event":
        """Create Event from database row."""
        return cls(
            event_id=data["event_id"],
            sport=data["sport"],
            teams=json.loads(data["teams"]) if isinstance(data["teams"], str) else data["teams"],
            start_time=datetime.fromisoformat(data["start_time"]) if isinstance(data["start_time"], str) else data["start_time"],
            market_type=data["market_type"],
            source=data["source"],
            source_event_id=data["source_event_id"],
            title=data["title"],
            category=data.get("category"),
            status=data.get("status", "upcoming"),
            created_at=datetime.fromisoformat(data["created_at"]) if isinstance(data["created_at"], str) else data["created_at"],
            updated_at=datetime.fromisoformat(data["updated_at"]) if isinstance(data["updated_at"], str) else data["updated_at"],
            metadata=json.loads(data["metadata"]) if data.get("metadata") else None,
        )
    
    @classmethod
    def create(
        cls,
        sport: str,
        teams: List[str],
        start_time: datetime,
        market_type: str,
        source: str,
        source_event_id: str,
        title: str,
        **kwargs
    ) -> "Event":
        """Create a new Event with auto-generated UUID."""
        return cls(
            event_id=str(uuid.uuid4()),
            sport=sport,
            teams=teams,
            start_time=start_time,
            market_type=market_type,
            source=source,
            source_event_id=source_event_id,
            title=title,
            **kwargs
        )


@dataclass
class Odds:
    """
    Represents odds/prices for an event at a specific point in time.
    
    Attributes:
        id: Unique identifier (auto-increment)
        event_id: Reference to Event
        market_type: Type of market
        outcomes: List of outcomes with names and odds
        source: Data source name
        source_type: Type of source (sportsbook or prediction_market)
        timestamp: When these odds were recorded
        url: Deep link to the market
        liquidity: Available liquidity if known
        volume: Trading volume if available
        spread: Point spread if applicable
        total: Over/under total if applicable
        is_live: Whether these are live/in-play odds
        freshness_seconds: How fresh is this data
        metadata: Additional JSON metadata
    """
    event_id: str
    market_type: str
    outcomes: List[Dict[str, Any]]  # [{"name": "Lakers", "odds": 1.85, "source": "..."}, ...]
    source: str
    timestamp: datetime = field(default_factory=datetime.utcnow)
    id: Optional[int] = None
    source_type: Optional[str] = None
    url: Optional[str] = None
    liquidity: Optional[float] = None
    volume: Optional[float] = None
    spread: Optional[float] = None
    total: Optional[float] = None
    is_live: bool = False
    freshness_seconds: Optional[int] = None
    metadata: Optional[Dict[str, Any]] = None
    
    def __post_init__(self):
        """Convert outcomes to list if stored as JSON string."""
        if isinstance(self.outcomes, str):
            self.outcomes = json.loads(self.outcomes)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for database insertion."""
        return {
            "id": self.id,
            "event_id": self.event_id,
            "market_type": self.market_type,
            "outcomes": json.dumps(self.outcomes) if self.outcomes else "[]",
            "source": self.source,
            "source_type": self.source_type,
            "timestamp": self.timestamp.isoformat() if isinstance(self.timestamp, datetime) else self.timestamp,
            "url": self.url,
            "liquidity": self.liquidity,
            "volume": self.volume,
            "spread": self.spread,
            "total": self.total,
            "is_live": self.is_live,
            "freshness_seconds": self.freshness_seconds,
            "metadata": json.dumps(self.metadata) if self.metadata else None,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Odds":
        """Create Odds from database row."""
        return cls(
            event_id=data["event_id"],
            market_type=data["market_type"],
            outcomes=json.loads(data["outcomes"]) if isinstance(data["outcomes"], str) else data["outcomes"],
            source=data["source"],
            timestamp=datetime.fromisoformat(data["timestamp"]) if isinstance(data["timestamp"], str) else data["timestamp"],
            id=data.get("id"),
            source_type=data.get("source_type"),
            url=data.get("url"),
            liquidity=data.get("liquidity"),
            volume=data.get("volume"),
            spread=data.get("spread"),
            total=data.get("total"),
            is_live=data.get("is_live", False),
            freshness_seconds=data.get("freshness_seconds"),
            metadata=json.loads(data["metadata"]) if data.get("metadata") else None,
        )
    
    def get_best_odds(self, outcome_name: str) -> Optional[float]:
        """Get odds for a specific outcome."""
        for outcome in self.outcomes:
            if outcome.get("name") == outcome_name:
                return outcome.get("odds")
        return None
    
    def to_normalized_format(self) -> Dict[str, Any]:
        """
        Convert to the normalized format used by the arbitrage system.
        
        Returns:
            Normalized odds dictionary matching the specification.
        """
        return {
            "event_id": self.event_id,
            "market_type": self.market_type,
            "outcomes": self.outcomes,
            "source": self.source,
            "timestamp": self.timestamp.isoformat() if isinstance(self.timestamp, datetime) else self.timestamp,
            "url": self.url,
            "liquidity": self.liquidity,
            "is_live": self.is_live,
        }


# SQL Schema for creating tables
EVENTS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS events (
    event_id TEXT PRIMARY KEY,
    sport TEXT NOT NULL,
    teams TEXT NOT NULL,  -- JSON array
    start_time TEXT NOT NULL,  -- ISO8601 timestamp
    market_type TEXT NOT NULL,
    source TEXT NOT NULL,
    source_event_id TEXT NOT NULL,
    title TEXT NOT NULL,
    category TEXT,
    status TEXT DEFAULT 'upcoming' CHECK (status IN ('upcoming', 'live', 'completed', 'cancelled')),
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
    metadata TEXT  -- JSON blob
);

CREATE INDEX IF NOT EXISTS idx_events_sport ON events(sport);
CREATE INDEX IF NOT EXISTS idx_events_start_time ON events(start_time);
CREATE INDEX IF NOT EXISTS idx_events_source ON events(source);
CREATE INDEX IF NOT EXISTS idx_events_status ON events(status);
"""

ODDS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS odds (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id TEXT NOT NULL,
    market_type TEXT NOT NULL,
    outcomes TEXT NOT NULL,  -- JSON array
    source TEXT NOT NULL,
    source_type TEXT,  -- 'sportsbook' or 'prediction_market'
    timestamp TEXT DEFAULT CURRENT_TIMESTAMP,  -- ISO8601
    url TEXT,
    liquidity REAL,
    volume REAL,
    spread REAL,
    total REAL,
    is_live BOOLEAN DEFAULT FALSE,
    freshness_seconds INTEGER,
    metadata TEXT,  -- JSON blob
    FOREIGN KEY (event_id) REFERENCES events(event_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_odds_event_id ON odds(event_id);
CREATE INDEX IF NOT EXISTS idx_odds_source ON odds(source);
CREATE INDEX IF NOT EXISTS idx_odds_timestamp ON odds(timestamp);
CREATE INDEX IF NOT EXISTS idx_odds_event_source ON odds(event_id, source);
"""

INGESTION_LOG_SQL = """
CREATE TABLE IF NOT EXISTS ingestion_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    source TEXT NOT NULL,
    start_time TEXT DEFAULT CURRENT_TIMESTAMP,  -- ISO8601
    end_time TEXT,  -- ISO8601
    status TEXT DEFAULT 'running' CHECK (status IN ('running', 'success', 'partial', 'failed')),
    events_fetched INTEGER DEFAULT 0,
    events_normalized INTEGER DEFAULT 0,
    events_stored INTEGER DEFAULT 0,
    errors TEXT,  -- JSON array of error messages
    metadata TEXT  -- JSON blob
);

CREATE INDEX IF NOT EXISTS idx_ingestion_run_id ON ingestion_log(run_id);
CREATE INDEX IF NOT EXISTS idx_ingestion_source ON ingestion_log(source);
CREATE INDEX IF NOT EXISTS idx_ingestion_time ON ingestion_log(start_time);
"""

TRIGGERS_SQL = """
-- Update events timestamp trigger
CREATE TRIGGER IF NOT EXISTS update_events_timestamp 
AFTER UPDATE ON events
BEGIN
    UPDATE events SET updated_at = CURRENT_TIMESTAMP WHERE event_id = NEW.event_id;
END;

-- Cleanup old records trigger (can be called manually)
CREATE TRIGGER IF NOT EXISTS cleanup_old_odds
AFTER INSERT ON odds
WHEN (SELECT COUNT(*) FROM odds) > 100000
BEGIN
    DELETE FROM odds WHERE timestamp < datetime('now', '-7 days');
END;
"""


def create_tables(db_path: str):
    """
    Create all tables in the database.
    
    Args:
        db_path: Path to the SQLite database file
    """
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    
    conn = sqlite3.connect(db_path)
    try:
        # Enable WAL mode
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA foreign_keys = ON")
        
        # Create tables
        conn.executescript(EVENTS_TABLE_SQL)
        conn.executescript(ODDS_TABLE_SQL)
        conn.executescript(INGESTION_LOG_SQL)
        conn.executescript(TRIGGERS_SQL)
        
        conn.commit()
    finally:
        conn.close()


def drop_tables(db_path: str):
    """
    Drop all ingestion tables (useful for testing).
    
    Args:
        db_path: Path to the SQLite database file
    """
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("DROP TABLE IF EXISTS odds")
        conn.execute("DROP TABLE IF EXISTS events")
        conn.execute("DROP TABLE IF EXISTS ingestion_log")
        conn.commit()
    finally:
        conn.close()
