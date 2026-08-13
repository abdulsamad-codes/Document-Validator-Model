"""Tests for the validation workflow end to end.

Covers the full validate / reject / correction workflows, run versioning (a
correction produces a brand new run while the historical run is preserved),
transaction rollback (a task transition can never persist without its log
entry), foreign-key integrity and the concurrent-start guard.
"""

import threading

from sqlalchemy import text

from app.database.connection import SessionLocal
from app.database.models.enums import ValidationTaskStatus
from app.database.models.validation_log import ValidationLog
from app.database.models.validation_run import ValidationRun
from app.database.models.validation_task import ValidationTask
from app.validation.exceptions import ValidationError
from app.validation.services import ValidationTaskService

API = "/api/v1"


def create_application(client, created_by: str = "tester") -> int:
    """Create an application via the API and return its id."""
    response = client.post(f"{API}/applications", json={"created_by": created_by})
    assert response.status_code == 201, response.text
    return response.json()["application"]["id"]


def create_task(client, application_id: int) -> dict:
    """Create a validation task and return the response body."""
    response = client.post(
        f"{API}/validation/tasks",
        json={"application_id": application_id},
    )
    assert response.status_code == 201, response.text
    return response.json()


def start(client, task_id: int):
    """Start a validation task and return the response."""
    return client.post(f"{API}/validation/tasks/{task_id}/start")


def complete(client, task_id: int):
    """Complete a validation task and return the response."""
    return client.post(f"{API}/validation/tasks/{task_id}/complete", json={})


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


def stored_logs(task_id: int) -> list[ValidationLog]:
    """Return the stored validation logs for a task, oldest first."""
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


def stored_runs(application_id: int) -> list[ValidationRun]:
    """Return the stored validation runs for an application, oldest first."""
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


# --- Workflows --------------------------------------------------------------


def test_full_validate_workflow(client):
    application_id = create_application(client)

    task = create_task(client, application_id)
    assert task["status"] == "PENDING"
    assert task["started_at"] is None

    started = start(client, task["id"]).json()
    assert started["status"] == "IN_REVIEW"
    assert started["started_at"] is not None

    completed = complete(client, task["id"]).json()
    assert completed["status"] == "VALIDATED"
    assert completed["completed_at"] is not None

    actions = [log.action.value for log in stored_logs(task["id"])]
    assert actions == ["TASK_CREATED", "TASK_STARTED", "VALIDATION_COMPLETED"]


def test_reject_workflow(client):
    application_id = create_application(client)
    task = create_task(client, application_id)
    start(client, task["id"])

    response = reject(client, task["id"], "Critical rule failure")

    assert response.status_code == 200
    assert response.json()["status"] == "REJECTED"
    assert stored_task(task["id"]).status is ValidationTaskStatus.REJECTED


def test_correction_and_revalidation_workflow(client):
    application_id = create_application(client)

    first = create_task(client, application_id)
    start(client, first["id"])
    corrected = request_correction(
        client, first["id"], "Account number does not match across documents"
    ).json()
    assert corrected["status"] == "NEEDS_CORRECTION"
    assert corrected["validation_run_id"] == first["validation_run_id"]

    second = create_task(client, application_id)
    assert second["status"] == "PENDING"
    assert second["validation_run_id"] != first["validation_run_id"]
    start(client, second["id"])
    completed = complete(client, second["id"]).json()
    assert completed["status"] == "VALIDATED"

    runs = stored_runs(application_id)
    assert [run.run_number for run in runs] == [1, 2]

    app_logs = client.get(
        f"{API}/validation/applications/{application_id}/logs"
    ).json()
    assert app_logs["total"] == 6
    actions = {log["action"] for log in app_logs["logs"]}
    assert actions == {
        "TASK_CREATED",
        "TASK_STARTED",
        "CORRECTION_REQUESTED",
        "VALIDATION_COMPLETED",
    }


def test_revalidation_preserves_historical_run(client):
    application_id = create_application(client)
    first = create_task(client, application_id)
    start(client, first["id"])
    complete(client, first["id"])

    second = create_task(client, application_id)
    start(client, second["id"])

    # The historical run's task and logs are untouched by the new run.
    first_logs = [log.action.value for log in stored_logs(first["id"])]
    assert first_logs == ["TASK_CREATED", "TASK_STARTED", "VALIDATION_COMPLETED"]
    assert stored_task(first["id"]).status is ValidationTaskStatus.VALIDATED
    assert stored_task(second["id"]).status is ValidationTaskStatus.IN_REVIEW


# --- Transaction safety -----------------------------------------------------


def test_start_rolls_back_when_log_creation_fails(client, monkeypatch):
    application_id = create_application(client)
    task = create_task(client, application_id)

    def boom(*args, **kwargs):
        raise RuntimeError("simulated log failure")

    monkeypatch.setattr(
        "app.validation.repositories.ValidationLogRepository.create", boom
    )

    response = start(client, task["id"])

    assert response.status_code == 500

    stored = stored_task(task["id"])
    assert stored.status is ValidationTaskStatus.PENDING
    assert stored.started_at is None
    assert [log.action.value for log in stored_logs(task["id"])] == ["TASK_CREATED"]


# --- Concurrency ------------------------------------------------------------


def test_concurrent_start_only_one_succeeds(client):
    application_id = create_application(client)
    task = create_task(client, application_id)

    results: list[tuple[str, int | str]] = []
    barrier = threading.Barrier(2)

    def attempt() -> None:
        db = SessionLocal()
        try:
            service = ValidationTaskService(db)
            barrier.wait(timeout=30)
            try:
                task_obj = service.start_validation(task_id=task["id"])
                results.append(("ok", task_obj.status.value))
            except ValidationError as exc:
                results.append((exc.__class__.__name__, exc.status_code))
        finally:
            db.close()

    threads = [threading.Thread(target=attempt) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=60)

    assert len(results) == 2
    ok = [result for result in results if result[0] == "ok"]
    assert len(ok) == 1
    failed = [result for result in results if result[0] != "ok"]
    assert len(failed) == 1
    assert failed[0][0] == "ValidationAlreadyStarted"


# --- Data integrity ---------------------------------------------------------


def test_foreign_key_cascade(client):
    application_id = create_application(client)
    task = create_task(client, application_id)
    start(client, task["id"])

    db = SessionLocal()
    try:
        db.execute(
            text("DELETE FROM applications WHERE id = :application_id"),
            {"application_id": application_id},
        )
        db.commit()

        assert db.query(ValidationTask).filter_by(id=task["id"]).count() == 0
        assert (
            db.query(ValidationRun).filter_by(application_id=application_id).count()
            == 0
        )
        assert (
            db.query(ValidationLog).filter_by(validation_task_id=task["id"]).count()
            == 0
        )
    finally:
        db.close()


def test_application_missing_task_creation_rejected(client):
    response = client.post(
        f"{API}/validation/tasks",
        json={"application_id": 999999},
    )

    assert response.status_code == 404