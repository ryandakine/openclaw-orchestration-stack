"""
Unit tests for OpenClaw Conductor modules.

Tests cover intent classification, routing decisions, action plan generation,
emitter functionality, audit logging, and idempotency checking.
"""

import os
import sys
import json
import pytest
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from openclaw.schemas.action_plan import (
    ActionPlan,
    IntentClassification,
    RoutingDecision,
    WorkerType,
    ActionType,
    IntentCategory,
    ConfidenceLevel,
    create_action_plan,
    should_require_review,
    RoutingConfig,
)
from openclaw.src.intent import (
    classify_intent,
    IntentClassifier,
    batch_classify,
    get_intent_stats,
    register_intent_keywords,
)
from openclaw.src.router import (
    route_to,
    RoutingError,
    ConfidenceTooLowError,
    detect_security_concerns,
    detect_deployment_request,
)
from openclaw.src.idempotency import (
    IdempotencyRecord,
    MemoryIdempotencyStore,
    generate_idempotency_key,
)


# ============================================
# Fixtures
# ============================================

@pytest.fixture
def sample_payload():
    """Sample request payload for testing."""
    return {
        "description": "Add a new API endpoint for user authentication",
        "type": "feature_request",
        "language": "python",
        "framework": "fastapi"
    }


@pytest.fixture
def sample_intent():
    """Sample intent classification."""
    return IntentClassification(
        category=IntentCategory.FEATURE_REQUEST,
        confidence=0.95,
        keywords=["add", "api", "authentication"],
        confidence_level=ConfidenceLevel.HIGH
    )


@pytest.fixture
def sample_routing():
    """Sample routing decision."""
    return RoutingDecision(
        worker_type=WorkerType.DEVCLAW,
        action_type=ActionType.CODE_GENERATION,
        confidence=0.92,
        reasoning="Clear feature request",
        requires_review=True,
        priority=7
    )


# ============================================
# ActionPlan Schema Tests
# ============================================

