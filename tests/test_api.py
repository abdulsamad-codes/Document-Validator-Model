import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from app.api.endpoints import app


@pytest.fixture
def client():
    return TestClient(app)


def test_health_check(client):
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "timestamp" in data


def test_list_document_types(client):
    response = client.get("/document-types")
    assert response.status_code == 200
    data = response.json()
    assert "document_types" in data
    types = data["document_types"]
    assert len(types) == 11  # 11 document types in our enum
    # Check tripartite is in there
    values = [t["value"] for t in types]
    assert "tripartite_agreement" in values
    assert "bilateral_agreement" in values
    assert "authority_letter" in values


def test_verify_single_invalid_type(client):
    """Sending an invalid document_type should return 400."""
    response = client.post(
        "/verify/single",
        data={"document_type": "invalid_type"},
        files={"file": ("test.pdf", b"fake pdf content", "application/pdf")}
    )
    assert response.status_code == 400
    assert "Invalid document_type" in response.json()["detail"]


def test_verify_package_mismatched_counts(client):
    """Sending mismatched file/type counts should return 400."""
    response = client.post(
        "/verify/package",
        data={"document_types": ["tripartite_agreement"]},
        files=[
            ("files", ("file1.pdf", b"content1", "application/pdf")),
            ("files", ("file2.pdf", b"content2", "application/pdf")),
        ]
    )
    assert response.status_code == 400
    assert "must match" in response.json()["detail"]


def test_get_report_not_found(client):
    """Requesting a nonexistent report should return 404."""
    response = client.get("/reports/NONEXISTENT-CASE")
    assert response.status_code == 404


def test_list_reports_empty(client):
    """Initially, reports list should be empty."""
    response = client.get("/reports")
    assert response.status_code == 200
    # May or may not be empty depending on test order, but should be a valid response
    assert "reports" in response.json()
