"""Message formatting for Telegram alerts.

Formats arbitrage opportunities into clean, readable Telegram messages
with proper escaping and emoji indicators.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any


def _escape_markdown(text: str | None) -> str:
    """Escape special characters for Telegram MarkdownV2.
    
    Characters to escape: _ * [ ] ( ) ~ ` > # + - = | { } . !
    """
    if text is None:
        return ""
    
    text = str(text)
    # Characters that need escaping in MarkdownV2
    # Note: Order matters - escape backslash first!
    escape_chars = ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']
    
    for char in escape_chars:
        text = text.replace(char, f"\\{char}")
    
    return text


def _format_currency(amount: float) -> str:
    """Format currency amount with commas."""
    return f"${amount:,.2f}"


def _format_percentage(pct: float) -> str:
    """Format percentage with sign."""
    return f"{pct * 100:.2f}%"


def _format_datetime(dt: datetime | None) -> str:
    """Format datetime for display."""
    if dt is None:
        return "Unknown"
    
    now = datetime.utcnow()
    delta = dt - now
    
    # If today, show time
    if delta.days == 0:
        return f"Today {dt.strftime('%I:%M %p')}"
    elif delta.days == 1:
        return f"Tomorrow {dt.strftime('%I:%M %p')}"
    elif delta.days < 7:
        return dt.strftime("%A %I:%M %p")
    else:
        return dt.strftime("%b %d, %Y %I:%M %p")


def _format_minutes(minutes: int) -> str:
    """Format minutes into human readable string."""
    if minutes < 60:
        return f"{minutes} minutes"
    hours = minutes // 60
    mins = minutes % 60
    if mins == 0:
        return f"{hours} hour{'s' if hours > 1 else ''}"
    return f"{hours}h {mins}m"


def _get_profit_emoji(profit_pct: float) -> str:
    """Get emoji based on profit percentage."""
    if profit_pct >= 0.05:
        return "🔥"
    elif profit_pct >= 0.03:
        return "🚀"
    elif profit_pct >= 0.015:
        return "💰"
    else:
        return "✨"


def _get_venue_emoji(venue: str) -> str:
    """Get emoji for venue."""
    venue_lower = venue.lower()
    
    emojis = {
        "polymarket": "📊",
        "draftkings": "🏈",
        "fanduel": "🏀",
        "betmgm": "⚽",
        "caesars": "🎰",
        "predictit": "📈",
        "kalshi": "📉",
    }
    
    for key, emoji in emojis.items():
        if key in venue_lower:
            return emoji
    
    return "🎯"


def format_opportunity_alert(
    event_title: str,
    side_a_venue: str,
    side_a_outcome: str,
    side_a_odds: float,
    side_b_venue: str,
    side_b_outcome: str,
    side_b_odds: float,
    profit_pct: float,
    total_stake: float,
    side_a_stake: float,
    side_b_stake: float,
    start_time: datetime | None = None,
    expires_minutes: int | None = None,
    additional_info: dict[str, Any] | None = None,
) -> str:
    """Format a complete arbitrage opportunity alert message.
    
    Args:
        event_title: Name of the event (e.g., "Lakers vs Warriors")
        side_a_venue: Name of first venue
        side_a_outcome: Outcome for first side
        side_a_odds: Decimal odds for first side
        side_b_venue: Name of second venue
        side_b_outcome: Outcome for second side
        side_b_odds: Decimal odds for second side
        profit_pct: Profit percentage after fees (e.g., 0.032 for 3.2%)
        total_stake: Recommended total stake amount
        side_a_stake: Stake amount for side A
        side_b_stake: Stake amount for side B
        start_time: Event start time (optional)
        expires_minutes: Minutes until opportunity expires (optional)
        additional_info: Additional fields to include (optional)
    
    Returns:
        Formatted message string ready for Telegram
    """
    profit_emoji = _get_profit_emoji(profit_pct)
    venue_a_emoji = _get_venue_emoji(side_a_venue)
    venue_b_emoji = _get_venue_emoji(side_b_venue)
    
    lines = [
        f"{profit_emoji} ARBITRAGE OPPORTUNITY",
        "",
        f"📊 Event: {_escape_markdown(event_title)}",
    ]
    
    if start_time:
        lines.append(f"⏰ Start: {_format_datetime(start_time)}")
    
    lines.extend([
        "",
        "💰 Opportunity:",
        f"• Side A: {_escape_markdown(side_a_outcome)} @ {side_a_odds:.2f} ({_escape_markdown(side_a_venue)}) {venue_a_emoji}",
        f"• Side B: {_escape_markdown(side_b_outcome)} @ {side_b_odds:.2f} ({_escape_markdown(side_b_venue)}) {venue_b_emoji}",
        "",
        f"📈 Profit: {_format_percentage(profit_pct)} after fees",
        f"💵 Recommended stake: {_format_currency(total_stake)} total",
        f"   - {_format_currency(side_a_stake)} on {_escape_markdown(side_a_outcome)}",
        f"   - {_format_currency(side_b_stake)} on {_escape_markdown(side_b_outcome)}",
    ])
    
    if expires_minutes:
        lines.append("")
        lines.append(f"⚠️ Expires in: {_format_minutes(expires_minutes)}")
    
    # Add any additional info
    if additional_info:
        lines.append("")
        for key, value in additional_info.items():
            lines.append(f"• {_escape_markdown(key)}: {_escape_markdown(str(value))}")
    
    return "\n".join(lines)


@dataclass
class FormattedAlert:
    """Container for formatted alert with metadata."""
    
    message: str
    priority: int  # 1-10, higher is more urgent
    event_id: str
    sport: str | None
    profit_pct: float


class AlertFormatter:
    """Formatter for arbitrage opportunity alerts."""
    
    def __init__(self, include_details: bool = True):
        """Initialize formatter.
        
        Args:
            include_details: Whether to include full details in messages
        """
        self.include_details = include_details
    
    def format_from_opportunity(self, opportunity: Any) -> FormattedAlert:
        """Format an ArbOpportunity object.
        
        Args:
            opportunity: ArbOpportunity dataclass instance
            
        Returns:
            FormattedAlert with message and metadata
        """
        # Extract data from ArbOpportunity
        event_title = getattr(opportunity, 'event_title', 'Unknown Event')
        left_leg = getattr(opportunity, 'left_leg', {})
        right_leg = getattr(opportunity, 'right_leg', {})
        net_edge_pct = getattr(opportunity, 'net_edge_pct', 0.0)
        max_size = getattr(opportunity, 'max_size', 0.0)
        expires_at = getattr(opportunity, 'expires_at', None)
        
        # Calculate stakes
        side_a_odds = left_leg.get('odds', 2.0)
        side_b_odds = right_leg.get('odds', 2.0)
        
        # Calculate proportional stakes for equal payout
        total_odds = side_a_odds + side_b_odds
        side_a_stake = max_size * (side_b_odds / total_odds)
        side_b_stake = max_size * (side_a_odds / total_odds)
        
        # Calculate expires minutes
        expires_minutes = None
        if expires_at:
            delta = expires_at - datetime.utcnow()
            expires_minutes = max(0, int(delta.total_seconds() / 60))
        
        # Build message
        message = format_opportunity_alert(
            event_title=event_title,
            side_a_venue=left_leg.get('venue', 'Venue A'),
            side_a_outcome=left_leg.get('side', 'Side A'),
            side_a_odds=side_a_odds,
            side_b_venue=right_leg.get('venue', 'Venue B'),
            side_b_outcome=right_leg.get('side', 'Side B'),
            side_b_odds=side_b_odds,
            profit_pct=net_edge_pct,
            total_stake=max_size,
            side_a_stake=side_a_stake,
            side_b_stake=side_b_stake,
            start_time=expires_at,
            expires_minutes=expires_minutes,
        )
        
        # Calculate priority (1-10)
        priority = self._calculate_priority(net_edge_pct, max_size)
        
        return FormattedAlert(
            message=message,
            priority=priority,
            event_id=getattr(opportunity, 'arb_id', 'unknown'),
            sport=left_leg.get('sport'),
            profit_pct=net_edge_pct,
        )
    
    def format_simple_notification(
        self,
        title: str,
        body: str,
        priority: int = 5,
    ) -> FormattedAlert:
        """Format a simple notification.
        
        Args:
            title: Notification title
            body: Notification body
            priority: Priority level (1-10)
            
        Returns:
            FormattedAlert with message
        """
        message = f"📢 {_escape_markdown(title)}\n\n{_escape_markdown(body)}"
        
        return FormattedAlert(
            message=message,
            priority=priority,
            event_id="simple",
            sport=None,
            profit_pct=0.0,
        )
    
    def format_system_alert(
        self,
        alert_type: str,
        message: str,
        details: dict[str, Any] | None = None,
    ) -> FormattedAlert:
        """Format a system alert (errors, startup, shutdown).
        
        Args:
            alert_type: Type of alert (error, startup, shutdown, etc.)
            message: Main alert message
            details: Additional details
            
        Returns:
            FormattedAlert with message
        """
        emoji_map = {
            "error": "🚨",
            "warning": "⚠️",
            "startup": "🚀",
            "shutdown": "🛑",
            "info": "ℹ️",
            "success": "✅",
        }
        
        emoji = emoji_map.get(alert_type.lower(), "📢")
        
        lines = [f"{emoji} {_escape_markdown(alert_type.upper())}", ""]
        lines.append(_escape_markdown(message))
        
        if details and self.include_details:
            lines.append("")
            for key, value in details.items():
                lines.append(f"• {_escape_markdown(key)}: {_escape_markdown(str(value))}")
        
        formatted = "\n".join(lines)
        
        # Priority based on type
        priority_map = {
            "error": 10,
            "warning": 7,
            "startup": 5,
            "shutdown": 5,
            "info": 3,
            "success": 4,
        }
        
        return FormattedAlert(
            message=formatted,
            priority=priority_map.get(alert_type.lower(), 5),
            event_id=f"system_{alert_type}",
            sport=None,
            profit_pct=0.0,
        )
    
    def _calculate_priority(self, profit_pct: float, max_size: float) -> int:
        """Calculate alert priority based on profit and size.
        
        Returns priority from 1-10 where 10 is highest.
        """
        base = 5
        
        # Profit boost (0-3 points)
        if profit_pct >= 0.05:
            base += 3
        elif profit_pct >= 0.03:
            base += 2
        elif profit_pct >= 0.015:
            base += 1
        
        # Size boost (0-2 points)
        if max_size >= 10000:
            base += 2
        elif max_size >= 5000:
            base += 1
        
        return min(10, base)
