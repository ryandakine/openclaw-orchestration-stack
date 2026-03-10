"""
OpenClaw Decision Engine Router

Makes routing decisions based on intent classification and request content.
"""

import os
import re
from typing import Any, Dict, List, Optional, Set
from pathlib import Path

import yaml

from .intent import IntentCategory, IntentClassification, ConfidenceLevel
from ..schemas.action_plan import (
    WorkerType, 
    ActionType, 
    RoutingDecision,
    RoutingConfig
)


class RoutingError(Exception):
    """Raised when routing decision cannot be made."""
    pass


class ConfidenceTooLowError(RoutingError):
    """Raised when confidence in routing decision is too low."""
    pass


# Default routing configuration
DEFAULT_CONFIG = RoutingConfig(
    default_worker=WorkerType.DEVCLAW,
    confidence_threshold=0.7,
    auto_review_threshold=0.9,
    max_retries=3,
    intent_routing={
        IntentCategory.FEATURE_REQUEST: WorkerType.DEVCLAW,
        IntentCategory.BUG_REPORT: WorkerType.DEVCLAW,
        IntentCategory.CODE_IMPROVEMENT: WorkerType.DEVCLAW,
        IntentCategory.REVIEW: WorkerType.SYMPHONY,
        IntentCategory.DEPLOYMENT: WorkerType.SYMPHONY,
        IntentCategory.QUESTION: WorkerType.DEVCLAW,
        IntentCategory.UNKNOWN: WorkerType.DEVCLAW,
    },
    action_routing={
        ActionType.HUMAN_REVIEW: WorkerType.SYMPHONY,
        ActionType.DEPLOYMENT: WorkerType.SYMPHONY,
    }
)

# Security-sensitive keywords that should trigger review
SECURITY_KEYWORDS: Set[str] = {
    "auth", "authentication", "authorize", "password", "credential",
    "secret", "token", "jwt", "oauth", "login", "logout",
    "permission", "role", "admin", "root", "sudo",
    "encrypt", "decrypt", "hash", "salt", "cipher",
    "firewall", "ssl", "tls", "certificate", "https",
    "sql injection", "xss", "csrf", "vulnerability"
}

# Deployment-related keywords
DEPLOYMENT_KEYWORDS: Set[str] = {
    "deploy", "deployment", "release", "production", "prod",
    "publish", "ship", "launch", "go live", "rollout"
}

# Destructive operation keywords
DESTRUCTIVE_KEYWORDS: Set[str] = {
    "delete", "drop", "remove", "destroy", "purge",
    "truncate", "wipe", "clean", "erase"
}

# Action type mappings from intent and payload
ACTION_MAPPINGS: Dict[IntentCategory, List[ActionType]] = {
    IntentCategory.FEATURE_REQUEST: [
        ActionType.CODE_GENERATION,
        ActionType.DOCUMENTATION
    ],
    IntentCategory.BUG_REPORT: [
        ActionType.BUG_FIX,
        ActionType.TEST_GENERATION
    ],
    IntentCategory.CODE_IMPROVEMENT: [
        ActionType.ANALYSIS,
        ActionType.REFACTORING
    ],
    IntentCategory.REVIEW: [
        ActionType.CODE_REVIEW,
        ActionType.HUMAN_REVIEW
    ],
    IntentCategory.DEPLOYMENT: [
        ActionType.DEPLOYMENT,
        ActionType.HUMAN_REVIEW
    ],
    IntentCategory.QUESTION: [
        ActionType.ANALYSIS,
        ActionType.DOCUMENTATION
    ],
    IntentCategory.UNKNOWN: [
        ActionType.ANALYSIS
    ],
}

# Load configuration from file if available
_config: Optional[RoutingConfig] = None


def load_config(config_path: Optional[str] = None) -> RoutingConfig:
    """
    Load routing configuration from YAML file.
    
    Args:
        config_path: Path to config file. If None, uses default locations.
    
    Returns:
        RoutingConfig instance
    """
    global _config
    
    if _config is not None:
        return _config
    
    if config_path is None:
        # Try default locations
        possible_paths = [
            Path(__file__).parent.parent / "config" / "routes.yaml",
            Path("openclaw/config/routes.yaml"),
            Path(os.environ.get("OPENCLAW_CONFIG", "")) / "routes.yaml",
        ]
    else:
        possible_paths = [Path(config_path)]
    
    for path in possible_paths:
        if path.exists():
            try:
                with open(path) as f:
                    data = yaml.safe_load(f)
                _config = RoutingConfig(**data.get("routing", {}))
                return _config
            except Exception as e:
                print(f"Warning: Failed to load config from {path}: {e}")
                continue
    
    # Use default config
    _config = DEFAULT_CONFIG
    return _config


