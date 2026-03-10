"""Format profit numbers for display.

Examples:
- $38 (not $38.00)
- $1.2k for large numbers
- $850k, $2.3M
"""

from __future__ import annotations


def format_profit(value: float | None, include_sign: bool = False) -> str:
    """Format profit number with appropriate suffix.
    
    Args:
        value: Profit value in USD
        include_sign: Whether to include + for positive values
        
    Returns:
        Formatted string like "$38", "$1.2k", "$2.3M"
        
    Examples:
        >>> format_profit(38.0)
        '$38'
        >>> format_profit(1200.0)
        '$1.2k'
        >>> format_profit(2300000.0)
        '$2.3M'
        >>> format_profit(-50.0)
        '-$50'
        >>> format_profit(None)
        'N/A'
    """
    if value is None:
        return "N/A"
    
    # Handle negative values
    negative = value < 0
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
        # No decimal for large numbers or small suffixless values
        formatted_num = f"{scaled:.0f}"
    elif scaled >= 10:
        # One decimal for medium numbers
        formatted_num = f"{scaled:.1f}"
    else:
        # One decimal for small numbers
        formatted_num = f"{scaled:.1f}"
    
    # Remove trailing .0 if present
    if ".0" in formatted_num:
        formatted_num = formatted_num.replace(".0", "")
    
    # Build result
    result = f"${formatted_num}{suffix}"
    
    if negative:
        result = f"-{result}"
    elif include_sign and value > 0:
        result = f"+{result}"
    
    return result


def format_profit_range(min_val: float, max_val: float) -> str:
    """Format a profit range.
    
    Args:
        min_val: Minimum profit
        max_val: Maximum profit
        
    Returns:
        Formatted range like "$38-$1.2k"
    """
    return f"{format_profit(min_val)}-{format_profit(max_val)}"
