"""Run dedicated bulk queue worker processes.

Production deployments that want queue draining fully outside the HTTP request
lifecycle start one or more of these processes (one per host, or more when a
single worker's concurrency cap is enough):

    .venv/bin/python -m app.bulk_queue --workers 2

Workers poll the PostgreSQL queue forever, claim jobs atomically (``FOR UPDATE
SKIP LOCKED``), heartbeat their in-flight job so slow documents are not
declared stale, and recover jobs abandoned by crashed workers after the
configured timeout. SIGTERM/SIGINT triggers a graceful shutdown after the
currently claimed job completes.
"""

from __future__ import annotations

import argparse
import logging
import signal
from concurrent.futures import ThreadPoolExecutor

from app.bulk_queue.workers import BulkQueueWorker
from app.core.config import get_settings
from app.core.logging import configure_logging

logger = logging.getLogger(__name__)


def main() -> int:
    """Run the configured worker count until a shutdown signal arrives."""
    parser = argparse.ArgumentParser(
        description="Run dedicated bulk queue worker processes against PostgreSQL.",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=None,
        help="Number of worker threads in this process (default: bulk_queue_workers setting).",
    )
    args = parser.parse_args()

    settings = get_settings()
    configure_logging(level=settings.log_level)
    worker_count = args.workers or settings.bulk_queue_workers
    workers = [BulkQueueWorker(settings=settings) for _ in range(worker_count)]

    def _shutdown(_signum: int, _frame: object) -> None:
        logger.info(
            "Shutdown signal received; stopping %s bulk queue worker(s) gracefully",
            len(workers),
        )
        for worker in workers:
            worker.stop()

    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)

    logger.info("Starting %s bulk queue worker(s)", len(workers))
    with ThreadPoolExecutor(max_workers=len(workers)) as executor:
        futures = [executor.submit(worker.loop_forever) for worker in workers]
        for future in futures:
            future.result()
    logger.info("All bulk queue workers stopped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
