"""
Title Similarity - Fuzzy string matching for event titles.

Module 2.2: Uses rapidfuzz for high-performance fuzzy matching with
normalization for punctuation, case, and common variations.
"""

import os
import re
from typing import Optional

from rapidfuzz import fuzz, process


# Environment-based thresholds
MIN_TITLE_SCORE = float(os.getenv("OPENCLAW_MIN_TITLE_SCORE", "0.70"))
FUZZY_MATCH_LIMIT = int(os.getenv("OPENCLAW_FUZZY_MATCH_LIMIT", "5"))


class TitleNormalizer:
    """Normalizes event titles for consistent comparison."""
    
    # Common words to remove (articles, stop words)
    STOP_WORDS = frozenset({
        "the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for",
        "of", "with", "by", "from", "as", "is", "was", "are", "will", "be",
    })
    
    # Sportsbook/market specific suffixes/prefixes to strip
    MARKET_SUFFIXES = [
        r"\s*[-–—]\s*match winner",
        r"\s*[-–—]\s*moneyline",
        r"\s*[-–—]\s*to win",
        r"\s*\(\s*regulation\s*\)",
        r"\s*\(\s*including\s*overtime\s*\)",
        r"\s*[-–—]\s*outright",
        r"\s*[-–—]\s*futures",
    ]
    
    def __init__(self) -> None:
        self._suffix_patterns = [
            re.compile(pattern, re.IGNORECASE) for pattern in self.MARKET_SUFFIXES
        ]
    
    def normalize(self, title: str) -> str:
        """
        Normalize a title for comparison.
        
        Steps:
        1. Lowercase
        2. Remove market-specific suffixes
        3. Remove punctuation except hyphens between words
        4. Remove extra whitespace
        5. Remove stop words
        """
        if not title:
            return ""
        
        # Lowercase
        normalized = title.lower()
        
        # Remove market suffixes
        for pattern in self._suffix_patterns:
            normalized = pattern.sub("", normalized)
        
        # Replace common punctuation with spaces, keep internal hyphens
        normalized = re.sub(r"[^\w\s-]", " ", normalized)
        
        # Normalize whitespace
        normalized = re.sub(r"\s+", " ", normalized).strip()
        
        # Remove stop words
        words = normalized.split()
        words = [w for w in words if w not in self.STOP_WORDS and len(w) > 1]
        
        return " ".join(words)
    
    def normalize_for_display(self, title: str) -> str:
        """Light normalization for display purposes (keep more context)."""
        if not title:
            return ""
        
        normalized = title.lower()
        normalized = re.sub(r"[^\w\s-]", " ", normalized)
        normalized = re.sub(r"\s+", " ", normalized).strip()
        
        return normalized


