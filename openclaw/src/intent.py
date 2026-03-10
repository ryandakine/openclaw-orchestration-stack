"""
Intent Classification Module

Classifies incoming requests into intent categories using keyword matching,
heuristics, and optional LLM-based classification.
"""

import re
from enum import Enum
from typing import Dict, List, Set, Any, Optional, Callable
from dataclasses import dataclass

from ..schemas.action_plan import IntentCategory, IntentClassification, ConfidenceLevel


# Keyword patterns for intent classification
INTENT_KEYWORDS: Dict[IntentCategory, List[str]] = {
    IntentCategory.FEATURE_REQUEST: [
        "add", "create", "implement", "build", "new", "feature",
        "support", "enable", "introduce", "generate", "develop",
        "make", "provide", "include", "integrate"
    ],
    IntentCategory.BUG_REPORT: [
        "fix", "bug", "error", "issue", "broken", "crash",
        "problem", "fail", "fails", "failure", "not working",
        "incorrect", "wrong", "exception", "traceback"
    ],
    IntentCategory.CODE_IMPROVEMENT: [
        "refactor", "improve", "optimize", "clean", "cleanup",
        "simplify", "better", "performance", "efficiency",
        "restructure", "modernize", "upgrade", "update"
    ],
    IntentCategory.REVIEW: [
        "review", "check", "audit", "validate", "verify",
        "inspect", "examine", "assess", "evaluate", "approve"
    ],
    IntentCategory.DEPLOYMENT: [
        "deploy", "release", "ship", "publish", "launch",
        "production", "prod", "go live", "rollout", "promote"
    ],
    IntentCategory.QUESTION: [
        "question", "how", "what", "why", "when", "where",
        "explain", "clarify", "understand", "help", "guide",
        "documentation", "docs", "example", "tutorial"
    ],
}

# Regex patterns for more complex matching
INTENT_PATTERNS: Dict[IntentCategory, List[re.Pattern]] = {
    IntentCategory.FEATURE_REQUEST: [
        re.compile(r"\badd\s+(?:a|an|the)?\s*(?:new)?\s*(?:feature|option|setting|function)", re.I),
        re.compile(r"\b(?:would|could|should)\s+(?:it\s+be\s+possible\s+to|be\s+great\s+to|be\s+nice\s+to)", re.I),
    ],
    IntentCategory.BUG_REPORT: [
        re.compile(r"\b(?:get|gets|got)\s+(?:an?\s+)?error", re.I),
        re.compile(r"\bthrows?\s+(?:an?\s+)?exception", re.I),
        re.compile(r"\bcrashes?\s+(?:when|on|while|after)", re.I),
    ],
    IntentCategory.DEPLOYMENT: [
        re.compile(r"\bdeploy\s+(?:to|on)\s+(?:prod|production|live)", re.I),
        re.compile(r"\bgo\s+live\b", re.I),
        re.compile(r"\bpush\s+(?:to|into)\s+(?:prod|production)", re.I),
    ],
}


class IntentClassifier:
    """
    Classifies requests into intent categories.
    Uses keyword matching, pattern matching, and optional ML-based classification.
    """
    
    def __init__(self):
        self._custom_classifiers: List[Callable[[str, Dict[str, Any]], Optional[IntentCategory]]] = []
    
    def add_custom_classifier(
        self, 
        classifier: Callable[[str, Dict[str, Any]], Optional[IntentCategory]]
    ):
        """Add a custom classifier function."""
        self._custom_classifiers.append(classifier)
    
    def classify(
        self, 
        payload: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None
    ) -> IntentClassification:
        """Classify the intent of a request."""
        context = context or {}
        
        # Extract text to analyze
        text = self._extract_text(payload)
        text_lower = text.lower()
        
        # Run custom classifiers first
        for classifier in self._custom_classifiers:
            result = classifier(text, payload)
            if result:
                return IntentClassification(
                    category=result,
                    confidence=0.85,
                    keywords=[],
                    confidence_level=ConfidenceLevel.HIGH
                )
        
        # Score each intent category
        scores: Dict[IntentCategory, float] = {}
        matched_keywords: Dict[IntentCategory, List[str]] = {}
        
        for category in IntentCategory:
            if category == IntentCategory.UNKNOWN:
                continue
                
            score, keywords = self._score_category(category, text_lower, payload)
            scores[category] = score
            matched_keywords[category] = keywords
        
        # Get best match
        if scores:
            best_category = max(scores, key=scores.get)
            best_score = scores[best_category]
        else:
            best_category = IntentCategory.UNKNOWN
            best_score = 0.0
        
        # Adjust confidence based on score distribution
        confidence = self._calculate_confidence(best_score, scores)
        
        return IntentClassification(
            category=best_category,
            confidence=confidence,
            keywords=matched_keywords.get(best_category, []),
            confidence_level=self._get_confidence_level(confidence)
        )
    
    def _extract_text(self, payload: Dict[str, Any]) -> str:
        """Extract searchable text from payload."""
        text_parts = []
        
        for field in ["description", "title", "message", "content", "text", "type"]:
            if field in payload and isinstance(payload[field], str):
                text_parts.append(payload[field])
        
        if "body" in payload and isinstance(payload["body"], str):
            text_parts.append(payload["body"])
        
        if "changes" in payload:
            text_parts.append(str(payload["changes"]))
        
        return " ".join(text_parts) if text_parts else str(payload)
    
    def _score_category(
        self, 
        category: IntentCategory, 
        text: str,
        payload: Dict[str, Any]
    ) -> tuple[float, List[str]]:
        """Score how well text matches an intent category."""
        score = 0.0
        matched = []
        
        # Keyword matching
        keywords = INTENT_KEYWORDS.get(category, [])
        for keyword in keywords:
            count = text.count(keyword)
            if count > 0:
                score += count * 0.1
                matched.append(keyword)
        
        # Pattern matching
        patterns = INTENT_PATTERNS.get(category, [])
        for pattern in patterns:
            matches = pattern.findall(text)
            score += len(matches) * 0.3
        
        # Check explicit type field
        payload_type = payload.get("type", "").lower()
        if payload_type == category.value or payload_type in [kw for kw in keywords]:
            score += 0.5
        
        # Check for GitHub event types
        event_type = payload.get("event_type", "").lower()
        event_mapping = {
            "issues": IntentCategory.BUG_REPORT,
            "pull_request": IntentCategory.CODE_IMPROVEMENT,
            "push": IntentCategory.CODE_IMPROVEMENT,
        }
        if category == event_mapping.get(event_type):
            score += 0.2
        
        return score, matched
    
    def _calculate_confidence(
        self, 
        best_score: float, 
        all_scores: Dict[IntentCategory, float]
    ) -> float:
        """Calculate confidence score based on best match and score distribution."""
        if not all_scores:
            return 0.0
        
        base_confidence = min(best_score / 2.0, 1.0)
        
        sorted_scores = sorted(all_scores.values(), reverse=True)
        if len(sorted_scores) >= 2:
            margin = sorted_scores[0] - sorted_scores[1]
            margin_boost = min(margin * 0.2, 0.2)
        else:
            margin_boost = 0
        
        confidence = base_confidence + margin_boost
        
        if best_score > 1.5:
            confidence = max(confidence, 0.8)
        
        return min(confidence, 1.0)
    
    def _get_confidence_level(self, confidence: float) -> ConfidenceLevel:
        """Map confidence score to confidence level."""
        if confidence >= 0.9:
            return ConfidenceLevel.HIGH
        elif confidence >= 0.7:
            return ConfidenceLevel.MEDIUM
        else:
            return ConfidenceLevel.LOW


