"""
Rules engine for configurable anomaly detection.

Allows definition of custom rules for pattern detection
beyond the built-in statistical patterns.
"""

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Optional
from uuid import UUID, uuid4

logger = logging.getLogger(__name__)


class RuleOperator(Enum):
    """Operators for rule conditions."""

    EQUALS = "eq"
    NOT_EQUALS = "ne"
    GREATER_THAN = "gt"
    GREATER_OR_EQUAL = "gte"
    LESS_THAN = "lt"
    LESS_OR_EQUAL = "lte"
    CONTAINS = "contains"
    MATCHES = "matches"  # Regex
    IN = "in"
    NOT_IN = "not_in"


@dataclass
class RuleCondition:
    """A single condition in a rule."""

    field: str  # Field path, e.g., "amount" or "entity.type"
    operator: RuleOperator
    value: Any


@dataclass
class Rule:
    """A detection rule."""

    id: UUID = field(default_factory=uuid4)
    name: str = ""
    description: str = ""
    conditions: list[RuleCondition] = field(default_factory=list)
    severity: str = "medium"  # low, medium, high, critical
    confidence: float = 0.8
    enabled: bool = True
    category: str = "custom"

    # When all conditions must match (AND) vs any (OR)
    require_all: bool = True

    # Metadata
    created_at: datetime = field(default_factory=datetime.utcnow)
    created_by: str = "system"


@dataclass
class RuleMatch:
    """Result of a rule match."""

    rule: Rule
    matched_data: dict
    timestamp: datetime = field(default_factory=datetime.utcnow)