class TestActionPlanSchema:
    """Tests for ActionPlan Pydantic models."""
    
    def test_intent_classification_creation(self):
        """Test IntentClassification can be created."""
        intent = IntentClassification(
            category=IntentCategory.FEATURE_REQUEST,
            confidence=0.85,
            keywords=["add", "feature"]
        )
        
        assert intent.category == IntentCategory.FEATURE_REQUEST
        assert intent.confidence == 0.85
        assert intent.confidence_level == ConfidenceLevel.HIGH
    
    def test_intent_confidence_level_calculation(self):
        """Test confidence level is calculated correctly."""
        high = IntentClassification(
            category=IntentCategory.BUG_REPORT,
            confidence=0.95,
            keywords=[]
        )
        assert high.confidence_level == ConfidenceLevel.HIGH
        
        medium = IntentClassification(
            category=IntentCategory.BUG_REPORT,
            confidence=0.8,
            keywords=[]
        )
        assert medium.confidence_level == ConfidenceLevel.MEDIUM
        
        low = IntentClassification(
            category=IntentCategory.BUG_REPORT,
            confidence=0.5,
            keywords=[]
        )
        assert low.confidence_level == ConfidenceLevel.LOW
    
    def test_routing_decision_creation(self):
        """Test RoutingDecision can be created."""
        routing = RoutingDecision(
            worker_type=WorkerType.SYMPHONY,
            action_type=ActionType.DEPLOYMENT,
            confidence=0.88,
            reasoning="Production deployment requires review"
        )
        
        assert routing.worker_type == WorkerType.SYMPHONY
        assert routing.action_type == ActionType.DEPLOYMENT
    
    def test_action_plan_creation(self, sample_intent, sample_routing):
        """Test ActionPlan can be created."""
        plan = ActionPlan(
            plan_id="plan_test_001",
            correlation_id="corr_test_001",
            request_id="req_test_001",
            intent=sample_intent,
            routing=sample_routing
        )
        
        assert plan.plan_id == "plan_test_001"
        assert plan.routing.worker_type == WorkerType.DEVCLAW
        assert plan.version == "1.0"
    
    def test_action_plan_serialization(self, sample_intent, sample_routing):
        """Test ActionPlan can be serialized to dict."""
        plan = ActionPlan(
            plan_id="plan_test_001",
            correlation_id="corr_test_001",
            request_id="req_test_001",
            intent=sample_intent,
            routing=sample_routing
        )
        
        data = plan.dict()
        
        assert data["plan_id"] == "plan_test_001"
        assert data["intent"]["category"] == "feature_request"
        assert "created_at" in data
    
    def test_create_action_plan_helper(self):
        """Test create_action_plan helper function."""
        plan = create_action_plan(
            request_id="req_001",
            correlation_id="corr_001",
            intent_category=IntentCategory.BUG_REPORT,
            worker_type=WorkerType.DEVCLAW,
            action_type=ActionType.BUG_FIX,
            confidence=0.9,
            reasoning="Clear bug fix request"
        )
        
        assert plan.intent.category == IntentCategory.BUG_REPORT
        assert plan.routing.worker_type == WorkerType.DEVCLAW
        assert plan.routing.action_type == ActionType.BUG_FIX
    
    def test_should_require_review_high_confidence(self):
        """Test review requirement for high confidence."""
        plan = create_action_plan(
            request_id="req_001",
            correlation_id="corr_001",
            intent_category=IntentCategory.FEATURE_REQUEST,
            worker_type=WorkerType.DEVCLAW,
            action_type=ActionType.CODE_GENERATION,
            confidence=0.95
        )
        
        config = RoutingConfig(auto_review_threshold=0.9)
        assert should_require_review(plan, config) is False
    
    def test_should_require_review_symphony(self):
        """Test that SYMPHONY tasks always require review."""
        plan = create_action_plan(
            request_id="req_001",
            correlation_id="corr_001",
            intent_category=IntentCategory.DEPLOYMENT,
            worker_type=WorkerType.SYMPHONY,
            action_type=ActionType.DEPLOYMENT,
            confidence=0.95
        )
        
        config = RoutingConfig()
        assert should_require_review(plan, config) is True
    
    def test_should_require_review_deployment(self):
        """Test that deployment always requires review."""
        plan = create_action_plan(
            request_id="req_001",
            correlation_id="corr_001",
            intent_category=IntentCategory.DEPLOYMENT,
            worker_type=WorkerType.DEVCLAW,
            action_type=ActionType.DEPLOYMENT,
            confidence=0.95
        )
        
        config = RoutingConfig()
        assert should_require_review(plan, config) is True


# ============================================
# Intent Classification Tests
# ============================================

class TestIntentClassification:
    """Tests for intent classification module."""
    
    def test_classify_feature_request(self):
        """Test classification of feature request."""
        payload = {"description": "Add a new button to the dashboard"}
        result = classify_intent(payload)
        
        assert result.category == IntentCategory.FEATURE_REQUEST
        assert result.confidence > 0.5
        assert "add" in result.keywords
    
    def test_classify_bug_report(self):
        """Test classification of bug report."""
        payload = {"description": "Fix the error that occurs on login"}
        result = classify_intent(payload)
        
        assert result.category == IntentCategory.BUG_REPORT
        assert result.confidence > 0.5
        assert "fix" in result.keywords
    
    def test_classify_deployment(self):
        """Test classification of deployment request."""
        payload = {"description": "Deploy to production"}
        result = classify_intent(payload)
        
        assert result.category == IntentCategory.DEPLOYMENT
    
    def test_classify_review_request(self):
        """Test classification of review request."""
        payload = {"description": "Please review my code changes"}
        result = classify_intent(payload)
        
        assert result.category == IntentCategory.REVIEW
    
    def test_classify_with_explicit_type(self):
        """Test that explicit type is respected."""
        payload = {
            "type": "bug_fix",
            "description": "Something random"
        }
        result = classify_intent(payload)
        
        assert result.category == IntentCategory.BUG_REPORT
    
    def test_batch_classify(self):
        """Test batch classification."""
        payloads = [
            {"description": "Add feature X"},
            {"description": "Fix bug Y"},
            {"description": "Deploy to prod"},
        ]
        
        results = batch_classify(payloads)
        
        assert len(results) == 3
        assert results[0].category == IntentCategory.FEATURE_REQUEST
        assert results[1].category == IntentCategory.BUG_REPORT
        assert results[2].category == IntentCategory.DEPLOYMENT
    
    def test_get_intent_stats(self):
        """Test intent statistics."""
        payloads = [
            {"description": "Add feature X"},
            {"description": "Add feature Y"},
            {"description": "Fix bug Y"},
        ]
        
        stats = get_intent_stats(payloads)
        
        assert stats["total_requests"] == 3
        assert "feature_request" in stats["category_distribution"]
        assert "bug_report" in stats["category_distribution"]
        assert stats["category_distribution"]["feature_request"] == 2
    
    def test_register_intent_keywords(self):
        """Test registering custom keywords."""
        register_intent_keywords(IntentCategory.FEATURE_REQUEST, ["custom_keyword"])
        
        payload = {"description": "custom_keyword something"}
        result = classify_intent(payload)
        
        assert "custom_keyword" in result.keywords


