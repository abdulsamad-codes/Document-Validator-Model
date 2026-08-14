"""Tests for the validation task API and lifecycle.

Exercises the real FastAPI application against the real database: task creation
(with its versioned run and initial log), retrieval, queue listing with filters
and pagination, and the state machine (start, complete, reject,
request-correction) including the illegal transitions, the missing-reason rules
and the results endpoint.
"""

from app.database.connection import SessionLocal
from app.database.models.enums import (
    Severity,
    ValidationStatus,
    ValidationTaskStatus,
)
from app.database.models.validation_log import ValidationLog
from app.database.models.validation_run import ValidationRun
from app.database.models.validation_task import ValidationTask
from app.database.repositories.validation_repository import ValidationRepository

API = "/api/v1"


def create_application(client, created_by: str = "tester") -> int:
    """Create an application via the API and return its id."""
    response = client.post(f"{API}/applications", json={"created_by": created_by})
    assert response.status_code == 201, response.text
    return response.json()["application"]["id"]


def create_task(
    client,
    application_id: int,
    priority: str | None = None,
    expected_status: int = 201,
):
    """Create a validation task via the API and return the response."""
    payload = {"application_id": application_id}
    if priority is not None:
        payload["priority"] = priority
    response = client.post(f"{API}/validation/tasks", json=payload)
    assert response.status_code == expected_status, response.text
    return response


def start(client, task_id: int):
    """Start a validation task and return the response."""
    return client.post(f"{API}/validation/tasks/{task_id}/start")


def complete(client, task_id: int, comment: str | None = None):
    """Complete a validation task and return the response."""
    payload = {"comment": comment} if comment is not None else {}
    return client.post(f"{API}/validation/tasks/{task_id}/complete", json=payload)


def reject(client, task_id: int, reason: str):
    """Reject a validation task and return the response."""
    return client.post(
        f"{API}/validation/tasks/{task_id}/reject",
        json={"reason": reason},
    )


def request_correction(client, task_id: int, reason: str):
    """Request a correction on a validation task and return the response."""
    return client.post(
        f"{API}/validation/tasks/{task_id}/request-correction",
        json={"reason": reason},
    )


def stored_task(task_id: int) -> ValidationTask:
    """Return the stored validation task."""
    db = SessionLocal()
    try:
        return db.get(ValidationTask, task_id)
    finally:
        db.close()


def stored_runs(application_id: int) -> list[ValidationRun]:
    """Return the stored validation runs for an application."""
    db = SessionLocal()
    try:
        return (
            db.query(ValidationRun)
            .filter_by(application_id=application_id)
            .order_by(ValidationRun.run_number)
            .all()
        )
    finally:
        db.close()


def stored_logs(task_id: int) -> list[ValidationLog]:
    """Return the stored validation logs for a task."""
    db = SessionLocal()
    try:
        return (
            db.query(ValidationLog)
            .filter_by(validation_task_id=task_id)
            .order_by(ValidationLog.id)
            .all()
        )
    finally:
        db.close()


def add_validation_result(application_id: int) -> int:
    """Insert a rule-engine validation result directly and return its id."""
    db = SessionLocal()
    try:
        result = ValidationRepository(db).create(
            application_id=application_id,
            rule_id="ACCOUNT_NUMBER_CONSISTENCY",
            rule_name="Account number consistency",
            rule_category="cross_document",
            severity=Severity.ERROR,
            status=ValidationStatus.FAIL,
            message="Account number does not match.",
        )
        return result.id
    finally:
        db.close()


# --- Creation ---------------------------------------------------------------


