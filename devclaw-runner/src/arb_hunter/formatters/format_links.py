"""Format markdown links for Telegram.

Telegram Bot API uses MarkdownV2 which requires escaping of special characters.
"""

from __future__ import annotations

import re


# Characters that need escaping in Telegram MarkdownV2
MARKDOWN_V2_ESCAPE_CHARS = r"_\*\[\]\(\)~`>#\+\-=\|{}\.!"


def escape_markdown_v2(text: str | None) -> str:
    """Escape special characters for Telegram MarkdownV2.
    
    Args:
        text: Raw text to escape
        
    Returns:
        Escaped text safe for MarkdownV2
        
    Examples:
        >>> escape_markdown_v2("Hello (world)")
        'Hello \\(world\\)'
        >>> escape_markdown_v2("Price: $50.00")
        'Price: $50\\.00'
    """
    if text is None:
        return ""
    
    # Escape each special character with backslash
    escaped = re.sub(f"([{re.escape(MARKDOWN_V2_ESCAPE_CHARS)}])", r"\\\1", text)
    return escaped


def format_markdown_link(text: str, url: str | None) -> str:
    """Format a markdown link for Telegram.
    
    Args:
        text: Link display text
        url: URL to link to
        
    Returns:
        Markdown formatted link like "[text](url)"
        
    Examples:
        >>> format_markdown_link("Polymarket", "https://polymarket.com")
        '[Polymarket](https://polymarket.com)'
    """
    if not url:
        return escape_markdown_v2(text)
    
    # Escape the display text
    escaped_text = escape_markdown_v2(text)
    
    # URLs in Telegram don't need escaping of most chars,
    # but parentheses in URLs need to be escaped
    escaped_url = url.replace("(", "\\(").replace(")", "\\)")
    
    return f"[{escaped_text}]({escaped_url})"


def format_venue_links(
    left_venue: str,
    left_url: str | None,
    right_venue: str,
    right_url: str | None,
) -> str:
    """Format venue links as markdown.
    
    Args:
        left_venue: Left venue name
        left_url: Left venue URL
        right_venue: Right venue name
        right_url: Right venue URL
        
    Returns:
        Formatted links like "[Polymarket](url) | [DraftKings](url)"
    """
    left_link = format_markdown_link(left_venue, left_url)
    right_link = format_markdown_link(right_venue, right_url)
    
    return f"{left_link} \\| {right_link}"


def truncate_text(text: str, max_length: int = 100, suffix: str = "...") -> str:
    """Truncate text to max length.
    
    Args:
        text: Text to truncate
        max_length: Maximum length
        suffix: Suffix to add if truncated
        
    Returns:
        Truncated text
    """
    if len(text) <= max_length:
        return text
    
    return text[: max_length - len(suffix)] + suffix
