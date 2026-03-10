"""
Database integration for arbitrage opportunities.

This module provides functions for saving arbitrage opportunities
to the database and querying historical opportunities.
"""

import json
from datetime import datetime
from decimal import Decimal
from typing import List, Optional, Dict, Any

from .models import ArbitrageOpportunity, ArbitrageLeg


# Custom JSON encoder for Decimal values
class DecimalEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Decimal):
            return float(obj)
        return super().default(obj)


def _leg_to_dict(leg: ArbitrageLeg) -> Dict[str, Any]:
    """Convert ArbitrageLeg to dictionary for JSON serialization."""
    return {
        "source": leg.source,
        "source_event_id": leg.source_event_id,
        "side": leg.side,
        "price": float(leg.price),
        "american_odds": leg.american_odds,
        "liquidity": float(leg.liquidity) if leg.liquidity else None,
        "url": leg.url,
        "fees_pct": float(leg.fees_pct),
    }


def save_opportunity(
    opportunity: ArbitrageOpportunity,
    conn=None,
) -> str:
    """
    Save an arbitrage opportunity to the database.
    
    Args:
        opportunity: The arbitrage opportunity to save
        conn: Database connection (optional, will use default if not provided)
        
    Returns:
        The ID of the saved opportunity
    """
    # Import here to avoid circular imports
    if conn is None:
        from shared.db import insert
        use_insert = True
    else:
        use_insert = False
    
    # Prepare data for insertion
    data = {
        "arb_id": opportunity.arb_id,
        "event_title": opportunity.event_title,
        "left_leg": json.dumps(opportunity.left_leg.to_dict() if opportunity.left_leg else {}, cls=DecimalEncoder),
        "right_leg": json.dumps(opportunity.right_leg.to_dict() if opportunity.right_leg else {}, cls=DecimalEncoder),
        "gross_edge_pct": float(opportunity.gross_edge_pct),
        "fees_pct": float(opportunity.fees_pct),
        "slippage_pct": float(opportunity.slippage_pct),
        "net_edge_pct": float(opportunity.net_edge_pct),
        "max_stake": float(opportunity.max_stake),
        "expected_profit": float(opportunity.expected_profit),
        "match_score": float(opportunity.match_score),
        "resolution_confidence": float(opportunity.resolution_confidence),
        "freshness_seconds": opportunity.freshness_seconds,
        "alertable": opportunity.alertable,
        "detected_at": opportunity.detected_at.isoformat(),
        "expires_at": opportunity.expires_at.isoformat() if opportunity.expires_at else None,
        "metadata": json.dumps(opportunity.metadata, cls=DecimalEncoder),
    }
    
    if use_insert:
        from shared.db import insert
        return str(insert("arbitrage_opportunities", data, return_id=True))
    else:
        cursor = conn.execute(
            """
            INSERT INTO arbitrage_opportunities (
                arb_id, event_title, left_leg, right_leg,
                gross_edge_pct, fees_pct, slippage_pct, net_edge_pct,
                max_stake, expected_profit, match_score, resolution_confidence,
                freshness_seconds, alertable, detected_at, expires_at, metadata
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                data["arb_id"],
                data["event_title"],
                data["left_leg"],
                data["right_leg"],
                data["gross_edge_pct"],
                data["fees_pct"],
                data["slippage_pct"],
                data["net_edge_pct"],
                data["max_stake"],
                data["expected_profit"],
                data["match_score"],
                data["resolution_confidence"],
                data["freshness_seconds"],
                data["alertable"],
                data["detected_at"],
                data["expires_at"],
                data["metadata"],
            ),
        )
        return str(cursor.lastrowid)


def save_opportunities(
    opportunities: List[ArbitrageOpportunity],
    conn=None,
) -> List[str]:
    """
    Save multiple arbitrage opportunities to the database.
    
    Args:
        opportunities: List of arbitrage opportunities to save
        conn: Database connection (optional)
        
    Returns:
        List of saved opportunity IDs
    """
    return [save_opportunity(opp, conn) for opp in opportunities]


def get_opportunity_by_id(arb_id: str) -> Optional[ArbitrageOpportunity]:
    """
    Retrieve an arbitrage opportunity by ID.
    
    Args:
        arb_id: The arbitrage opportunity ID
        
    Returns:
        The opportunity if found, None otherwise
    """
    from shared.db import execute
    
    row = execute(
        "SELECT * FROM arbitrage_opportunities WHERE arb_id = ?",
        (arb_id,),
        fetch_one=True,
    )
    
    if not row:
        return None
    
    return _row_to_opportunity(row)


def get_opportunities(
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    min_profit_pct: Optional[float] = None,
    alertable_only: bool = False,
    limit: int = 100,
) -> List[ArbitrageOpportunity]:
    """
    Query arbitrage opportunities with filters.
    
    Args:
        start_date: Filter by detection date (inclusive)
        end_date: Filter by detection date (inclusive)
        min_profit_pct: Minimum net profit percentage
        alertable_only: Only return alertable opportunities
        limit: Maximum number of results
        
    Returns:
        List of matching opportunities
    """
    from shared.db import execute
    
    query = "SELECT * FROM arbitrage_opportunities WHERE 1=1"
    params = []
    
    if start_date:
        query += " AND detected_at >= ?"
        params.append(start_date.isoformat())
    
    if end_date:
        query += " AND detected_at <= ?"
        params.append(end_date.isoformat())
    
    if min_profit_pct is not None:
        query += " AND net_edge_pct >= ?"
        params.append(min_profit_pct)
    
    if alertable_only:
        query += " AND alertable = 1"
    
    query += " ORDER BY detected_at DESC LIMIT ?"
    params.append(limit)
    
    rows = execute(query, tuple(params))
    return [_row_to_opportunity(row) for row in rows]


def get_recent_opportunities(
    hours: int = 24,
    alertable_only: bool = True,
) -> List[ArbitrageOpportunity]:
    """
    Get opportunities detected within the last N hours.
    
    Args:
        hours: Number of hours to look back
        alertable_only: Only return alertable opportunities
        
    Returns:
        List of recent opportunities
    """
    from datetime import timedelta
    
    start_date = datetime.utcnow() - timedelta(hours=hours)
    return get_opportunities(
        start_date=start_date,
        alertable_only=alertable_only,
        limit=100,
    )


def _row_to_opportunity(row: Dict[str, Any]) -> ArbitrageOpportunity:
    """Convert a database row to an ArbitrageOpportunity."""
    # Parse JSON fields
    left_leg_data = json.loads(row.get("left_leg", "{}"))
    right_leg_data = json.loads(row.get("right_leg", "{}"))
    metadata = json.loads(row.get("metadata", "{}"))
    
    # Create legs
    left_leg = ArbitrageLeg(
        source=left_leg_data.get("source", ""),
        source_event_id=left_leg_data.get("source_event_id", ""),
        side=left_leg_data.get("side", ""),
        price=Decimal(str(left_leg_data.get("price", 0))),
        american_odds=left_leg_data.get("american_odds"),
        liquidity=Decimal(str(left_leg_data.get("liquidity"))) if left_leg_data.get("liquidity") else None,
        url=left_leg_data.get("url"),
        fees_pct=Decimal(str(left_leg_data.get("fees_pct", 0))),
    ) if left_leg_data else None
    
    right_leg = ArbitrageLeg(
        source=right_leg_data.get("source", ""),
        source_event_id=right_leg_data.get("source_event_id", ""),
        side=right_leg_data.get("side", ""),
        price=Decimal(str(right_leg_data.get("price", 0))),
        american_odds=right_leg_data.get("american_odds"),
        liquidity=Decimal(str(right_leg_data.get("liquidity"))) if right_leg_data.get("liquidity") else None,
        url=right_leg_data.get("url"),
        fees_pct=Decimal(str(right_leg_data.get("fees_pct", 0))),
    ) if right_leg_data else None
    
    return ArbitrageOpportunity(
        arb_id=row.get("arb_id", ""),
        event_title=row.get("event_title", ""),
        left_leg=left_leg,
        right_leg=right_leg,
        gross_edge_pct=Decimal(str(row.get("gross_edge_pct", 0))),
        fees_pct=Decimal(str(row.get("fees_pct", 0))),
        slippage_pct=Decimal(str(row.get("slippage_pct", 0))),
        net_edge_pct=Decimal(str(row.get("net_edge_pct", 0))),
        max_stake=Decimal(str(row.get("max_stake", 0))),
        expected_profit=Decimal(str(row.get("expected_profit", 0))),
        match_score=Decimal(str(row.get("match_score", 0))),
        resolution_confidence=Decimal(str(row.get("resolution_confidence", 0))),
        freshness_seconds=row.get("freshness_seconds", 0),
        alertable=bool(row.get("alertable", False)),
        detected_at=datetime.fromisoformat(row.get("detected_at", "")) if row.get("detected_at") else datetime.utcnow(),
        expires_at=datetime.fromisoformat(row.get("expires_at", "")) if row.get("expires_at") else None,
        metadata=metadata,
    )


def get_opportunity_stats(
    days: int = 30,
) -> Dict[str, Any]:
    """
    Get statistics on arbitrage opportunities.
    
    Args:
        days: Number of days to analyze
        
    Returns:
        Dictionary with statistics
    """
    from shared.db import execute
    from datetime import timedelta
    
    start_date = (datetime.utcnow() - timedelta(days=days)).isoformat()
    
    # Total opportunities
    total = execute(
        "SELECT COUNT(*) as count FROM arbitrage_opportunities WHERE detected_at >= ?",
        (start_date,),
        fetch_one=True,
    )
    
    # Alertable opportunities
    alertable = execute(
        "SELECT COUNT(*) as count FROM arbitrage_opportunities WHERE detected_at >= ? AND alertable = 1",
        (start_date,),
        fetch_one=True,
    )
    
    # Average profit
    avg_profit = execute(
        "SELECT AVG(net_edge_pct) as avg FROM arbitrage_opportunities WHERE detected_at >= ?",
        (start_date,),
        fetch_one=True,
    )
    
    # Max profit
    max_profit = execute(
        "SELECT MAX(net_edge_pct) as max FROM arbitrage_opportunities WHERE detected_at >= ?",
        (start_date,),
        fetch_one=True,
    )
    
    # By source
    by_source = execute(
        """
        SELECT 
            json_extract(left_leg, '$.source') as source,
            COUNT(*) as count
        FROM arbitrage_opportunities
        WHERE detected_at >= ?
        GROUP BY source
        """,
        (start_date,),
    )
    
    return {
        "total_opportunities": total.get("count", 0) if total else 0,
        "alertable_opportunities": alertable.get("count", 0) if alertable else 0,
        "avg_profit_pct": avg_profit.get("avg", 0) if avg_profit else 0,
        "max_profit_pct": max_profit.get("max", 0) if max_profit else 0,
        "by_source": {row.get("source", "unknown"): row.get("count", 0) for row in by_source} if by_source else {},
        "period_days": days,
    }


def create_arbitrage_table_sql() -> str:
    """
    Get SQL to create the arbitrage_opportunities table.
    
    Returns:
        SQL string for table creation
    """
    return """
    CREATE TABLE IF NOT EXISTS arbitrage_opportunities (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        arb_id TEXT UNIQUE NOT NULL,
        event_title TEXT NOT NULL,
        left_leg TEXT NOT NULL,  -- JSON
        right_leg TEXT NOT NULL,  -- JSON
        gross_edge_pct REAL NOT NULL,
        fees_pct REAL NOT NULL,
        slippage_pct REAL NOT NULL,
        net_edge_pct REAL NOT NULL,
        max_stake REAL NOT NULL,
        expected_profit REAL NOT NULL,
        match_score REAL NOT NULL,
        resolution_confidence REAL NOT NULL,
        freshness_seconds INTEGER NOT NULL,
        alertable INTEGER NOT NULL DEFAULT 0,
        detected_at TIMESTAMP NOT NULL,
        expires_at TIMESTAMP,
        metadata TEXT,  -- JSON
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    
    CREATE INDEX IF NOT EXISTS idx_arb_detected_at ON arbitrage_opportunities(detected_at);
    CREATE INDEX IF NOT EXISTS idx_arb_net_edge ON arbitrage_opportunities(net_edge_pct);
    CREATE INDEX IF NOT EXISTS idx_arb_alertable ON arbitrage_opportunities(alertable);
    CREATE INDEX IF NOT EXISTS idx_arb_expires ON arbitrage_opportunities(expires_at);
    """
