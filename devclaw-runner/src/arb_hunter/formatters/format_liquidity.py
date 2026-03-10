"""Format liquidity values for display.

Examples:
- $47k
- $1.2M
- N/A for missing values
"""

from __future__ import annotations


def format_liquidity(value: float | None) -> str:
    """Format liquidity value with appropriate suffix.
    
    Args:
        value: Liquidity value in USD
        
    Returns:
        Formatted string like "$47k", "$1.2M", or "N/A"
        
    Examples:
        >>> format_liquidity(47000.0)
        '$47k'
        >>> format_liquidity(1200000.0)
        '$1.2M'
        >>> format_liquidity(None)
        'N/A'
        >>> format_liquidity(0)
        '$0'
    """
    if value is None:
        return "N/A"
    
    abs_value = abs(value)
    
    # Determine suffix and scale
    if abs_value >= 1_000_000_000:
        scaled = abs_value / 1_000_000_000
        suffix = "B"
    elif abs_value >= 1_000_000:
        scaled = abs_value / 1_000_000
        suffix = "M"
    elif abs_value >= 1_000:
        scaled = abs_value / 1_000
        suffix = "k"
    else:
        scaled = abs_value
        suffix = ""
    
    # Format the number
    if scaled >= 100 or suffix == "":
        formatted_num = f"{scaled:.0f}"
    else:
        formatted_num = f"{scaled:.1f}"
    
    # Remove trailing .0 if present
    if ".0" in formatted_num:
        formatted_num = formatted_num.replace(".0", "")
    
    return f"${formatted_num}{suffix}"


def format_liquidity_pair(left_liq: float | None, right_liq: float | None) -> str:
    """Format a pair of liquidity values.
    
    Args:
        left_liq: Left leg liquidity
        right_liq: Right leg liquidity
        
    Returns:
        Formatted pair like "$47k / $1.2M"
    """
    return f"{format_liquidity(left_liq)} / {format_liquidity(right_liq)}"


def get_liquidity_emoji(value: float | None) -> str:
    """Get an emoji indicator for liquidity level.
    
    Args:
        value: Liquidity value in USD
        
    Returns:
        Emoji string indicating liquidity level
    """
    if value is None:
        return "⚠️"
    
    if value >= 1_000_000:
        return "🟢"  # High liquidity
    elif value >= 100_000:
        return "🟡"  # Medium liquidity
    elif value >= 10_000:
        return "🟠"  # Low liquidity
    else:
        return "🔴"  # Very low liquidity