def test_create_task_creates_run_and_log(authenticated_client):
    application_id = create_application(authenticated_client)

    response = create_task(authenticated_client, application_id)

    task = response.json()
    assert task["status"] == "PENDING"
    assert task["priority"] == "NORMAL"
    assert task["started_at"] is None
    assert task["completed_at"] is None
    assert task["validation_run_id"] is not None

    runs = stored_runs(application_id)
    assert len(runs) == 1
    assert runs[0].run_number == 1
    assert runs[0].id == task["validation_run_id"]

    logs = stored_logs(task["id"])
    assert len(logs) == 1
    assert logs[0].action.value == "TASK_CREATED"


def test_create_task_with_priority(authenticated_client):
    application_id = create_application(authenticated_client)

    response = create_task(authenticated_client, application_id, priority="URGENT")

    assert response.status_code == 201
    assert response.json()["priority"] == "URGENT"


def test_create_task_application_not_found(authenticated_client):
    response = create_task(authenticated_client, application_id=999999, expected_status=404)

    assert response.status_code == 404
    assert "Application not found" in response.json()["detail"]


def test_create_task_rejects_active_task_conflict(authenticated_client):
    application_id = create_application(authenticated_client)
    create_task(authenticated_client, application_id)

    response = create_task(authenticated_client, application_id, expected_status=409)

    assert "active validation task" in response.json()["detail"]


def test_create_task_revalidation_allowed_after_terminal(authenticated_client):
    application_id = create_application(authenticated_client)
    first = create_task(authenticated_client, application_id).json()
    start(authenticated_client, first["id"])
    complete(authenticated_client, first["id"])

    second = create_task(authenticated_client, application_id).json()

    assert second["status"] == "PENDING"
    assert second["validation_run_id"] != first["validation_run_id"]
    runs = stored_runs(application_id)
    assert [run.run_number for run in runs] == [1, 2]


# --- Retrieval and listing --------------------------------------------------


def test_get_task(authenticated_client):
    application_id = create_application(authenticated_client)
    task_id = create_task(authenticated_client, application_id).json()["id"]

    response = authenticated_client.get(f"{API}/validation/tasks/{task_id}")

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == task_id
    assert body["application_id"] == application_id


def test_get_task_not_found(authenticated_client):
    response = authenticated_client.get(f"{API}/validation/tasks/999999")

    assert response.status_code == 404
    assert "Validation task not found" in response.json()["detail"]


def test_list_tasks_filter_and_paginate(authenticated_client):
    # One task per application: only one active task is allowed per
    # application, so the queue-wide listing is exercised across three
    # separate applications instead of three tasks on one.
    ids = [create_task(authenticated_client, create_application(authenticated_client)).json()["id"] for _ in range(3)]
    start(authenticated_client, ids[0])

    response = authenticated_client.get(f"{API}/validation/tasks")

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 3
    assert len(body["tasks"]) == 3
    assert body["limit"] == 50
    assert body["offset"] == 0

    pending = authenticated_client.get(
        f"{API}/validation/tasks", params={"status": "PENDING"}
    ).json()
    assert pending["total"] == 2
    assert all(t["status"] == "PENDING" for t in pending["tasks"])

    page = authenticated_client.get(
        f"{API}/validation/tasks", params={"offset": 1, "limit": 1}
    ).json()
    assert page["total"] == 3
    assert len(page["tasks"]) == 1


def test_list_tasks_rejects_invalid_status(authenticated_client):
    response = authenticated_client.get(f"{API}/validation/tasks", params={"status": "BOGUS"})

    assert response.status_code == 422


# --- State machine ----------------------------------------------------------


def test_start_task(authenticated_client):
    application_id = create_application(authenticated_client)
    task_id = create_task(authenticated_client, application_id).json()["id"]

    response = start(authenticated_client, task_id)

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "IN_REVIEW"
    assert body["started_at"] is not None
    assert stored_task(task_id).status is ValidationTaskStatus.IN_REVIEW


def test_start_task_twice_conflicts(authenticated_client):
    application_id = create_application(authenticated_client)
    task_id = create_task(authenticated_client, application_id).json()["id"]
    start(authenticated_client, task_id)

    response = start(authenticated_client, task_id)

    assert response.status_code == 409


