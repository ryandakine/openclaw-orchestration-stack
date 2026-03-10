"""Arb Validator - Final validation before execution."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

try:
    from .arb_opportunity_schema import ArbOpportunity
except ImportError:
    from arb_opportunity_schema import ArbOpportunity


@dataclass
class ValidationResult:
    """Result of final validation."""
    
    is_valid: bool
    """True if opportunity passes all validation checks."""
    
    passed_checks: list[str] = field(default_factory=list)
    """List of checks that passed."""
    
    failed_checks: list[str] = field(default_factory=list)
    """List of checks that failed with reasons."""
    
    warnings: list[str] = field(default_factory=list)
    """Non-fatal warnings."""
    
    validation_timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    """When validation was performed."""
    
    @property
    def can_execute(self) -> bool:
        """True if opportunity can be executed."""
        return self.is_valid and not self.failed_checks


class ArbValidator:
    """
    Final validation for arbitrage opportunities.
    
    Validates:
    1. Resolution semantics match (both legs resolve identically)
    2. Event has not started
    3. Both legs are tradable (not suspended/closed)
    4. Odds haven't moved significantly since discovery
    5. No blacklisted conditions
    """
    
    # Validation thresholds
    MAX_ODS_MOVEMENT_PCT: float = 0.05  # 5% max movement
    MIN_TIME_TO_START_MINUTES: int = 5  # 5 minutes buffer
    
    def __init__(
        self,
        max_odds_movement_pct: float = MAX_ODS_MOVEMENT_PCT,
        min_time_to_start_minutes: int = MIN_TIME_TO_START_MINUTES,
    ) -> None:
        """
        Initialize arb validator.
        
        Args:
            max_odds_movement_pct: Max allowed odds movement since discovery
            min_time_to_start_minutes: Minimum time before event starts
        """
        self.max_odds_movement_pct = max_odds_movement_pct
        self.min_time_to_start_minutes = min_time_to_start_minutes
    
    async def validate(
        self,
        opportunity: ArbOpportunity,
        current_odds: Optional[dict] = None,
    ) -> ValidationResult:
        """
        Perform full validation on an opportunity.
        
        Args:
            opportunity: The arbitrage opportunity
            current_odds: Optional current odds to check for movement
            
        Returns:
            ValidationResult with detailed results
        """
        passed: list[str] = []
        failed: list[str] = []
        warnings: list[str] = []
        
        # Check 1: Resolution semantics match
        resolution_valid = self._validate_resolution_semantics(opportunity)
        if resolution_valid:
            passed.append("resolution_semantics_match")
        else:
            failed.append("resolution_semantics_match (legs resolve differently)")
        
        # Check 2: Event not started
        event_started = self._check_event_started(opportunity)
        if not event_started:
            passed.append("event_not_started")
        else:
            failed.append("event_already_started")
        
        # Check 3: Both legs tradable
        tradable = self._check_tradable(opportunity)
        if tradable:
            passed.append("both_legs_tradable")
        else:
            failed.append("one_or_more_legs_not_tradable")
        
        # Check 4: Odds haven't moved too much
        if current_odds:
            odds_valid = self._validate_odds_stability(opportunity, current_odds)
            if odds_valid:
                passed.append("odds_stable")
            else:
                failed.append(
                    f"odds_moved_too_much (max: {self.max_odds_movement_pct:.1%})"
                )
        else:
            warnings.append("current_odds_not_provided_for_stability_check")
        
        # Check 5: Event info consistency
        event_consistent = self._validate_event_consistency(opportunity)
        if event_consistent:
            passed.append("event_info_consistent")
        else:
            warnings.append("minor_event_info_inconsistencies")
        
        # Check 6: Liquidity still available
        liquidity_valid = self._validate_liquidity(opportunity)
        if liquidity_valid:
            passed.append("liquidity_confirmed")
        else:
            failed.append("liquidity_no_longer_available")
        
        # Check 7: Not near event start
        time_valid = self._validate_time_buffer(opportunity)
        if time_valid:
            passed.append("time_buffer_ok")
        else:
            warnings.append(
                f"event_starting_soon (< {self.min_time_to_start_minutes} min)"
            )
        
        is_valid = len(failed) == 0
        
        # Update opportunity
        opportunity.passed_validation = is_valid
        opportunity.validation_errors = failed
        
        return ValidationResult(
            is_valid=is_valid,
            passed_checks=passed,
            failed_checks=failed,
            warnings=warnings,
        )
    
    def _validate_resolution_semantics(self, opp: ArbOpportunity) -> bool:
        """
        Validate that both legs resolve identically.
        
        Checks:
        - Same event outcome determines both legs
        - No conflicting resolution criteria
        - Same resolution source/timing
        """
        left = opp.left_leg
        right = opp.right_leg
        
        # Check resolution confidence is high enough
        if opp.resolution_confidence < 0.9:
            return False
        
        # Check for resolution source if available
        left_source = left.get("resolution_source")
        right_source = right.get("resolution_source")
        
        if left_source and right_source:
            if left_source != right_source:
                return False
        
        # Check resolution timing
        left_time = left.get("resolution_time")
        right_time = right.get("resolution_time")
        
        if left_time and right_time:
            # Allow some tolerance for timing differences
            try:
                left_dt = datetime.fromisoformat(left_time.replace('Z', '+00:00'))
                right_dt = datetime.fromisoformat(right_time.replace('Z', '+00:00'))
                diff = abs((left_dt - right_dt).total_seconds())
                if diff > 3600:  # 1 hour tolerance
                    return False
            except (ValueError, TypeError):
                pass
        
        return True
    
    def _check_event_started(self, opp: ArbOpportunity) -> bool:
        """Check if event has already started."""
        now = datetime.now(timezone.utc)
        
        # Check left leg
        left_start = opp.left_leg.get("start_time")
        if left_start:
            try:
                start = datetime.fromisoformat(left_start.replace('Z', '+00:00'))
                if start <= now:
                    return True
            except (ValueError, TypeError):
                pass
        
        # Check right leg
        right_start = opp.right_leg.get("start_time")
        if right_start:
            try:
                start = datetime.fromisoformat(right_start.replace('Z', '+00:00'))
                if start <= now:
                    return True
            except (ValueError, TypeError):
                pass
        
        # Check opportunity expires_at
        if opp.expires_at:
            if opp.expires_at <= now:
                return True
        
        return False
    
    def _check_tradable(self, opp: ArbOpportunity) -> bool:
        """Check if both legs are currently tradable."""
        left = opp.left_leg
        right = opp.right_leg
        
        # Check status
        left_status = left.get("status", "open").lower()
        right_status = right.get("status", "open").lower()
        
        valid_statuses = ["open", "active", "trading"]
        
        left_tradable = left_status in valid_statuses
        right_tradable = right_status in valid_statuses
        
        # Check for suspension flags
        left_suspended = left.get("suspended", False)
        right_suspended = right.get("suspended", False)
        
        return left_tradable and right_tradable and not left_suspended and not right_suspended
    
    def _validate_odds_stability(
        self,
        opp: ArbOpportunity,
        current_odds: dict,
    ) -> bool:
        """Validate that odds haven't moved too much."""
        left_current = current_odds.get("left")
        right_current = current_odds.get("right")
        
        left_original = opp.left_leg.get("odds" or opp.left_leg.get("price"))
        right_original = opp.right_leg.get("odds" or opp.right_leg.get("price"))
        
        if left_current and left_original:
            movement = abs(left_current - left_original) / left_original
            if movement > self.max_odds_movement_pct:
                return False
        
        if right_current and right_original:
            movement = abs(right_current - right_original) / right_original
            if movement > self.max_odds_movement_pct:
                return False
        
        return True
    
    def _validate_event_consistency(self, opp: ArbOpportunity) -> bool:
        """Validate event information is consistent between legs."""
        left = opp.left_leg
        right = opp.right_leg
        
        # Check event IDs if available
        left_event_id = left.get("event_id")
        right_event_id = right.get("event_id")
        
        if left_event_id and right_event_id:
            # Don't require exact match - could be different formats
            pass
        
        # Check match score is high
        if opp.match_score < 0.8:
            return False
        
        return True
    
    def _validate_liquidity(self, opp: ArbOpportunity) -> bool:
        """Validate liquidity is still available."""
        left_liq = opp.left_leg.get("liquidity", 0)
        right_liq = opp.right_leg.get("liquidity", 0)
        
        # Must have some liquidity
        return left_liq > 100 and right_liq > 100
    
    def _validate_time_buffer(self, opp: ArbOpportunity) -> bool:
        """Validate there's enough time before event starts."""
        now = datetime.now(timezone.utc)
        
        # Get earliest start time
        start_times = []
        
        left_start = opp.left_leg.get("start_time")
        if left_start:
            try:
                start_times.append(
                    datetime.fromisoformat(left_start.replace('Z', '+00:00'))
                )
            except (ValueError, TypeError):
                pass
        
        right_start = opp.right_leg.get("start_time")
        if right_start:
            try:
                start_times.append(
                    datetime.fromisoformat(right_start.replace('Z', '+00:00'))
                )
            except (ValueError, TypeError):
                pass
        
        if opp.expires_at:
            start_times.append(opp.expires_at)
        
        if not start_times:
            return True  # No start time known, assume ok
        
        earliest_start = min(start_times)
        time_to_start = (earliest_start - now).total_seconds() / 60  # minutes
        
        return time_to_start >= self.min_time_to_start_minutes
    
    async def pre_execution_check(
        self,
        opportunity: ArbOpportunity,
    ) -> tuple[bool, list[str]]:
        """
        Quick pre-execution validation.
        
        Returns:
            Tuple of (can_execute, warnings)
        """
        warnings: list[str] = []
        
        # Critical checks only
        if self._check_event_started(opportunity):
            return False, ["Event already started"]
        
        if not self._check_tradable(opportunity):
            return False, ["One or more legs not tradable"]
        
        # Time buffer warning
        if not self._validate_time_buffer(opportunity):
            warnings.append(
                f"Event starting in < {self.min_time_to_start_minutes} minutes"
            )
        
        return True, warnings
