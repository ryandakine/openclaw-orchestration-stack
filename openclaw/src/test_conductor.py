"""Tests for OpenClaw conductor."""
import pytest
from conductor import OpenClawConductor, ActionPlan, Intent, RouteTarget


class TestActionPlan:
    """Test ActionPlan dataclass."""
    
    def test_create_action_plan(self):
        """Test ActionPlan creation."""
        plan = ActionPlan.create(
            route_to=RouteTarget.DEVCLAW,
            intent=Intent.CODE_CHANGE,
            payload={"file": "test.py"}
        )
        
        assert plan.route_to == "DEVCLAW"
        assert plan.intent == "CODE_CHANGE"
        assert plan.payload == {"file": "test.py"}
        assert plan.action_id is not None
        assert plan.correlation_id is not None
        assert plan.idempotency_key is not None
    
    def test_action_plan_to_dict(self):
        """Test conversion to dictionary."""
        plan = ActionPlan.create(
            route_to=RouteTarget.SYMPHONY,
            intent=Intent.PR_FIX,
            payload={"pr_number": 42}
        )
        
        d = plan.to_dict()
        assert d["route_to"] == "SYMPHONY"
        assert d["intent"] == "PR_FIX"
        assert "audit" in d


class TestConductorRouting:
    """Test OpenClaw routing logic."""
    
    @pytest.fixture
    def conductor(self):
        """Create conductor instance."""
        return OpenClawConductor()
    
    def test_routes_code_change_to_devclaw(self, conductor):
        """CODE_CHANGE should route to DEVCLAW."""
        request = {"intent": "CODE_CHANGE", "payload": {}}
        plan = conductor.process_request(request)
        assert plan.route_to == "DEVCLAW"
        assert plan.intent == "CODE_CHANGE"
    
    def test_routes_pr_fix_to_symphony(self, conductor):
        """PR_FIX should route to SYMPHONY."""
        request = {"intent": "PR_FIX", "payload": {}}
        plan = conductor.process_request(request)
        assert plan.route_to == "SYMPHONY"
        assert plan.intent == "PR_FIX"
    
    def test_routes_db_read_to_mcp_db(self, conductor):
        """DB_READ should route to MCP_DB."""
        request = {"intent": "DB_READ", "payload": {}}
        plan = conductor.process_request(request)
        assert plan.route_to == "MCP_DB"
    
    def test_routes_notify_to_n8n(self, conductor):
        """NOTIFY should route to N8N."""
        request = {"intent": "NOTIFY", "payload": {}}
        plan = conductor.process_request(request)
        assert plan.route_to == "N8N"
    
    def test_defaults_to_code_change(self, conductor):
        """Unknown intent defaults to CODE_CHANGE."""
        request = {"intent": "UNKNOWN", "payload": {}}
        plan = conductor.process_request(request)
        assert plan.intent == "CODE_CHANGE"
        assert plan.route_to == "DEVCLAW"
    
    def test_preserves_correlation_id(self, conductor):
        """Should preserve provided correlation_id."""
        request = {
            "intent": "CODE_CHANGE",
            "payload": {},
            "correlation_id": "test-corr-123"
        }
        plan = conductor.process_request(request)
        assert plan.correlation_id == "test-corr-123"
    
    def test_preserves_idempotency_key(self, conductor):
        """Should preserve provided idempotency_key."""
        request = {
            "intent": "CODE_CHANGE",
            "payload": {},
            "idempotency_key": "test-idemp-456"
        }
        plan = conductor.process_request(request)
        assert plan.idempotency_key == "test-idemp-456"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