# ============================================
# Router Tests
# ============================================

class TestRouter:
    """Tests for routing decision engine."""
    
    def test_route_feature_request_to_devclaw(self):
        """Test that feature requests route to DEVCLAW."""
        intent = IntentClassification(
            category=IntentCategory.FEATURE_REQUEST,
            confidence=0.9,
            keywords=["add"],
            confidence_level=ConfidenceLevel.HIGH
        )
        payload = {"description": "Add new feature"}
        
        routing = route_to(intent, payload)
        
        assert routing.worker_type == WorkerType.DEVCLAW
        assert routing.action_type == ActionType.CODE_GENERATION
    
    def test_route_deployment_to_symphony(self):
        """Test that deployments route to SYMPHONY."""
        intent = IntentClassification(
            category=IntentCategory.DEPLOYMENT,
            confidence=0.9,
            keywords=["deploy"],
            confidence_level=ConfidenceLevel.HIGH
        )
        payload = {"description": "Deploy to production"}
        
        routing = route_to(intent, payload)
        
        assert routing.worker_type == WorkerType.SYMPHONY
        assert routing.action_type == ActionType.DEPLOYMENT
    
    def test_route_review_to_symphony(self):
        """Test that reviews route to SYMPHONY."""
        intent = IntentClassification(
            category=IntentCategory.REVIEW,
            confidence=0.9,
            keywords=["review"],
            confidence_level=ConfidenceLevel.HIGH
        )
        payload = {"description": "Please review this code"}
        
        routing = route_to(intent, payload)
        
        assert routing.worker_type == WorkerType.SYMPHONY
    
    def test_route_low_confidence_raises_error(self):
        """Test that low confidence raises an error."""
        intent = IntentClassification(
            category=IntentCategory.UNKNOWN,
            confidence=0.4,
            keywords=[],
            confidence_level=ConfidenceLevel.LOW
        )
        payload = {"description": ""}
        
        with pytest.raises(ConfidenceTooLowError):
            route_to(intent, payload)
    
    def test_detect_security_concerns(self):
        """Test security concern detection."""
        payload = {"description": "Update authentication mechanism"}
        has_security, concerns = detect_security_concerns(payload)
        
        assert has_security is True
        assert "auth" in concerns
    
    def test_detect_deployment_request(self):
        """Test deployment request detection."""
        payload = {"description": "Deploy to production environment"}
        is_deployment = detect_deployment_request(payload)
        
        assert is_deployment is True
    
    def test_security_concerns_require_review(self):
        """Test that security concerns trigger review requirement."""
        intent = IntentClassification(
            category=IntentCategory.FEATURE_REQUEST,
            confidence=0.95,
            keywords=["add", "authentication"],
            confidence_level=ConfidenceLevel.HIGH
        )
        payload = {"description": "Add password authentication"}
        
        routing = route_to(intent, payload)
        
        assert routing.requires_review is True
        assert "security" in routing.reasoning.lower()


# ============================================
# Idempotency Tests
# ============================================

