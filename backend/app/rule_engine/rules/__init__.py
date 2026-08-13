"""Business rule registry.

Collects every rule instance of the module into a deterministic, ordered
registry. The registry is the single entry point the service uses to execute
the ruleset; it also exposes lookups by id and category for tests and future
drill-downs. Rules execute in registration order, which the registry keeps
stable.
"""

from app.rule_engine.constants import RULE_CATEGORY_KEYS
from app.rule_engine.rules.base import BaseRule
from app.rule_engine.rules.cross_document_rules import (
    CrossAccountHolderRule,
    CrossAccountNumberRule,
    CrossIbanRule,
    CrossPeriodRule,
)
from app.rule_engine.rules.date_rules import (
    DateDobSanityRule,
    DateExpiryPresenceRule,
    DateIssuePrecedesExpiryRule,
    DateIssuePresenceRule,
    DatePaymentRecencyRule,
    DatePeriodRangeRule,
    DatePeriodSequenceRule,
)
from app.rule_engine.rules.document_rules import (
    DocumentAmcRule,
    DocumentAuthorityLetterRule,
    DocumentBilateralRule,
    DocumentBrdRule,
    DocumentFormalRequestRule,
    DocumentOneLinkRule,
    DocumentScheduleRule,
    DocumentTripartiteRule,
)
from app.rule_engine.rules.field_rules import (
    FieldAccountHolderPresenceRule,
    FieldAccountNumberPresenceRule,
    FieldBalancesPresenceRule,
    FieldBankNamePresenceRule,
    FieldIbanPresenceRule,
    FieldStatementPeriodPresenceRule,
)
from app.rule_engine.rules.format_rules import (
    FormatAccountNumberRule,
    FormatAmountRule,
    FormatCnicRule,
    FormatDateShapeRule,
    FormatEStampRule,
    FormatIbanRule,
)
from app.rule_engine.rules.policy_rules import (
    PolicyAccountHolderRealRule,
    PolicyBalanceReconciliationRule,
    PolicyPeriodSalaryAlignedRule,
    PolicySingleCurrencyRule,
)
from app.rule_engine.rules.quality_rules import (
    QualityConfidenceFloorRule,
    QualityNoEmptyValuesRule,
    QualityNormalizedValuesCleanRule,
    QualityTransactionCountRule,
)
from app.rule_engine.rules.visual_rules import (
    VisualSignatureAmcRule,
    VisualSignatureAuthorityLetterRule,
    VisualSignatureBilateralRule,
    VisualSignatureFormalRequestRule,
    VisualSignatureOneLinkRule,
    VisualSignatureTripartiteRule,
    VisualStampAmcRule,
    VisualStampAuthorityLetterRule,
    VisualStampBilateralRule,
    VisualStampOneLinkRule,
    VisualStampTripartiteRule,
)


class RuleRegistry:
    """Ordered registry of every rule in the module."""

    def __init__(self) -> None:
        self._rules: tuple[BaseRule, ...] = tuple(
            [
                # Document completeness (8).
                DocumentTripartiteRule(),
                DocumentBilateralRule(),
                DocumentAmcRule(),
                DocumentOneLinkRule(),
                DocumentAuthorityLetterRule(),
                DocumentScheduleRule(),
                DocumentBrdRule(),
                DocumentFormalRequestRule(),
                # Required field presence (6).
                FieldIbanPresenceRule(),
                FieldAccountNumberPresenceRule(),
                FieldAccountHolderPresenceRule(),
                FieldBankNamePresenceRule(),
                FieldStatementPeriodPresenceRule(),
                FieldBalancesPresenceRule(),


                # Format (6).
                FormatIbanRule(),
                FormatCnicRule(),
                FormatAccountNumberRule(),
                FormatAmountRule(),
                FormatDateShapeRule(),
                FormatEStampRule(),

                # Cross-document consistency (4).
                # CrossBranchCodeRule is implemented but deliberately not
                # registered: its `branch_code` field has no extraction or
                # normalization support anywhere in the pipeline (unlike the
                # other cross-document fields below, which are genuinely
                # extracted), and `_CrossDocumentRule.evaluate` FAILs (not
                # WARNING/PENDING_MANUAL_REVIEW) when a participant document
                # lacks the field. Registering it today would make every real
                # application FAIL this rule permanently. Register it once
                # branch-code extraction exists.
                CrossAccountHolderRule(),
                CrossAccountNumberRule(),
                CrossIbanRule(),
                CrossPeriodRule(),

                # Date and period (7).
                DatePeriodSequenceRule(),
                DatePeriodRangeRule(),
                DateIssuePrecedesExpiryRule(),
                DatePaymentRecencyRule(),
                DateDobSanityRule(),
                DateIssuePresenceRule(),
                DateExpiryPresenceRule(),
                # Visual verification (11).
                VisualSignatureTripartiteRule(),
                VisualSignatureAmcRule(),
                VisualSignatureOneLinkRule(),
                VisualSignatureAuthorityLetterRule(),
                VisualSignatureBilateralRule(),
                VisualSignatureFormalRequestRule(),
                VisualStampTripartiteRule(),
                VisualStampAmcRule(),
                VisualStampOneLinkRule(),
                VisualStampAuthorityLetterRule(),
                VisualStampBilateralRule(),
                # Policy compliance (4).
                PolicyAccountHolderRealRule(),
                PolicyBalanceReconciliationRule(),
                PolicySingleCurrencyRule(),
                PolicyPeriodSalaryAlignedRule(),
                # Data quality (4).
                QualityNormalizedValuesCleanRule(),
                QualityNoEmptyValuesRule(),
                QualityConfidenceFloorRule(),
                QualityTransactionCountRule(),
            ]
        )
        ids = [rule.id for rule in self._rules]
        if len(set(ids)) != len(ids):  # pragma: no cover - defensive guard
            raise ValueError("Duplicate rule ids registered")
        for rule in self._rules:
            if rule.category not in RULE_CATEGORY_KEYS:  # pragma: no cover
                raise ValueError(f"Unknown rule category {rule.category}")

    def rules(self) -> tuple[BaseRule, ...]:
        """Return every rule in stable registration order."""
        return self._rules

    def get(self, rule_id: str) -> BaseRule | None:
        """Return the rule registered under ``rule_id``, or ``None``."""
        for rule in self._rules:
            if rule.id == rule_id:
                return rule
        return None

    def by_category(self, category: str) -> tuple[BaseRule, ...]:
        """Return the rules belonging to ``category`` in registration order."""
        return tuple(rule for rule in self._rules if rule.category == category)


#: Module-level singleton consumed by the service.
REGISTRY = RuleRegistry()

__all__ = ["RuleRegistry", "REGISTRY"]
