"""Jinja2-style template for Telegram alert messages.

This module provides templates for formatting arbitrage opportunity alerts.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..arb_opportunity_schema import ArbOpportunity


# Main alert template using f-string style
ALERT_TEMPLATE = r"""🎯 *Arbitrage Opportunity*

📊 *{event_title}*

💰 *Profit:* {profit} | *Edge:* {net_edge}
📏 *Size:* {max_size} | *Match:* {match_score}

🔹 *Left:* {left_venue} \- {left_odds} @ {left_liquidity}
   {left_side}
🔸 *Right:* {right_venue} \- {right_odds} @ {right_liquidity}
   {right_side}

📈 *Edge Breakdown:*
   Gross: {gross_edge} | Fees: {fees} | Slip: {slippage}

⏱️ *Freshness:* {freshness}s | 🔒 *Resolution:* {resolution_confidence}%

🔗 {links}

⚡ _Expires: {expires_at}_
🆔 `{arb_id_short}`
"""

# Compact template for high-volume alerts
COMPACT_TEMPLATE = """🎯 {event_title}
💰 {profit} @ {net_edge} | {links}
🆔 `{arb_id_short}`
"""

# Expired opportunity template
EXPIRED_TEMPLATE = """⏹️ *Opportunity Expired*

📊 *{event_title}*

Was: {profit} @ {net_edge}
🔍 *Lived for:* {duration}
🆔 `{arb_id_short}`
"""


@dataclass
class AlertTemplateData:
    """Data structure for template rendering."""
    
    # Event info
    event_title: str
    arb_id_short: str
    
    # Profit & Edge
    profit: str
    net_edge: str
    gross_edge: str
    fees: str
    slippage: str
    
    # Sizing
    max_size: str
    
    # Match quality
    match_score: str
    resolution_confidence: str
    freshness: str
    
    # Left leg
    left_venue: str
    left_odds: str
    left_liquidity: str
    left_side: str
    
    # Right leg
    right_venue: str
    right_odds: str
    right_liquidity: str
    right_side: str
    
    # Links
    links: str
    
    # Timing
    expires_at: str
    
    # Optional fields (must come after required fields)
    left_url: str | None = None
    right_url: str | None = None
    
    # Expired template fields
    duration: str = ""
    
    def render(self, template_type: str = "full") -> str:
        """Render the template with current data.
        
        Args:
            template_type: "full", "compact", or "expired"
            
        Returns:
            Rendered alert message
        """
        if template_type == "compact":
            return COMPACT_TEMPLATE.format(**self.__dict__)
        elif template_type == "expired":
            return EXPIRED_TEMPLATE.format(**self.__dict__)
        else:
            return ALERT_TEMPLATE.format(**self.__dict__)


class AlertTemplateEngine:
    """Template engine for alert messages."""
    
    @staticmethod
    def render_opportunity(
        opportunity: "ArbOpportunity",
        formatter: "AlertFormatter",
    ) -> str:
        """Render a full opportunity alert.
        
        Args:
            opportunity: The arbitrage opportunity
            formatter: Formatter instance with formatting methods
            
        Returns:
            Rendered alert message
        """
        data = formatter.format_opportunity(opportunity)
        return data.render("full")
    
    @staticmethod
    def render_compact(
        opportunity: "ArbOpportunity",
        formatter: "AlertFormatter",
    ) -> str:
        """Render a compact opportunity alert.
        
        Args:
            opportunity: The arbitrage opportunity
            formatter: Formatter instance with formatting methods
            
        Returns:
            Rendered compact alert message
        """
        data = formatter.format_opportunity(opportunity)
        return data.render("compact")
    
    @staticmethod
    def render_expired(
        opportunity: "ArbOpportunity",
        duration_seconds: int,
        formatter: "AlertFormatter",
    ) -> str:
        """Render an expired opportunity alert.
        
        Args:
            opportunity: The arbitrage opportunity that expired
            duration_seconds: How long the opportunity was alive
            formatter: Formatter instance with formatting methods
            
        Returns:
            Rendered expired alert message
        """
        data = formatter.format_expired(opportunity, duration_seconds)
        return data.render("expired")