class RulesEngine:
    """
    Configurable rules engine for custom detection patterns.

    Allows analysts to define rules without code changes.
    """

    def __init__(self):
        """Initialize the rules engine."""
        self._rules: dict[UUID, Rule] = {}
        self._load_default_rules()

    def _load_default_rules(self):
        """Load default detection rules."""
        # High-value cash transaction
        self.add_rule(
            Rule(
                name="High Value Cash",
                description="Cash transaction over 50,000 SEK",
                conditions=[
                    RuleCondition(
                        field="amount",
                        operator=RuleOperator.GREATER_OR_EQUAL,
                        value=50000,
                    ),
                    RuleCondition(
                        field="transaction_type",
                        operator=RuleOperator.CONTAINS,
                        value="cash",
                    ),
                ],
                severity="high",
                confidence=0.9,
                category="aml",
            )
        )

        # Just under reporting threshold
        self.add_rule(
            Rule(
                name="Near Threshold",
                description="Transaction between 140,000 and 150,000 SEK",
                conditions=[
                    RuleCondition(
                        field="amount",
                        operator=RuleOperator.GREATER_OR_EQUAL,
                        value=140000,
                    ),
                    RuleCondition(
                        field="amount",
                        operator=RuleOperator.LESS_THAN,
                        value=150000,
                    ),
                ],
                severity="high",
                confidence=0.85,
                category="structuring",
            )
        )

        # High-risk country
        self.add_rule(
            Rule(
                name="High Risk Country",
                description="Transaction involving high-risk jurisdiction",
                conditions=[
                    RuleCondition(
                        field="counterparty_country",
                        operator=RuleOperator.IN,
                        value=[
                            "AF",
                            "IR",
                            "KP",
                            "SY",
                            "YE",
                        ],  # Example list
                    ),
                ],
                severity="critical",
                confidence=0.95,
                category="sanctions",
            )
        )

        # New entity with large transaction
        self.add_rule(
            Rule(
                name="New Entity Large Transaction",
                description="Entity less than 90 days old with transaction over 100,000 SEK",
                conditions=[
                    RuleCondition(
                        field="entity_age_days",
                        operator=RuleOperator.LESS_THAN,
                        value=90,
                    ),
                    RuleCondition(
                        field="amount",
                        operator=RuleOperator.GREATER_OR_EQUAL,
                        value=100000,
                    ),
                ],
                severity="high",
                confidence=0.75,
                category="kyc",
            )
        )

    def add_rule(self, rule: Rule) -> None:
        """Add a rule to the engine."""
        self._rules[rule.id] = rule
        logger.info(f"Added rule: {rule.name}")

    def remove_rule(self, rule_id: UUID) -> bool:
        """Remove a rule from the engine."""
        if rule_id in self._rules:
            del self._rules[rule_id]
            return True
        return False

    def get_rule(self, rule_id: UUID) -> Optional[Rule]:
        """Get a rule by ID."""
        return self._rules.get(rule_id)

    def list_rules(
        self,
        enabled_only: bool = True,
        category: Optional[str] = None,
    ) -> list[Rule]:
        """List all rules, optionally filtered."""
        rules = list(self._rules.values())

        if enabled_only:
            rules = [r for r in rules if r.enabled]

        if category:
            rules = [r for r in rules if r.category == category]

        return rules

    def evaluate(
        self,
        data: dict[str, Any],
        categories: Optional[list[str]] = None,
    ) -> list[RuleMatch]:
        """
        Evaluate data against all enabled rules.

        Args:
            data: Data to evaluate (transaction, entity, etc.)
            categories: Optional filter for rule categories

        Returns:
            List of matching rules
        """
        matches = []

        for rule in self._rules.values():
            if not rule.enabled:
                continue

            if categories and rule.category not in categories:
                continue

            if self._evaluate_rule(rule, data):
                matches.append(
                    RuleMatch(
                        rule=rule,
                        matched_data=data,
                    )
                )

        return matches

    def _evaluate_rule(self, rule: Rule, data: dict[str, Any]) -> bool:
        """
        Evaluate a single rule against data.

        Args:
            rule: Rule to evaluate
            data: Data to check

        Returns:
            True if rule matches
        """
        results = []

        for condition in rule.conditions:
            result = self._evaluate_condition(condition, data)
            results.append(result)

        if rule.require_all:
            return all(results)
        else:
            return any(results)

    def _evaluate_condition(
        self,
        condition: RuleCondition,
        data: dict[str, Any],
    ) -> bool:
        """
        Evaluate a single condition.

        Args:
            condition: Condition to evaluate
            data: Data to check

        Returns:
            True if condition is met
        """
        # Get field value (supports nested paths)
        value = self._get_field_value(data, condition.field)

        if value is None:
            return False

        try:
            return self._compare(value, condition.operator, condition.value)
        except Exception as e:
            logger.warning(f"Error evaluating condition: {e}")
            return False

    def _get_field_value(
        self,
        data: dict[str, Any],
        field_path: str,
    ) -> Any:
        """
        Get a value from nested data using dot notation.

        Args:
            data: Data dictionary
            field_path: Path like "entity.type" or "amount"

        Returns:
            Field value or None
        """
        parts = field_path.split(".")
        value = data

        for part in parts:
            if isinstance(value, dict):
                value = value.get(part)
            elif hasattr(value, part):
                value = getattr(value, part)
            else:
                return None

            if value is None:
                return None

        return value

    def _compare(
        self,
        actual: Any,
        operator: RuleOperator,
        expected: Any,
    ) -> bool:
        """
        Compare values using the specified operator.

        Args:
            actual: Actual value from data
            operator: Comparison operator
            expected: Expected value from rule

        Returns:
            Comparison result
        """
        if operator == RuleOperator.EQUALS:
            return actual == expected

        if operator == RuleOperator.NOT_EQUALS:
            return actual != expected

        if operator == RuleOperator.GREATER_THAN:
            return actual > expected

        if operator == RuleOperator.GREATER_OR_EQUAL:
            return actual >= expected

        if operator == RuleOperator.LESS_THAN:
            return actual < expected

        if operator == RuleOperator.LESS_OR_EQUAL:
            return actual <= expected

        if operator == RuleOperator.CONTAINS:
            if isinstance(actual, str):
                return expected.lower() in actual.lower()
            if isinstance(actual, (list, tuple)):
                return expected in actual
            return False

        if operator == RuleOperator.MATCHES:
            if isinstance(actual, str):
                return bool(re.match(expected, actual))
            return False

        if operator == RuleOperator.IN:
            return actual in expected

        if operator == RuleOperator.NOT_IN:
            return actual not in expected

        return False
