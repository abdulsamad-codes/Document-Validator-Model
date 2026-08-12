"""Benchmark the PostgreSQL bulk queue with controlled mock processing."""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone

from app.bulk_queue.workers import drain_queue
from app.database.connection import SessionLocal
from app.database.models.application import Application
from app.database.models.document import Document
from app.database.models.enums import DocumentProcessingStatus, DocumentType
from app.database.models.queue_job import QueueJob
from app.database.repositories.queue_job_repository import QueueJobRepository
from app.core.config import get_settings


class BenchmarkProcessor:
    """Small deterministic workload that avoids OCR and AI resources."""

    def __init__(self, db):
        self.db = db

    def process_one(self, *, application_id: int, document_id: int):
        time.sleep(0.01)
        document = self.db.get(Document, document_id)
        document.processing_status = DocumentProcessingStatus.COMPLETED
        self.db.commit()
        from app.document_processing.schemas import DocumentProcessingResult, ProcessingOutcome

        return DocumentProcessingResult(
            document_id=document_id,
            file_name=document.original_filename,
            outcome=ProcessingOutcome.PROCESSED,
        )


def run_batch(document_count: int, workers: int) -> dict[str, float | int]:
    db = SessionLocal()
    try:
        application = Application(created_by="queue-benchmark")
        db.add(application)
        db.flush()
        documents = [
            Document(
                application_id=application.id,
                document_type=DocumentType.OTHER_SUPPORTING_DOCUMENT,
                copy_number=index + 1,
                original_filename=f"benchmark-{index + 1}.pdf",
                stored_file_path=f"benchmark/{application.id}/{index + 1}.pdf",
                file_type="application/pdf",
                processing_status=DocumentProcessingStatus.UPLOADED,
            )
            for index in range(document_count)
        ]
        db.add_all(documents)
        db.commit()
        QueueJobRepository(db).enqueue_uploaded_documents(
            application_id=application.id,
            max_attempts=get_settings().bulk_queue_max_attempts,
        )
    finally:
        db.close()

    started = time.perf_counter()
    summary = drain_queue(workers=workers, processor_factory=BenchmarkProcessor)
    elapsed = time.perf_counter() - started

    db = SessionLocal()
    try:
        jobs = list(
            db.query(QueueJob)
            .filter(QueueJob.application_id == application.id)
            .all()
        )
        waits = [
            (job.started_at - job.created_at).total_seconds()
            for job in jobs
            if job.started_at and job.created_at
        ]
    finally:
        db.close()

    return {
        "documents": document_count,
        "workers": workers,
        "elapsed_seconds": round(elapsed, 4),
        "documents_per_minute": round(summary.succeeded / elapsed * 60, 2),
        "average_queue_wait_seconds": round(sum(waits) / len(waits), 4),
        "worker_utilization_percent": round((document_count * 0.01) / (elapsed * workers) * 100, 2),
        "retries": summary.retried,
        "failures": summary.failed,
    }


if __name__ == "__main__":
    print(json.dumps([run_batch(size, workers) for size in (10, 40, 80) for workers in (1, 2, 3)], indent=2))
