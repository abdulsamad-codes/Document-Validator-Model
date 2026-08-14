"""End-to-end tests for the upload API endpoints.

Exercises the real application against the real database while the storage
backend writes to a temporary directory (see ``conftest.py``).
"""

from pathlib import Path

from tests.conftest import JPEG_BYTES, PDF_BYTES, PNG_BYTES

API = "/api/v1"


def create_application(client, created_by: str = "tester") -> int:
    """Create an application via the API and return its id."""
    response = client.post(f"{API}/applications", json={"created_by": created_by})
    assert response.status_code == 201, response.text
    return response.json()["application"]["id"]


def upload(
    client,
    application_id: int,
    filename: str = "scan.pdf",
    content: bytes = PDF_BYTES,
    content_type: str = "application/pdf",
    document_type: str = "TRIPARTITE_AGREEMENT",
    copy_number: int | None = None,
):
    """Upload a document via the API and return the response."""
    data = {"document_type": document_type}
    if copy_number is not None:
        data["copy_number"] = copy_number
    return client.post(
        f"{API}/applications/{application_id}/documents",
        data=data,
        files={"file": (filename, content, content_type)},
    )


def stored_files(storage_root: Path, application_id: int, slug: str) -> list[Path]:
    """Return the stored files for one application + document type slug."""
    directory = storage_root / "applications" / f"APP-{application_id:06d}" / slug
    return sorted(directory.glob("*")) if directory.is_dir() else []


# --- Upload ----------------------------------------------------------------


def test_upload_document_success(client, storage_root: Path):
    application_id = create_application(client)
    response = upload(client, application_id)

    assert response.status_code == 201, response.text
    body = response.json()["document"]
    assert body["application_id"] == application_id
    assert body["document_type"] == "TRIPARTITE_AGREEMENT"
    assert body["original_filename"] == "scan.pdf"
    assert body["file_type"] == "application/pdf"
    assert body["processing_status"] == "UPLOADED"
    assert "stored_file_path" not in body

    files = stored_files(storage_root, application_id, "tripartite")
    assert len(files) == 1
    assert files[0].suffix == ".pdf"
    assert files[0].read_bytes() == PDF_BYTES


def test_upload_png_document(client, storage_root: Path):
    application_id = create_application(client)
    response = upload(
        client,
        application_id,
        filename="scan.png",
        content=PNG_BYTES,
        content_type="image/png",
    )

    assert response.status_code == 201, response.text
    body = response.json()["document"]
    assert body["file_type"] == "image/png"
    assert body["document_type"] == "TRIPARTITE_AGREEMENT"

    files = stored_files(storage_root, application_id, "tripartite")
    assert len(files) == 1
    assert files[0].suffix == ".png"


def test_upload_invalid_extension(client, storage_root: Path):
    application_id = create_application(client)
    response = upload(client, application_id, filename="notes.txt", content=PDF_BYTES)

    assert response.status_code == 400, response.text
    assert stored_files(storage_root, application_id, "tripartite") == []


def test_upload_unsupported_mime(client):
    application_id = create_application(client)
    response = upload(
        client,
        application_id,
        filename="scan.pdf",
        content=PDF_BYTES,
        content_type="text/plain",
    )

    assert response.status_code == 400, response.text


def test_upload_content_extension_mismatch(client):
    application_id = create_application(client)
    response = upload(
        client,
        application_id,
        filename="scan.png",
        content=PDF_BYTES,
        content_type="application/pdf",
    )

    assert response.status_code == 400, response.text


def test_upload_oversized(client, monkeypatch):
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "max_upload_size_mb", 0)
    application_id = create_application(client)
    response = upload(client, application_id)

    assert response.status_code == 413, response.text
    assert "maximum" in response.json()["detail"].lower()


def test_upload_empty_file(client):
    application_id = create_application(client)
    response = upload(client, application_id, content=b"")

    assert response.status_code == 400, response.text


def test_upload_missing_file(client):
    application_id = create_application(client)
    response = client.post(
        f"{API}/applications/{application_id}/documents",
        data={"document_type": "TRIPARTITE_AGREEMENT"},
    )

    assert response.status_code == 400, response.text


