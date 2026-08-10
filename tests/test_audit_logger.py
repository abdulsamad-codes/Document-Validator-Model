import pytest
import json
from pathlib import Path
from app.database.audit_logger import AuditLogger


@pytest.fixture
def audit_logger(tmp_path):
    """Create an audit logger with a temporary directory."""
    return AuditLogger(log_dir=str(tmp_path))


def test_log_event(audit_logger, tmp_path):
    """Test that events are logged to JSONL file."""
    event = audit_logger.log_event(
        "TEST_EVENT",
        "CASE-001",
        {"key": "value"},
        user="test_user"
    )
    
    assert event["event_type"] == "TEST_EVENT"
    assert event["case_id"] == "CASE-001"
    assert event["user"] == "test_user"
    assert "timestamp" in event
    
    # Verify file was written
    jsonl_path = tmp_path / "audit_events.jsonl"
    assert jsonl_path.exists()
    
    with open(jsonl_path, "r") as f:
        line = f.readline().strip()
        saved_event = json.loads(line)
        assert saved_event["event_type"] == "TEST_EVENT"


def test_log_verification_started(audit_logger):
    event = audit_logger.log_verification_started(
        "CASE-002",
        ["tripartite.pdf", "bilateral.pdf"]
    )
    assert event["event_type"] == "VERIFICATION_STARTED"
    assert event["details"]["count"] == 2


def test_log_verification_completed(audit_logger):
    event = audit_logger.log_verification_completed(
        "CASE-002",
        "PASS",
        total_pass=5,
        total_fail=0
    )
    assert event["event_type"] == "VERIFICATION_COMPLETED"
    assert event["details"]["overall_status"] == "PASS"


def test_log_manual_override(audit_logger):
    event = audit_logger.log_manual_override(
        "CASE-003",
        rule_id="GEN_001_SIGNATURE",
        original_status="FAIL",
        new_status="PASS",
        reason="Verified manually by reviewer",
        user="admin_user"
    )
    assert event["event_type"] == "MANUAL_OVERRIDE"
    assert event["user"] == "admin_user"
    assert event["details"]["reason"] == "Verified manually by reviewer"


def test_get_events_for_case(audit_logger):
    """Test retrieving events filtered by case_id."""
    audit_logger.log_event("EVENT_A", "CASE-A", {"x": 1})
    audit_logger.log_event("EVENT_B", "CASE-B", {"y": 2})
    audit_logger.log_event("EVENT_C", "CASE-A", {"z": 3})
    
    events = audit_logger.get_events_for_case("CASE-A")
    assert len(events) == 2
    assert all(e["case_id"] == "CASE-A" for e in events)
    
    events_b = audit_logger.get_events_for_case("CASE-B")
    assert len(events_b) == 1


def test_get_events_empty(audit_logger):
    """Test empty result for nonexistent case."""
    events = audit_logger.get_events_for_case("NONEXISTENT")
    assert events == []