class TitleSimilarityScorer:
    """Scores similarity between event titles using rapidfuzz."""
    
    def __init__(self) -> None:
        self.normalizer = TitleNormalizer()
    
    def score(
        self,
        title1: str,
        title2: str,
        use_token_sort: bool = True,
        use_partial: bool = True,
    ) -> float:
        """
        Calculate similarity score between two titles (0-1).
        
        Combines multiple fuzzy matching strategies for robust scoring:
        - Ratio: Standard fuzzy ratio
        - Token Sort: Accounts for word order variations
        - Token Set: Accounts for partial matches
        - Partial Ratio: Catches substring matches
        
        Args:
            title1: First title (e.g., prediction market event)
            title2: Second title (e.g., sportsbook event)
            use_token_sort: Whether to use token sort ratio
            use_partial: Whether to use partial ratio
        
        Returns:
            Float between 0 and 1 representing similarity
        """
        if not title1 or not title2:
            return 0.0
        
        if title1 == title2:
            return 1.0
        
        # Normalize both titles
        norm1 = self.normalizer.normalize(title1)
        norm2 = self.normalizer.normalize(title2)
        
        if not norm1 or not norm2:
            return 0.0
        
        if norm1 == norm2:
            return 1.0
        
        # Calculate multiple similarity metrics
        scores: list[float] = []
        
        # Standard ratio
        scores.append(fuzz.ratio(norm1, norm2) / 100.0)
        
        # Token sort ratio (handles word order differences)
        if use_token_sort:
            scores.append(fuzz.token_sort_ratio(norm1, norm2) / 100.0)
        
        # Token set ratio (handles partial word matches)
        scores.append(fuzz.token_set_ratio(norm1, norm2) / 100.0)
        
        # Partial ratio (catches substring matches)
        if use_partial:
            scores.append(fuzz.partial_ratio(norm1, norm2) / 100.0)
            # Partial token sort for ordered subsets
            scores.append(fuzz.partial_token_sort_ratio(norm1, norm2) / 100.0)
        
        # Weighted combination favoring higher scores
        # Token set is weighted higher as it handles partial matches well
        weights = [0.2, 0.25, 0.35, 0.1, 0.1] if use_partial else [0.3, 0.3, 0.4]
        weighted_score = sum(s * w for s, w in zip(sorted(scores, reverse=True), weights))
        
        return min(1.0, max(0.0, weighted_score))
    
    def score_batch(
        self,
        query: str,
        candidates: list[str],
        limit: int = FUZZY_MATCH_LIMIT,
        score_cutoff: float = MIN_TITLE_SCORE,
    ) -> list[tuple[str, float]]:
        """
        Score query against multiple candidates, returning top matches.
        
        Args:
            query: Title to match
            candidates: List of candidate titles
            limit: Maximum number of results
            score_cutoff: Minimum score to include (0-100 for rapidfuzz)
        
        Returns:
            List of (title, score) tuples sorted by score descending
        """
        if not query or not candidates:
            return []
        
        norm_query = self.normalizer.normalize(query)
        norm_candidates = [self.normalizer.normalize(c) for c in candidates]
        
        # Create mapping back to original
        norm_to_original = {
            norm: orig for norm, orig in zip(norm_candidates, candidates)
        }
        
        # Use rapidfuzz's optimized extract function
        results = process.extract(
            norm_query,
            norm_candidates,
            scorer=fuzz.token_set_ratio,
            limit=limit,
            score_cutoff=score_cutoff * 100,  # Convert to 0-100 scale
        )
        
        # Convert back to original titles and 0-1 scale
        return [
            (norm_to_original.get(result[0], result[0]), result[1] / 100.0)
            for result in results
        ]
    
    def is_match(
        self,
        title1: str,
        title2: str,
        threshold: float = MIN_TITLE_SCORE,
    ) -> bool:
        """Quick check if titles match above threshold."""
        return self.score(title1, title2) >= threshold
    
    def explain_score(
        self,
        title1: str,
        title2: str,
    ) -> dict[str, float | str]:
        """Return detailed breakdown of similarity scores."""
        norm1 = self.normalizer.normalize(title1)
        norm2 = self.normalizer.normalize(title2)
        
        return {
            "original_1": title1,
            "original_2": title2,
            "normalized_1": norm1,
            "normalized_2": norm2,
            "ratio": fuzz.ratio(norm1, norm2) / 100.0,
            "token_sort_ratio": fuzz.token_sort_ratio(norm1, norm2) / 100.0,
            "token_set_ratio": fuzz.token_set_ratio(norm1, norm2) / 100.0,
            "partial_ratio": fuzz.partial_ratio(norm1, norm2) / 100.0,
            "partial_token_sort": fuzz.partial_token_sort_ratio(norm1, norm2) / 100.0,
            "weighted_score": self.score(title1, title2),
        }


# Singleton instance for convenience
_default_scorer: Optional[TitleSimilarityScorer] = None


def get_scorer() -> TitleSimilarityScorer:
    """Get the default title similarity scorer instance."""
    global _default_scorer
    if _default_scorer is None:
        _default_scorer = TitleSimilarityScorer()
    return _default_scorer


def calculate_similarity(title1: str, title2: str) -> float:
    """Convenience function to calculate title similarity."""
    return get_scorer().score(title1, title2)


def calculate_similarity_batch(
    query: str,
    candidates: list[str],
    limit: int = FUZZY_MATCH_LIMIT,
) -> list[tuple[str, float]]:
    """Convenience function for batch title matching."""
    return get_scorer().score_batch(query, candidates, limit)