def test_upload_unsupported_document_type(client):
    application_id = create_application(client)
    response = client.post(
        f"{API}/applications/{application_id}/documents",
        data={"document_type": "NONSENSE"},
        files={"file": ("scan.pdf", PDF_BYTES, "application/pdf")},
    )

    assert response.status_code == 422, response.text


def test_upload_duplicate_type_rejected(client):
    application_id = create_application(client)
    assert upload(client, application_id).status_code == 201
    response = upload(client, application_id, filename="scan2.pdf")

    assert response.status_code == 409, response.text
    assert "already exists" in response.json()["detail"]


def test_upload_multiple_copies_success(client):
    application_id = create_application(client)
    for copy_number in (1, 2, 3):
        response = upload(
            client,
            application_id,
            filename=f"scan-{copy_number}.pdf",
            document_type="TRIPARTITE_AGREEMENT",
            copy_number=copy_number,
        )
        assert response.status_code == 201, response.text
        assert response.json()["document"]["copy_number"] == copy_number

    response = client.get(f"{API}/applications/{application_id}/documents")
    assert response.status_code == 200, response.text
    copies = {item["copy_number"] for item in response.json()["items"]}
    assert copies == {1, 2, 3}


def test_upload_exceeds_copy_cap_rejected(client):
    application_id = create_application(client)
    for copy_number in (1, 2, 3):
        assert (
            upload(
                client,
                application_id,
                document_type="TRIPARTITE_AGREEMENT",
                copy_number=copy_number,
            ).status_code
            == 201
        )
    response = upload(
        client,
        application_id,
        document_type="TRIPARTITE_AGREEMENT",
        copy_number=4,
    )

    assert response.status_code == 409, response.text
    assert "Cannot upload more than 3 copies" in response.json()["detail"]


def test_upload_copy_slot_already_occupied(client):
    application_id = create_application(client)
    assert upload(client, application_id, copy_number=2).status_code == 201
    response = upload(client, application_id, filename="scan2.pdf", copy_number=2)

    assert response.status_code == 409, response.text
    assert "Copy 2 of TRIPARTITE_AGREEMENT already exists" in response.json()["detail"]


def test_upload_single_copy_type_limit(client):
    application_id = create_application(client)
    assert (
        upload(
            client,
            application_id,
            document_type="AUTHORITY_LETTER",
            copy_number=1,
        ).status_code
        == 201
    )
    response = upload(
        client,
        application_id,
        document_type="AUTHORITY_LETTER",
        copy_number=2,
    )

    assert response.status_code == 409, response.text
    assert "Cannot upload more than 1 copy" in response.json()["detail"]


def test_upload_missing_application(client):
    response = upload(client, 999999)

    assert response.status_code == 404, response.text


def test_upload_sanitizes_filename(client, storage_root: Path):
    application_id = create_application(client)
    response = upload(client, application_id, filename="../../etc/scan.pdf")

    assert response.status_code == 201, response.text
    assert response.json()["document"]["original_filename"] == "scan.pdf"
    files = stored_files(storage_root, application_id, "tripartite")
    assert len(files) == 1
    assert files[0].parent == storage_root / "applications" / f"APP-{application_id:06d}" / "tripartite"


# --- Application name from uploaded PDF ------------------------------------


def test_application_has_no_name_until_upload(client):
    application_id = create_application(client)
    detail = client.get(f"{API}/applications/{application_id}").json()["application"]
    assert detail["name"] is None


def test_first_upload_sets_application_name_from_filename(client):
    application_id = create_application(client)
    response = upload(client, application_id, filename="My Bank Statement.pdf")

    assert response.status_code == 201, response.text
    detail = client.get(f"{API}/applications/{application_id}").json()["application"]
    assert detail["name"] == "My Bank Statement"