def reload_config():
    """Force reload of configuration from file."""
    global _config
    _config = None
    return load_config()


def extract_keywords(text: str) -> Set[str]:
    """Extract relevant keywords from text."""
    # Convert to lowercase and extract words
    words = set(re.findall(r'\b[a-zA-Z_]+\b', text.lower()))
    return words


def detect_security_concerns(payload: Dict[str, Any]) -> tuple[bool, List[str]]:
    """
    Detect if the request involves security concerns.
    
    Returns:
        Tuple of (has_concerns, list_of_concerns)
    """
    concerns = []
    
    # Convert payload to string for analysis
    payload_text = str(payload).lower()
    
    for keyword in SECURITY_KEYWORDS:
        if keyword in payload_text:
            concerns.append(keyword)
    
    return len(concerns) > 0, concerns


def detect_deployment_request(payload: Dict[str, Any]) -> bool:
    """Detect if the request is a deployment request."""
    payload_text = str(payload).lower()
    return any(keyword in payload_text for keyword in DEPLOYMENT_KEYWORDS)


def detect_destructive_operation(payload: Dict[str, Any]) -> bool:
    """Detect if the request involves destructive operations."""
    payload_text = str(payload).lower()
    return any(keyword in payload_text for keyword in DESTRUCTIVE_KEYWORDS)


def determine_action_type(
    intent: IntentCategory,
    payload: Dict[str, Any],
    context: Optional[Dict[str, Any]] = None
) -> ActionType:
    """
    Determine the specific action type based on intent and payload.
    
    Args:
        intent: Classified intent
        payload: Request payload
        context: Additional context
    
    Returns:
        ActionType enum value
    """
    context = context or {}
    
    # Check for explicit type in payload
    payload_type = payload.get("type", "").lower()
    
    # Map explicit types
    type_mapping = {
        "code_generation": ActionType.CODE_GENERATION,
        "code_review": ActionType.CODE_REVIEW,
        "refactoring": ActionType.REFACTORING,
        "bug_fix": ActionType.BUG_FIX,
        "test_generation": ActionType.TEST_GENERATION,
        "deployment": ActionType.DEPLOYMENT,
        "documentation": ActionType.DOCUMENTATION,
        "analysis": ActionType.ANALYSIS,
        "human_review": ActionType.HUMAN_REVIEW,
    }
    
    if payload_type in type_mapping:
        return type_mapping[payload_type]
    
    # Check for deployment
    if detect_deployment_request(payload):
        return ActionType.DEPLOYMENT
    
    # Check for review request
    payload_text = payload.get("description", "").lower()
    if "review" in payload_text or intent == IntentCategory.REVIEW:
        return ActionType.CODE_REVIEW
    
    # Use intent-based mapping
    possible_actions = ACTION_MAPPINGS.get(intent, [ActionType.ANALYSIS])
    
    # Return first match or default
    return possible_actions[0]


def calculate_routing_confidence(
    intent: IntentClassification,
    payload: Dict[str, Any],
    context: Optional[Dict[str, Any]] = None
) -> float:
    """
    Calculate confidence in the routing decision.
    
    Args:
        intent: Intent classification result
        payload: Request payload
        context: Additional context
    
    Returns:
        Confidence score (0.0 - 1.0)
    """
    base_confidence = intent.confidence
    
    # Adjust based on payload clarity
    description = payload.get("description", "")
    if len(description) > 100:
        base_confidence += 0.05
    elif len(description) < 20:
        base_confidence -= 0.1
    
    # Adjust based on context availability
    context = context or {}
    if context.get("source") in ["github_webhook", "api", "cli"]:
        base_confidence += 0.05
    
    # Penalize unknown intent
    if intent.category == IntentCategory.UNKNOWN:
        base_confidence -= 0.3
    
    # Clamp to valid range
    return max(0.0, min(1.0, base_confidence))


def should_require_review(
    routing: RoutingDecision,
    intent: IntentClassification,
    payload: Dict[str, Any],
    config: RoutingConfig
) -> bool:
    """
    Determine if the task requires human review.
    
    Args:
        routing: Routing decision
        intent: Intent classification
        payload: Request payload
        config: Routing configuration
    
    Returns:
        True if review is required
    """
    # Always review if confidence is low
    if intent.confidence_level == ConfidenceLevel.LOW:
        return True
    
    # Always review SYMPHONY tasks
    if routing.worker_type == WorkerType.SYMPHONY:
        return True
    
    # Always review deployments
    if routing.action_type == ActionType.DEPLOYMENT:
        return True
    
    # Review security concerns
    has_security, _ = detect_security_concerns(payload)
    if has_security:
        return True
    
    # Review destructive operations
    if detect_destructive_operation(payload):
        return True
    
    # Review if confidence is below auto-review threshold
    if routing.confidence < config.auto_review_threshold:
        return True
    
    return False


