import pytest
from app.rule_engine.rules.date_rules import DateIssuePresenceRule, DateExpiryPresenceRule
from app.rule_engine.rules.base import RuleContext, RuleResult, NormalizedValue
from app.database.models.enums import ValidationStatus

# Helper dummy objects
class DummyField:
    def __init__(self, field_name: str, document_id: int, value: str):
        self.field_name = field_name
        self.document_id = document_id
        self.value = value

class DummyContext(RuleContext):
    def __init__(self, fields):
        self._fields = fields

    def fields(self, field_name: str):
        return [f for f in self._fields if f.field_name == field_name]

    def values(self, field_name: str):
        return [NormalizedValue(value=f.value, document_id=f.document_id) for f in self._fields if f.field_name == field_name]

def test_issue_presence_rule_fails_when_missing():
    ctx = DummyContext(fields=[DummyField("expiry_date", 1, "2025-01-01")])
    result: RuleResult = DateIssuePresenceRule().evaluate(ctx)
    assert result.status == ValidationStatus.FAIL
    assert "missing or blank" in result.message

def test_issue_presence_rule_passes_when_present():
    ctx = DummyContext(fields=[DummyField("issue_date", 1, "2024-01-01"), DummyField("expiry_date", 1, "2025-01-01")])
    result: RuleResult = DateIssuePresenceRule().evaluate(ctx)
    assert result.status == ValidationStatus.PASS

def test_expiry_presence_rule_fails_when_missing():
    ctx = DummyContext(fields=[DummyField("issue_date", 1, "2024-01-01")])
    result: RuleResult = DateExpiryPresenceRule().evaluate(ctx)
    assert result.status == ValidationStatus.FAIL
    assert "missing or blank" in result.message

def test_expiry_presence_rule_passes_when_present():
    ctx = DummyContext(fields=[DummyField("issue_date", 1, "2024-01-01"), DummyField("expiry_date", 1, "2025-01-01")])
    result: RuleResult = DateExpiryPresenceRule().evaluate(ctx)
    assert result.status == ValidationStatus.PASS