class TestIdempotency:
    """Tests for idempotency checking."""
    
    def test_memory_store_get_set(self):
        """Test memory store get and set operations."""
        store = MemoryIdempotencyStore()
        
        record = IdempotencyRecord(
            key="test_key",
            correlation_id="corr_001",
            plan_id="plan_001",
            created_at=datetime.utcnow(),
            response_data={"status": "success"},
            ttl_seconds=3600
        )
        
        store.set(record)
        retrieved = store.get("test_key")
        
        assert retrieved is not None
        assert retrieved.plan_id == "plan_001"
    
    def test_memory_store_expired_record(self):
        """Test that expired records are not returned."""
        store = MemoryIdempotencyStore()
        
        record = IdempotencyRecord(
            key="expired_key",
            correlation_id="corr_001",
            plan_id="plan_001",
            created_at=datetime.utcnow() - timedelta(hours=2),
            response_data={"status": "success"},
            ttl_seconds=3600  # 1 hour TTL, but created 2 hours ago
        )
        
        store.set(record)
        retrieved = store.get("expired_key")
        
        assert retrieved is None
    
    def test_memory_store_cleanup(self):
        """Test cleanup of expired records."""
        store = MemoryIdempotencyStore()
        
        # Add expired record
        expired = IdempotencyRecord(
            key="cleanup_key",
            correlation_id="corr_001",
            plan_id="plan_001",
            created_at=datetime.utcnow() - timedelta(hours=2),
            response_data={},
            ttl_seconds=3600
        )
        store.set(expired)
        
        # Add valid record
        valid = IdempotencyRecord(
            key="valid_key",
            correlation_id="corr_002",
            plan_id="plan_002",
            created_at=datetime.utcnow(),
            response_data={},
            ttl_seconds=3600
        )
        store.set(valid)
        
        cleaned = store.cleanup_expired()
        
        assert cleaned == 1
        assert store.get("cleanup_key") is None
        assert store.get("valid_key") is not None
    
    def test_generate_idempotency_key(self):
        """Test idempotency key generation."""
        key1 = generate_idempotency_key("component1", "component2")
        key2 = generate_idempotency_key("component1", "component2")
        key3 = generate_idempotency_key("different", "components")
        
        assert key1 == key2  # Deterministic
        assert key1 != key3  # Different inputs
        assert len(key1) == 32  # SHA256 truncated to 32 chars


# ============================================
# Integration Tests
# ============================================

class TestIntegration:
    """Integration tests for full request flow."""
    
    def test_full_flow_feature_request(self):
        """Test full flow for a feature request."""
        # Step 1: Classify intent
        payload = {
            "description": "Add a REST API endpoint for user management",
            "type": "feature_request",
            "language": "python"
        }
        
        intent = classify_intent(payload)
        assert intent.category == IntentCategory.FEATURE_REQUEST
        
        # Step 2: Make routing decision
        routing = route_to(intent, payload)
        assert routing.worker_type == WorkerType.DEVCLAW
        assert routing.action_type == ActionType.CODE_GENERATION
        
        # Step 3: Create action plan
        plan = create_action_plan(
            request_id="req_integration_001",
            correlation_id="corr_integration_001",
            intent_category=intent.category,
            worker_type=routing.worker_type,
            action_type=routing.action_type,
            confidence=routing.confidence,
            reasoning=routing.reasoning,
            skills=["python", "fastapi", "rest"],
            context_files=["api/routes.py"]
        )
        
        assert plan.plan_id.startswith("plan_")
        assert plan.requirements.skills == ["python", "fastapi", "rest"]
    
    def test_full_flow_deployment(self):
        """Test full flow for a deployment request."""
        payload = {
            "description": "Deploy the latest changes to production",
            "type": "deployment"
        }
        
        intent = classify_intent(payload)
        assert intent.category == IntentCategory.DEPLOYMENT
        
        routing = route_to(intent, payload)
        assert routing.worker_type == WorkerType.SYMPHONY
        assert routing.action_type == ActionType.DEPLOYMENT
        assert routing.requires_review is True
    
    def test_full_flow_security_feature(self):
        """Test full flow for a security-related feature."""
        payload = {
            "description": "Implement JWT authentication with role-based access control",
            "type": "feature_request"
        }
        
        intent = classify_intent(payload)
        assert intent.category == IntentCategory.FEATURE_REQUEST
        
        routing = route_to(intent, payload)
        assert routing.worker_type == WorkerType.DEVCLAW
        assert routing.requires_review is True  # Security concern triggers review
