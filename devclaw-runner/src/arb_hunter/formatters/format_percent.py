"""Format percentages for display.

Examples:
- +3.8%
- -1.2%
- Always show sign for changes
"""

from __future__ import annotations


def format_percent(
    value: float | None,
    decimals: int = 1,
    always_show_sign: bool = True,
    is_basis_points: bool = False,
) -> str:
    """Format percentage with sign.
    
    Args:
        value: Percentage as decimal (e.g., 0.038 for 3.8%)
        decimals: Number of decimal places
        always_show_sign: Whether to always show + for positive
        is_basis_points: If True, value is in basis points (e.g., 380 for 3.8%)
        
    Returns:
        Formatted string like "+3.8%", "-1.2%"
        
    Examples:
        >>> format_percent(0.038)
        '+3.8%'
        >>> format_percent(-0.012)
        '-1.2%'
        >>> format_percent(0.05, always_show_sign=False)
        '5.0%'
        >>> format_percent(None)
        'N/A'
        >>> format_percent(380, is_basis_points=True)
        '+3.8%'
    """
    if value is None:
        return "N/A"
    
    # Convert basis points to decimal if needed
    if is_basis_points:
        value = value / 10000
    
    # Convert decimal to percentage
    pct = value * 100
    
    # Determine sign
    if pct > 0 and always_show_sign:
        sign = "+"
    elif pct < 0:
        sign = ""
    else:
        sign = "+" if always_show_sign else ""
    
    # Format number
    formatted = f"{pct:.{decimals}f}%"
    
    return f"{sign}{formatted}"


def format_edge_components(
    gross: float,
    fees: float,
    slippage: float,
    net: float,
) -> str:
    """Format edge components for detailed display.
    
    Args:
        gross: Gross edge percentage
        fees: Fees percentage
        slippage: Slippage percentage
        net: Net edge percentage
        
    Returns:
        Multi-line formatted string
    """
    return (
        f"Gross: {format_percent(gross)}\n"
        f"Fees:  {format_percent(-fees)}\n"
        f"Slip:  {format_percent(-slippage)}\n"
        f"Net:   {format_percent(net)}"
    )


def format_win_probability(probability: float | None) -> str:
    """Format win probability as percentage.
    
    Args:
        probability: Probability as decimal (0.0 to 1.0)
        
    Returns:
        Formatted string like "65.2%"
    """
    if probability is None:
        return "N/A"
    
    pct = probability * 100
    return f"{pct:.1f}%"