def test_later_uploads_do_not_overwrite_application_name(client):
    application_id = create_application(client)

    assert upload(client, application_id, filename="First Document.pdf").status_code == 201
    assert upload(
        client,
        application_id,
        filename="Second Document.pdf",
        document_type="ACCOUNT_MAINTENANCE_CERTIFICATE",
    ).status_code == 201

    detail = client.get(f"{API}/applications/{application_id}").json()["application"]
    assert detail["name"] == "First Document"


def test_application_name_included_in_list_response(client):
    application_id = create_application(client)
    upload(client, application_id, filename="GDA Abbotabad.pdf")

    items = client.get(f"{API}/applications").json()["items"]
    matching = [item for item in items if item["id"] == application_id]
    assert len(matching) == 1
    assert matching[0]["name"] == "GDA Abbotabad"


# --- Replace ---------------------------------------------------------------


def test_replace_document(client, storage_root: Path):
    application_id = create_application(client)
    document_id = upload(client, application_id).json()["document"]["id"]
    original = stored_files(storage_root, application_id, "tripartite")[0]

    new_content = b"%PDF-1.7\n% replaced\n%%EOF\n"
    response = client.put(
        f"{API}/applications/{application_id}/documents/{document_id}",
        data={"document_type": "TRIPARTITE_AGREEMENT"},
        files={"file": ("replacement.pdf", new_content, "application/pdf")},
    )

    assert response.status_code == 200, response.text
    body = response.json()["document"]
    assert body["original_filename"] == "replacement.pdf"
    assert body["processing_status"] == "UPLOADED"

    files = stored_files(storage_root, application_id, "tripartite")
    assert len(files) == 1
    assert files[0] != original
    assert not original.exists()
    assert files[0].read_bytes() == new_content


def test_replace_document_missing(client):
    application_id = create_application(client)
    response = client.put(
        f"{API}/applications/{application_id}/documents/999999",
        data={"document_type": "TRIPARTITE_AGREEMENT"},
        files={"file": ("new.pdf", PDF_BYTES, "application/pdf")},
    )

    assert response.status_code == 404, response.text


def test_replace_document_of_other_application(client):
    application_id = create_application(client)
    other_id = create_application(client)
    document_id = upload(client, application_id).json()["document"]["id"]

    response = client.put(
        f"{API}/applications/{other_id}/documents/{document_id}",
        data={"document_type": "TRIPARTITE_AGREEMENT"},
        files={"file": ("new.pdf", PDF_BYTES, "application/pdf")},
    )

    assert response.status_code == 404, response.text


# --- Delete ----------------------------------------------------------------


def test_delete_document(client, storage_root: Path):
    application_id = create_application(client)
    document_id = upload(client, application_id).json()["document"]["id"]
    stored = stored_files(storage_root, application_id, "tripartite")[0]

    response = client.delete(f"{API}/applications/{application_id}/documents/{document_id}")

    assert response.status_code == 200, response.text
    assert client.get(f"{API}/documents/{document_id}").status_code == 404
    assert not stored.exists()
    assert stored_files(storage_root, application_id, "tripartite") == []


def test_delete_document_missing(client):
    application_id = create_application(client)
    response = client.delete(f"{API}/applications/{application_id}/documents/999999")

    assert response.status_code == 404, response.text


# --- List ------------------------------------------------------------------


def test_list_documents(client):
    application_id = create_application(client)
    first = upload(client, application_id, document_type="TRIPARTITE_AGREEMENT").json()["document"]
    second = upload(
        client,
        application_id,
        filename="bilateral.pdf",
        document_type="BILATERAL_AGREEMENT",
    ).json()["document"]

    response = client.get(f"{API}/applications/{application_id}/documents")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["total"] == 2
    assert [item["id"] for item in body["items"]] == [second["id"], first["id"]]


def test_list_documents_empty(client):
    application_id = create_application(client)
    response = client.get(f"{API}/applications/{application_id}/documents")

    assert response.status_code == 200
    assert response.json() == {"items": [], "total": 0}


def test_list_documents_pagination(client):
    application_id = create_application(client)
    upload(client, application_id, filename="a.pdf", document_type="TRIPARTITE_AGREEMENT")
    upload(client, application_id, filename="b.pdf", document_type="BILATERAL_AGREEMENT")

    response = client.get(f"{API}/applications/{application_id}/documents", params={"limit": 1})

    assert response.status_code == 200
    assert response.json()["total"] == 2
    assert len(response.json()["items"]) == 1