def test_start_task_not_found(authenticated_client):
    response = start(authenticated_client, 999999)

    assert response.status_code == 404


def test_complete_requires_started(authenticated_client):
    application_id = create_application(authenticated_client)
    task_id = create_task(authenticated_client, application_id).json()["id"]

    response = complete(authenticated_client, task_id)

    assert response.status_code == 400
    assert "not been started" in response.json()["detail"]


def test_complete_flow(authenticated_client):
    application_id = create_application(authenticated_client)
    task_id = create_task(authenticated_client, application_id).json()["id"]
    start(authenticated_client, task_id)

    response = complete(authenticated_client, task_id, comment="All checks reviewed")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "VALIDATED"
    assert body["completed_at"] is not None

    logs = stored_logs(task_id)
    assert logs[-1].action.value == "VALIDATION_COMPLETED"
    assert logs[-1].reason == "All checks reviewed"


def test_complete_twice_conflicts(authenticated_client):
    application_id = create_application(authenticated_client)
    task_id = create_task(authenticated_client, application_id).json()["id"]
    start(authenticated_client, task_id)
    complete(authenticated_client, task_id)

    response = complete(authenticated_client, task_id)

    assert response.status_code == 409


def test_reject_requires_reason(authenticated_client):
    application_id = create_application(authenticated_client)
    task_id = create_task(authenticated_client, application_id).json()["id"]
    start(authenticated_client, task_id)

    response = reject(authenticated_client, task_id, reason="")

    assert response.status_code == 422


def test_reject_flow(authenticated_client):
    application_id = create_application(authenticated_client)
    task_id = create_task(authenticated_client, application_id).json()["id"]
    start(authenticated_client, task_id)

    response = reject(authenticated_client, task_id, reason="Missing signature")

    assert response.status_code == 200
    assert response.json()["status"] == "REJECTED"
    logs = stored_logs(task_id)
    assert logs[-1].action.value == "VALIDATION_REJECTED"
    assert logs[-1].reason == "Missing signature"


def test_request_correction_flow(authenticated_client):
    application_id = create_application(authenticated_client)
    task_id = create_task(authenticated_client, application_id).json()["id"]
    start(authenticated_client, task_id)

    response = request_correction(authenticated_client, task_id, reason="Account number mismatch")

    assert response.status_code == 200
    assert response.json()["status"] == "NEEDS_CORRECTION"
    logs = stored_logs(task_id)
    assert logs[-1].action.value == "CORRECTION_REQUESTED"
    assert logs[-1].reason == "Account number mismatch"


def test_request_correction_requires_reason(authenticated_client):
    application_id = create_application(authenticated_client)
    task_id = create_task(authenticated_client, application_id).json()["id"]
    start(authenticated_client, task_id)

    response = request_correction(authenticated_client, task_id, reason="   ")

    assert response.status_code == 422


# --- Results ----------------------------------------------------------------


def test_get_results_returns_stored_checks(authenticated_client):
    application_id = create_application(authenticated_client)
    task_id = create_task(authenticated_client, application_id).json()["id"]
    add_validation_result(application_id)

    response = authenticated_client.get(f"{API}/validation/tasks/{task_id}/results")

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    result = body["results"][0]
    assert result["rule_id"] == "ACCOUNT_NUMBER_CONSISTENCY"
    assert result["status"] == "FAIL"


def test_get_results_empty(authenticated_client):
    application_id = create_application(authenticated_client)
    task_id = create_task(authenticated_client, application_id).json()["id"]

    response = authenticated_client.get(f"{API}/validation/tasks/{task_id}/results")

    assert response.status_code == 200
    assert response.json()["total"] == 0


def test_get_results_task_not_found(authenticated_client):
    response = authenticated_client.get(f"{API}/validation/tasks/999999/results")

    assert response.status_code == 404