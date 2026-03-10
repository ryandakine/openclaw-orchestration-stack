"""Build complete alert messages from ArbOpportunity objects.

This module coordinates all formatters to build polished Telegram alerts.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from ..formatters.format_profit import format_profit
from ..formatters.format_liquidity import format_liquidity
from ..formatters.format_percent import format_percent, format_win_probability
from ..formatters.format_links import (
    format_markdown_link,
    format_venue_links,
    escape_markdown_v2,
)
from .alert_template import AlertTemplateData

if TYPE_CHECKING:
    from ..arb_opportunity_schema import ArbOpportunity


class AlertFormatter:
    """Formats arbitrage opportunities into alert data."""
    
    def format_opportunity(
        self,
        opportunity: "ArbOpportunity",
    ) -> AlertTemplateData:
        """Format an opportunity into template data.
        
        Args:
            opportunity: The arbitrage opportunity to format
            
        Returns:
            AlertTemplateData ready for rendering
        """
        # Extract leg details
        left_leg = opportunity.left_leg
        right_leg = opportunity.right_leg
        
        # Format event title (truncate if too long)
        event_title = escape_markdown_v2(
            opportunity.event_title[:100] + "..."
            if len(opportunity.event_title) > 100
            else opportunity.event_title
        )
        
        # Format short arb ID (first 8 chars)
        arb_id_short = opportunity.arb_id[:8]
        
        # Format profit and edges
        profit = format_profit(opportunity.expected_profit)
        net_edge = format_percent(opportunity.net_edge_pct)
        gross_edge = format_percent(opportunity.gross_edge_pct)
        fees = format_percent(-opportunity.fees_pct)
        slippage = format_percent(-opportunity.slippage_pct)
        
        # Format sizing
        max_size = format_profit(opportunity.max_size)
        
        # Format match quality
        match_score = format_win_probability(opportunity.match_score)
        resolution_confidence = format_win_probability(opportunity.resolution_confidence)
        freshness = str(opportunity.freshness_seconds)
        
        # Format left leg
        left_venue = escape_markdown_v2(left_leg.get("venue", "Unknown"))
        left_odds = self._format_odds(left_leg.get("odds"))
        left_liquidity = format_liquidity(left_leg.get("liquidity"))
        left_side = escape_markdown_v2(left_leg.get("side", "Unknown"))
        left_url = left_leg.get("url")
        
        # Format right leg
        right_venue = escape_markdown_v2(right_leg.get("venue", "Unknown"))
        right_odds = self._format_odds(right_leg.get("odds"))
        right_liquidity = format_liquidity(right_leg.get("liquidity"))
        right_side = escape_markdown_v2(right_leg.get("side", "Unknown"))
        right_url = right_leg.get("url")
        
        # Format links
        links = format_venue_links(
            left_leg.get("venue", "Left"),
            left_url,
            right_leg.get("venue", "Right"),
            right_url,
        )
        
        # Format expiration time
        if opportunity.expires_at:
            expires_at = opportunity.expires_at.strftime("%Y-%m-%d %H:%M UTC")
        else:
            expires_at = "Unknown"
        
        return AlertTemplateData(
            event_title=event_title,
            arb_id_short=arb_id_short,
            profit=profit,
            net_edge=net_edge,
            gross_edge=gross_edge,
            fees=fees,
            slippage=slippage,
            max_size=max_size,
            match_score=match_score,
            resolution_confidence=resolution_confidence,
            freshness=freshness,
            left_venue=left_venue,
            left_odds=left_odds,
            left_liquidity=left_liquidity,
            left_side=left_side,
            left_url=left_url,
            right_venue=right_venue,
            right_odds=right_odds,
            right_liquidity=right_liquidity,
            right_side=right_side,
            right_url=right_url,
            links=links,
            expires_at=expires_at,
        )
    
    def format_expired(
        self,
        opportunity: "ArbOpportunity",
        duration_seconds: int,
    ) -> AlertTemplateData:
        """Format an expired opportunity into template data.
        
        Args:
            opportunity: The expired arbitrage opportunity
            duration_seconds: How long the opportunity was alive
            
        Returns:
            AlertTemplateData ready for rendering
        """
        # Format event title
        event_title = escape_markdown_v2(
            opportunity.event_title[:100] + "..."
            if len(opportunity.event_title) > 100
            else opportunity.event_title
        )
        
        # Format short arb ID
        arb_id_short = opportunity.arb_id[:8]
        
        # Format profit and edge (as they were)
        profit = format_profit(opportunity.expected_profit)
        net_edge = format_percent(opportunity.net_edge_pct)
        
        # Format duration
        duration = self._format_duration(duration_seconds)
        
        # Create minimal template data for expired alert
        return AlertTemplateData(
            event_title=event_title,
            arb_id_short=arb_id_short,
            profit=profit,
            net_edge=net_edge,
            gross_edge="",
            fees="",
            slippage="",
            max_size="",
            match_score="",
            resolution_confidence="",
            freshness="",
            left_venue="",
            left_odds="",
            left_liquidity="",
            left_side="",
            right_venue="",
            right_odds="",
            right_liquidity="",
            right_side="",
            links="",
            expires_at="",
            duration=duration,
        )
    
    @staticmethod
    def _format_odds(odds: float | None) -> str:
        """Format decimal odds.
        
        Args:
            odds: Decimal odds value
            
        Returns:
            Formatted odds string
        """
        if odds is None:
            return "N/A"
        return f"{odds:.2f}"
    
    @staticmethod
    def _format_duration(seconds: int) -> str:
        """Format duration in human-readable form.
        
        Args:
            seconds: Duration in seconds
            
        Returns:
            Formatted duration string
        """
        if seconds < 60:
            return f"{seconds}s"
        elif seconds < 3600:
            minutes = seconds // 60
            return f"{minutes}m"
        else:
            hours = seconds // 3600
            minutes = (seconds % 3600) // 60
            return f"{hours}h {minutes}m"


class AlertBuilder:
    """Builds complete alert messages."""
    
    def __init__(self) -> None:
        """Initialize the alert builder."""
        self.formatter = AlertFormatter()
    
    def build_alert(self, opportunity: "ArbOpportunity") -> str:
        """Build a full alert message.
        
        Args:
            opportunity: The arbitrage opportunity
            
        Returns:
            Complete alert message ready to send
        """
        data = self.formatter.format_opportunity(opportunity)
        return data.render("full")
    
    def build_compact_alert(self, opportunity: "ArbOpportunity") -> str:
        """Build a compact alert message.
        
        Args:
            opportunity: The arbitrage opportunity
            
        Returns:
            Compact alert message
        """
        data = self.formatter.format_opportunity(opportunity)
        return data.render("compact")
    
    def build_expired_alert(
        self,
        opportunity: "ArbOpportunity",
        duration_seconds: int,
    ) -> str:
        """Build an expired opportunity alert.
        
        Args:
            opportunity: The expired arbitrage opportunity
            duration_seconds: How long the opportunity was alive
            
        Returns:
            Expired alert message
        """
        data = self.formatter.format_expired(opportunity, duration_seconds)
        return data.render("expired")