def test_list_documents_missing_application(client):
    response = client.get(f"{API}/applications/999999/documents")

    assert response.status_code == 404, response.text


# --- Metadata & download ---------------------------------------------------


def test_get_document_metadata(client):
    application_id = create_application(client)
    document_id = upload(client, application_id).json()["document"]["id"]

    response = client.get(f"{API}/documents/{document_id}")

    assert response.status_code == 200, response.text
    body = response.json()["document"]
    assert body["id"] == document_id
    assert body["application_id"] == application_id
    assert body["original_filename"] == "scan.pdf"
    assert "stored_file_path" not in body


def test_get_document_missing(client):
    response = client.get(f"{API}/documents/999999")

    assert response.status_code == 404, response.text


def test_download_document(client):
    application_id = create_application(client)
    document_id = upload(client, application_id).json()["document"]["id"]

    response = client.get(f"{API}/documents/{document_id}/download")

    assert response.status_code == 200, response.text
    assert response.content == PDF_BYTES
    assert response.headers["content-type"] == "application/pdf"
    disposition = response.headers["content-disposition"]
    assert "attachment" in disposition
    assert "scan.pdf" in disposition


def test_download_png_document(client):
    application_id = create_application(client)
    document_id = upload(
        client,
        application_id,
        filename="scan.png",
        content=PNG_BYTES,
        content_type="image/png",
    ).json()["document"]["id"]

    response = client.get(f"{API}/documents/{document_id}/download")

    assert response.status_code == 200
    assert response.content == PNG_BYTES


def test_download_missing_document(client):
    response = client.get(f"{API}/documents/999999/download")

    assert response.status_code == 404, response.text


# --- Application creation --------------------------------------------------


def test_create_application(client):
    response = client.post(f"{API}/applications", json={"created_by": "reviewer.alex"})

    assert response.status_code == 201, response.text
    application = response.json()["application"]
    assert application["id"] > 0
    assert application["created_by"] == "reviewer.alex"
    assert application["status"] == "SUBMITTED"
    assert "submitted_at" in application


# --- Application list & detail ---------------------------------------------


def test_list_applications(client):
    first = client.post(f"{API}/applications", json={"created_by": "alice"}).json()["application"]
    second = client.post(f"{API}/applications", json={"created_by": "bob"}).json()["application"]

    response = client.get(f"{API}/applications")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["total"] == 2
    # Ordered by submission date descending: the newest application first.
    assert [item["id"] for item in body["items"]] == [second["id"], first["id"]]


def test_list_applications_empty(client):
    response = client.get(f"{API}/applications")

    assert response.status_code == 200
    assert response.json() == {"items": [], "total": 0}


def test_list_applications_status_filter(client):
    client.post(f"{API}/applications", json={"created_by": "alice"})

    response = client.get(f"{API}/applications", params={"status": "APPROVED"})

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 0
    assert body["items"] == []


def test_list_applications_pagination(client):
    client.post(f"{API}/applications", json={"created_by": "alice"})
    client.post(f"{API}/applications", json={"created_by": "bob"})

    response = client.get(f"{API}/applications", params={"offset": 1, "limit": 1})

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 2
    assert len(body["items"]) == 1


def test_list_applications_invalid_status(client):
    response = client.get(f"{API}/applications", params={"status": "NONSENSE"})

    assert response.status_code == 422, response.text


def test_get_application(client):
    application_id = create_application(client)

    response = client.get(f"{API}/applications/{application_id}")

    assert response.status_code == 200, response.text
    application = response.json()["application"]
    assert application["id"] == application_id
    assert application["created_by"] == "tester"
    assert application["status"] == "SUBMITTED"
    assert "submitted_at" in application
    assert "updated_at" in application


def test_get_application_missing(client):
    response = client.get(f"{API}/applications/999999")

    assert response.status_code == 404, response.text
    assert "not found" in response.json()["detail"].lower()
