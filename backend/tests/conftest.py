"""Shared fixtures for the upload test suite.

Uploads are exercised through the real FastAPI application and the real
``finance_verification`` database, while the storage backend is redirected to a
per-test temporary directory so the repository's ``storage/`` tree is never
touched. The database is wiped before and after every test via the cascade on
``applications`` (which removes documents, OCR data, validations and reviews).
"""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.auth.seed import seed as seed_default_account
from app.core.config import get_settings
from app.core.security import hash_password
from app.database.connection import SessionLocal
from app.database.models.user import User
from app.main import app

#: Credentials for the fixed operator identity the ``authenticated_client``
#: fixture logs in as. Safe to hardcode: ``isolated_database`` wipes every
#: user before and after each test, so there is never a collision with a
#: prior test's data.
_TEST_OPERATOR_EMPLOYEE_ID = "TEST-OPERATOR"
_TEST_OPERATOR_PASSWORD = "TestPass@123"

#: Minimal but realistic PDF payload starting with the ``%PDF-`` magic bytes.
PDF_BYTES = (
    b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n"
    b"1 0 obj\n<< /Type /Catalog >>\nendobj\n"
    b"trailer\n<< /Root 1 0 R >>\n%%EOF\n"
)

#: PNG payload starting with the PNG signature.
PNG_BYTES = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"
    b"\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde"
)

#: JPEG payload starting with the JPEG magic bytes.
JPEG_BYTES = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00\xff\xd9"


def _wipe_database() -> None:
    """Delete every application and user; dependent tables cascade."""
    db = SessionLocal()
    try:
        db.execute(text("DELETE FROM refresh_tokens"))
        db.execute(text("DELETE FROM users"))
        db.execute(text("DELETE FROM applications"))
        db.commit()
    finally:
        db.close()


@pytest.fixture()
def storage_root(tmp_path: Path) -> Path:
    """A fresh, empty storage root for the test."""
    return tmp_path / "storage"


@pytest.fixture()
def client(storage_root: Path, monkeypatch: pytest.MonkeyPatch):
    """A TestClient whose upload service writes to the temporary storage root.

    The cached settings object is mutated in place (and restored afterwards) so
    every ``UploadService`` instantiated during the test resolves the temporary
    root, while the database settings remain the real development database.
    """
    settings = get_settings()
    monkeypatch.setattr(settings, "upload_storage_root", storage_root)
    monkeypatch.setattr("app.upload.services.get_settings", lambda: settings)
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture()
def authenticated_client(client: TestClient) -> TestClient:
    """A ``client`` pre-authenticated as a fixed test operator identity.

    Every route except ``/health`` and the ``auth`` module itself requires a
    valid session (see ``app/api/__init__.py``). Tests that exercise those
    endpoints and aren't specifically testing the unauthenticated case should
    depend on this fixture instead of the raw ``client`` one -- it returns the
    same ``TestClient``, just with a valid session cookie already set, so
    every subsequent request on it carries the cookie automatically.
    """
    db = SessionLocal()
    try:
        db.add(
            User(
                employee_id=_TEST_OPERATOR_EMPLOYEE_ID,
                email="test-operator@example.test",
                name="Test Operator",
                role="Verification Officer",
                password_hash=hash_password(_TEST_OPERATOR_PASSWORD),
                is_active=True,
            )
        )
        db.commit()
    finally:
        db.close()
    response = client.post(
        f"{get_settings().api_prefix}/auth/login",
        json={
            "identifier": _TEST_OPERATOR_EMPLOYEE_ID,
            "password": _TEST_OPERATOR_PASSWORD,
            "remember": False,
        },
    )
    assert response.status_code == 200, response.text
    return client


@pytest.fixture(autouse=True)
def isolated_database():
    """Guarantee a clean database around every test."""
    _wipe_database()
    yield
    _wipe_database()


@pytest.fixture(scope="session", autouse=True)
def restore_default_account():
    """Re-create the default employee account once the whole session has run.

    ``isolated_database`` wipes every user around each test, which also removes
    the seeded ``DEFAULT_EMPLOYEE_*`` account that development and manual login
    depend on. Re-seeding afterwards keeps the local environment usable after a
    test run.
    """
    yield
    seed_default_account()