# Global classifier instance
_classifier: Optional[IntentClassifier] = None


def get_classifier() -> IntentClassifier:
    """Get or create the global classifier instance."""
    global _classifier
    if _classifier is None:
        _classifier = IntentClassifier()
    return _classifier


def classify_intent(
    payload: Dict[str, Any],
    context: Optional[Dict[str, Any]] = None
) -> IntentClassification:
    """Classify the intent of a request."""
    classifier = get_classifier()
    return classifier.classify(payload, context)


def batch_classify(
    payloads: List[Dict[str, Any]],
    context: Optional[Dict[str, Any]] = None
) -> List[IntentClassification]:
    """Classify multiple requests in batch."""
    classifier = get_classifier()
    return [classifier.classify(p, context) for p in payloads]


def register_intent_keywords(
    category: IntentCategory,
    keywords: List[str]
) -> None:
    """Register additional keywords for an intent category."""
    if category in INTENT_KEYWORDS:
        INTENT_KEYWORDS[category].extend(keywords)
    else:
        INTENT_KEYWORDS[category] = keywords


def get_intent_stats(
    payloads: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """Get statistics about intent distribution in a batch of payloads."""
    classifications = batch_classify(payloads)
    
    category_counts: Dict[str, int] = {}
    confidence_sum = 0.0
    high_confidence_count = 0
    
    for classification in classifications:
        cat = classification.category.value
        category_counts[cat] = category_counts.get(cat, 0) + 1
        confidence_sum += classification.confidence
        if classification.confidence_level == ConfidenceLevel.HIGH:
            high_confidence_count += 1
    
    total = len(classifications)
    
    return {
        "total_requests": total,
        "category_distribution": category_counts,
        "average_confidence": confidence_sum / total if total > 0 else 0,
        "high_confidence_percentage": (high_confidence_count / total * 100) if total > 0 else 0,
    }


# Advanced classification using LLM

async def classify_with_llm(
    payload: Dict[str, Any],
    context: Optional[Dict[str, Any]] = None,
    model: str = "gpt-4"
) -> IntentClassification:
    """Classify intent using an LLM."""
    try:
        import openai
    except ImportError:
        return classify_intent(payload, context)
    
    text = str(payload)
    
    prompt = f"""Classify the following request into one of these categories:
- feature_request: Request for new functionality
- bug_report: Report of something broken
- code_improvement: Refactoring or optimization
- review: Request for code review
- deployment: Deployment or release request
- question: Question or documentation request
- unknown: Unclear or doesn't fit above

Request: {text}

Respond with JSON format:
{{"category": "<category>", "confidence": <0.0-1.0>, "keywords": ["word1", "word2"]}}"""
    
    try:
        response = await openai.ChatCompletion.acreate(
            model=model,
            messages=[
                {"role": "system", "content": "You are an intent classification assistant."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.0
        )
        
        result = response.choices[0].message.content
        data = eval(result)
        
        category = IntentCategory(data.get("category", "unknown"))
        confidence = float(data.get("confidence", 0.5))
        keywords = data.get("keywords", [])
        
        return IntentClassification(
            category=category,
            confidence=confidence,
            keywords=keywords,
            confidence_level=ConfidenceLevel.HIGH if confidence > 0.9 else 
                           ConfidenceLevel.MEDIUM if confidence > 0.7 else 
                           ConfidenceLevel.LOW
        )
    except Exception as e:
        print(f"LLM classification failed: {e}, falling back to keyword matching")
        return classify_intent(payload, context)
