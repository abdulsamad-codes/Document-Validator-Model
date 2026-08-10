"""
FastAPI REST API for the Document Verification System.
"""

import os
import uuid
import shutil
import tempfile
from pathlib import Path
from typing import List, Optional
from datetime import datetime

from fastapi import FastAPI, File, UploadFile, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from app.schemas.document_schemas import DocumentType, ExtractedDocument
from app.schemas.verification_schemas import VerificationReport, VerificationStatus
from app.pipeline.orchestrator import PipelineOrchestrator
from app.rules.rule_engine import RuleEngine

app = FastAPI(
    title="KPITB Document Verification API",
    description="AI-assisted financial document verification for sub-biller onboarding",
    version="0.1.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Shared instances
orchestrator = PipelineOrchestrator()
rule_engine = RuleEngine()

# In-memory store for reports (replace with DB in production)
reports_store: dict = {}


@app.get("/health")
def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}


@app.get("/document-types")
def list_document_types():
    """List all supported document types."""
    return {
        "document_types": [
            {"value": dt.value, "name": dt.name.replace("_", " ").title()}
            for dt in DocumentType
        ]
    }


@app.post("/verify/single")
async def verify_single_document(
    file: UploadFile = File(...),
    document_type: str = Form(...)
):
    """
    Upload and verify a single document.
    Returns the per-document verification result.
    """
    # Validate document type
    try:
        doc_type = DocumentType(document_type)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid document_type: '{document_type}'. Use /document-types for valid options."
        )

    # Save uploaded file to temp location
    upload_dir = Path(tempfile.mkdtemp())
    file_path = upload_dir / file.filename
    try:
        with open(file_path, "wb") as f:
            content = await file.read()
            f.write(content)

        # Run pipeline
        extracted_doc = orchestrator.process_document(file_path, doc_type)
        
        # Run rules
        doc_result = rule_engine.verify_document(extracted_doc)

        return {
            "file_name": file.filename,
            "document_type": doc_type.value,
            "result": doc_result.model_dump()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        # Cleanup temp files
        shutil.rmtree(upload_dir, ignore_errors=True)


@app.post("/verify/package")
async def verify_document_package(
    files: List[UploadFile] = File(...),
    document_types: List[str] = Form(...),
    case_id: Optional[str] = Form(None)
):
    """
    Upload and verify a full sub-biller onboarding package (multiple documents).
    Returns a complete VerificationReport with cross-document checks.
    """
    if len(files) != len(document_types):
        raise HTTPException(
            status_code=400,
            detail=f"Number of files ({len(files)}) must match number of document_types ({len(document_types)})."
        )

    if not case_id:
        case_id = f"CASE-{uuid.uuid4().hex[:8].upper()}"

    # Validate all document types first
    parsed_types = []
    for dt_str in document_types:
        try:
            parsed_types.append(DocumentType(dt_str))
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid document_type: '{dt_str}'. Use /document-types for valid options."
            )

    upload_dir = Path(tempfile.mkdtemp())
    extracted_docs: List[ExtractedDocument] = []

    try:
        # Process each file
        for uploaded_file, doc_type in zip(files, parsed_types):
            file_path = upload_dir / uploaded_file.filename
            with open(file_path, "wb") as f:
                content = await uploaded_file.read()
                f.write(content)

            extracted_doc = orchestrator.process_document(file_path, doc_type)
            extracted_docs.append(extracted_doc)

        # Generate full report with cross-document checks
        report = rule_engine.generate_verification_report(case_id, extracted_docs)
        report.verified_at = datetime.now()

        # Store the report
        reports_store[case_id] = report.model_dump()

        return report.model_dump()

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        shutil.rmtree(upload_dir, ignore_errors=True)


@app.get("/reports/{case_id}")
def get_report(case_id: str):
    """Retrieve a previously generated verification report."""
    if case_id not in reports_store:
        raise HTTPException(status_code=404, detail=f"Report '{case_id}' not found.")
    return reports_store[case_id]


@app.get("/reports")
def list_reports():
    """List all verification report case IDs."""
    return {
        "reports": [
            {"case_id": cid, "status": r.get("overall_status", "UNKNOWN")}
            for cid, r in reports_store.items()
        ]
    }
