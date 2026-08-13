"""Tests for the immutable validation log and review-time logging.

Covers log creation and retrieval (per task and per application), the
preservation of original values on field corrections, signature/stamp evidence
review logging, the IN_REVIEW requirement, the not-found cases and pagination.
The logs are append-only: multiple events accumulate and are never overwritten.
"""

from app.database.connection import SessionLocal
from app.database.models.document import Document
from app.database.models.enums import DocumentType
from app.database.models.extracted_field import ExtractedField
from app.database.models.ocr_result import OCRResult
from app.database.models.validation_log import ValidationLog
from app.database.repositories.document_repository import DocumentRepository
from app.database.repositories.ocr_repository import OCRRepository
from app.database.repositories.visual_detection_repository import (
    VisualDetectionRepository,
)

API = "/api/v1"


def create_application(client, created_by: str = "tester") -> int:
    """Create an application via the API and return its id."""
    response = client.post(f"{API}/applications", json={"created_by": created_by})
    assert response.status_code == 201, response.text
    return response.json()["application"]["id"]


def create_task(client, application_id: int) -> int:
    """Create a validation task and return its id."""
    response = client.post(
        f"{API}/validation/tasks",
        json={"application_id": application_id},
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def start_task(client, task_id: int):
    """Start a validation task and return the response."""
    return client.post(f"{API}/validation/tasks/{task_id}/start")


def make_document(application_id: int, document_type: DocumentType) -> Document:
    """Create a document row directly and return it."""
    db = SessionLocal()
    try:
        return DocumentRepository(db).create(
            application_id=application_id,
            document_type=document_type,
            original_filename="scan.pdf",
            stored_file_path="/tmp/scan.pdf",
            file_type="application/pdf",
        )
    finally:
        db.close()


def make_extracted_field(
    application_id: int,
    field_name: str = "account_number",
    value: str = "123456789",
) -> int:
    """Create a document + OCR result + extracted field and return field id."""
    db = SessionLocal()
    try:
        document = DocumentRepository(db).create(
            application_id=application_id,
            document_type=DocumentType.TRIPARTITE_AGREEMENT,
            original_filename="scan.pdf",
            stored_file_path="/tmp/scan.pdf",
            file_type="application/pdf",
        )
        ocr = OCRRepository(db).create(
            document_id=document.id,
            raw_ocr_text=f"{field_name}: {value}",
            ocr_engine="test",
            overall_confidence=0.95,
        )
        field = ExtractedField(
            ocr_result_id=ocr.id,
            field_name=field_name,
            extracted_value=value,
            confidence_score=0.95,
        )
        db.add(field)
        db.commit()
        db.refresh(field)
        return field.id
    finally:
        db.close()


def make_detection(
    application_id: int,
    detection_type: str = "SIGNATURE",
    is_present: bool = True,
) -> int:
    """Create a document + visual detection row and return the detection id."""
    db = SessionLocal()
    try:
        document = make_document(
            application_id,
            DocumentType.AUTHORITY_LETTER,
        )
        detection = VisualDetectionRepository(db).upsert(
            document_id=document.id,
            detection_type=detection_type,
            is_present=is_present,
            confidence=0.91,
        )
        return detection.id
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


# --- Retrieval --------------------------------------------------------------


def test_get_task_logs(client):
    application_id = create_application(client)
    task_id = create_task(client, application_id)
    start_task(client, task_id)

    response = client.get(f"{API}/validation/tasks/{task_id}/logs")

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 2
    actions = {log["action"] for log in body["logs"]}
    assert actions == {"TASK_CREATED", "TASK_STARTED"}
    first = body["logs"][0]
    assert first["validation_task_id"] == task_id
    assert first["application_id"] == application_id


def test_get_task_logs_not_found(client):
    response = client.get(f"{API}/validation/tasks/999999/logs")

    assert response.status_code == 404


def test_get_application_logs_across_runs(client):
    application_id = create_application(client)
    first = create_task(client, application_id)
    start_task(client, first)
    client.post(f"{API}/validation/tasks/{first}/complete", json={})
    second = create_task(client, application_id)

    response = client.get(f"{API}/validation/applications/{application_id}/logs")

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 4
    task_ids = {log["validation_task_id"] for log in body["logs"]}
    assert task_ids == {first, second}


def test_get_application_logs_not_found(client):
    response = client.get(f"{API}/validation/applications/999999/logs")

    assert response.status_code == 404


def test_logs_pagination(client):
    # Starting an already-started task is an illegal transition (409), so the
    # six log rows come from one legitimate TASK_CREATED + TASK_STARTED plus
    # four separate FIELD_VERIFIED events instead of repeated start() calls.
    application_id = create_application(client)
    task_id = create_task(client, application_id)
    start_task(client, task_id)

    for _ in range(4):
        field_id = make_extracted_field(application_id)
        response = client.post(
            f"{API}/validation/fields/{field_id}/verify",
            json={"validation_task_id": task_id, "result": "CONFIRMED"},
        )
        assert response.status_code == 201, response.text

    page = client.get(
        f"{API}/validation/tasks/{task_id}/logs", params={"limit": 2}
    ).json()

    assert page["total"] == 6
    assert len(page["logs"]) == 2


# --- Log immutability / accumulation ----------------------------------------


def test_logs_accumulate_never_overwritten(client):
    application_id = create_application(client)
    task_id = create_task(client, application_id)
    start_task(client, task_id)

    before = stored_logs(task_id)
    assert [log.action.value for log in before] == ["TASK_CREATED", "TASK_STARTED"]

    client.post(f"{API}/validation/tasks/{task_id}/complete", json={})
    after = stored_logs(task_id)

    assert len(after) == 3
    assert [log.action.value for log in before] == ["TASK_CREATED", "TASK_STARTED"]


# --- Field verification / correction ---------------------------------------


def test_field_correction_preserves_original_value(client):
    application_id = create_application(client)
    task_id = create_task(client, application_id)
    start_task(client, task_id)
    field_id = make_extracted_field(application_id, "account_number", "123456789")

    response = client.post(
        f"{API}/validation/fields/{field_id}/correct",
        json={
            "validation_task_id": task_id,
            "corrected_value": "1234567890",
            "reason": "OCR misread a digit",
        },
    )

    assert response.status_code == 201
    log = response.json()
    assert log["action"] == "FIELD_CORRECTED"
    assert log["check_type"] == "ACCOUNT_NUMBER"
    assert log["field_name"] == "account_number"
    assert log["previous_value"] == "123456789"
    assert log["new_value"] == "1234567890"
    assert log["result"] == "CORRECTED"
    assert log["reason"] == "OCR misread a digit"


def test_field_verification_logs(client):
    application_id = create_application(client)
    task_id = create_task(client, application_id)
    start_task(client, task_id)
    field_id = make_extracted_field(application_id, "ntn", "1234567")

    response = client.post(
        f"{API}/validation/fields/{field_id}/verify",
        json={"validation_task_id": task_id, "result": "CONFIRMED"},
    )

    assert response.status_code == 201
    log = response.json()
    assert log["action"] == "FIELD_VERIFIED"
    assert log["check_type"] == "NTN"
    assert log["result"] == "CONFIRMED"


def test_field_action_requires_review(client):
    application_id = create_application(client)
    task_id = create_task(client, application_id)
    field_id = make_extracted_field(application_id)

    response = client.post(
        f"{API}/validation/fields/{field_id}/verify",
        json={"validation_task_id": task_id, "result": "CONFIRMED"},
    )

    assert response.status_code == 400
    assert "not been started" in response.json()["detail"]


def test_field_action_field_not_found(client):
    application_id = create_application(client)
    task_id = create_task(client, application_id)
    start_task(client, task_id)

    response = client.post(
        f"{API}/validation/fields/999999/correct",
        json={"validation_task_id": task_id, "corrected_value": "x"},
    )

    assert response.status_code == 404


# --- Signature / stamp evidence review -------------------------------------


def test_signature_evidence_review(client):
    application_id = create_application(client)
    task_id = create_task(client, application_id)
    start_task(client, task_id)
    evidence_id = make_detection(application_id, "SIGNATURE", is_present=True)

    response = client.post(
        f"{API}/validation/evidence/{evidence_id}/review",
        json={"validation_task_id": task_id, "result": "CONFIRMED"},
    )

    assert response.status_code == 201
    log = response.json()
    assert log["action"] == "SIGNATURE_REVIEWED"
    assert log["check_type"] == "SIGNATURE"
    assert log["previous_value"] == "PRESENT"
    assert log["result"] == "CONFIRMED"


def test_stamp_evidence_review(client):
    application_id = create_application(client)
    task_id = create_task(client, application_id)
    start_task(client, task_id)
    evidence_id = make_detection(application_id, "STAMP", is_present=False)

    response = client.post(
        f"{API}/validation/evidence/{evidence_id}/review",
        json={
            "validation_task_id": task_id,
            "result": "REQUIRES_REVIEW",
            "comment": "Stamp is unclear",
        },
    )

    assert response.status_code == 201
    log = response.json()
    assert log["action"] == "STAMP_REVIEWED"
    assert log["check_type"] == "STAMP"
    assert log["previous_value"] == "NOT_PRESENT"
    assert log["result"] == "REQUIRES_REVIEW"
    assert log["reason"] == "Stamp is unclear"


def test_evidence_review_requires_review(client):
    application_id = create_application(client)
    task_id = create_task(client, application_id)
    evidence_id = make_detection(application_id, "SIGNATURE")

    response = client.post(
        f"{API}/validation/evidence/{evidence_id}/review",
        json={"validation_task_id": task_id, "result": "CONFIRMED"},
    )

    assert response.status_code == 400


def test_evidence_review_not_found(client):
    application_id = create_application(client)
    task_id = create_task(client, application_id)
    start_task(client, task_id)

    response = client.post(
        f"{API}/validation/evidence/999999/review",
        json={"validation_task_id": task_id, "result": "CONFIRMED"},
    )

    assert response.status_code == 404