def route_to(
    intent: IntentClassification,
    payload: Dict[str, Any],
    context: Optional[Dict[str, Any]] = None,
    config: Optional[RoutingConfig] = None
) -> RoutingDecision:
    """
    Make a routing decision based on intent and request content.
    
    This is the main entry point for the decision engine.
    
    Args:
        intent: Intent classification result
        payload: Request payload
        context: Additional context for routing
        config: Optional routing configuration
    
    Returns:
        RoutingDecision with worker assignment and action type
    
    Raises:
        ConfidenceTooLowError: If confidence is below threshold
        RoutingError: If routing cannot be determined
    """
    config = config or load_config()
    context = context or {}
    
    # Determine target worker
    worker_type = config.intent_routing.get(intent.category, config.default_worker)
    
    # Determine action type
    action_type = determine_action_type(intent.category, payload, context)
    
    # Override worker for specific action types
    if action_type in config.action_routing:
        worker_type = config.action_routing[action_type]
    
    # Calculate confidence
    confidence = calculate_routing_confidence(intent, payload, context)
    
    # Check minimum confidence threshold
    if confidence < config.confidence_threshold:
        raise ConfidenceTooLowError(
            f"Routing confidence ({confidence:.2f}) below threshold "
            f"({config.confidence_threshold:.2f}). Request clarification."
        )
    
    # Build reasoning
    reasons = [
        f"Intent classified as {intent.category.value} "
        f"with {intent.confidence_level.value} confidence ({intent.confidence:.2f})"
    ]
    
    # Add security concern if detected
    has_security, security_concerns = detect_security_concerns(payload)
    if has_security:
        reasons.append(f"Security keywords detected: {', '.join(security_concerns)}")
    
    # Add deployment detection
    if detect_deployment_request(payload):
        reasons.append("Deployment-related keywords detected")
    
    # Add destructive operation warning
    if detect_destructive_operation(payload):
        reasons.append("Destructive operations detected")
    
    # Create routing decision
    routing = RoutingDecision(
        worker_type=worker_type,
        action_type=action_type,
        confidence=confidence,
        reasoning="; ".join(reasons),
        requires_review=False,  # Will be set below
        estimated_effort=estimate_effort(payload),
        priority=calculate_priority(intent, payload, context)
    )
    
    # Determine if review is required
    routing.requires_review = should_require_review(routing, intent, payload, config)
    
    return routing


def estimate_effort(payload: Dict[str, Any]) -> str:
    """
    Estimate the effort required for the task.
    
    Returns:
        "small", "medium", or "large"
    """
    description = payload.get("description", "")
    
    # Simple heuristic based on description length and complexity
    word_count = len(description.split())
    
    if word_count < 20:
        return "small"
    elif word_count < 100:
        return "medium"
    else:
        return "large"


def calculate_priority(
    intent: IntentCategory,
    payload: Dict[str, Any],
    context: Optional[Dict[str, Any]] = None
) -> int:
    """
    Calculate task priority (1-10, higher = more urgent).
    
    Args:
        intent: Intent classification
        payload: Request payload
        context: Additional context
    
    Returns:
        Priority score (1-10)
    """
    base_priority = 5
    
    # Bug reports get higher priority
    if intent == IntentCategory.BUG_REPORT:
        base_priority += 2
    
    # Security issues get highest priority
    has_security, _ = detect_security_concerns(payload)
    if has_security:
        base_priority += 3
    
    # Urgent keywords
    description = payload.get("description", "").lower()
    urgent_keywords = ["urgent", "critical", "blocking", "asap", "emergency"]
    if any(kw in description for kw in urgent_keywords):
        base_priority += 2
    
    # Clamp to valid range
    return max(1, min(10, base_priority))


def get_routing_rules() -> Dict[str, Any]:
    """Get current routing rules for inspection."""
    config = load_config()
    
    return {
        "intent_routing": {
            intent.value: worker.value 
            for intent, worker in config.intent_routing.items()
        },
        "action_routing": {
            action.value: worker.value 
            for action, worker in config.action_routing.items()
        },
        "thresholds": {
            "confidence_threshold": config.confidence_threshold,
            "auto_review_threshold": config.auto_review_threshold,
        },
        "default_worker": config.default_worker.value,
        "max_retries": config.max_retries
    }
