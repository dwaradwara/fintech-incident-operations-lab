import hashlib
import json
import logging
import os
import time
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation

import psycopg
import redis
from prometheus_client import (
    Counter,
    Gauge,
    start_http_server,
)


DATABASE_URL = os.environ["DATABASE_URL"]
REDIS_URL = os.environ["REDIS_URL"]

MAX_ATTEMPTS = 3

redis_client = redis.from_url(
    REDIS_URL,
    decode_responses=True
)

logging.basicConfig(
    level=logging.INFO,
    format="%(message)s"
)

logger = logging.getLogger("ledger-worker")


LEDGER_POSTED = Counter(
    "fintech_ledger_entries_posted_total",
    "Successfully posted ledger entries"
)

LEDGER_FAILURES = Counter(
    "fintech_ledger_processing_failures_total",
    "Ledger event processing failures"
)

LEDGER_DLQ_EVENTS = Counter(
    "fintech_ledger_events_quarantined_total",
    "Ledger events moved to the dead-letter queue"
)

LEDGER_QUEUE_DEPTH = Gauge(
    "fintech_ledger_queue_depth",
    "Current ledger queue depth"
)

LEDGER_DLQ_DEPTH = Gauge(
    "fintech_ledger_dlq_depth",
    "Current ledger dead-letter queue depth"
)

RECONCILIATION_MISMATCH = Gauge(
    "fintech_reconciliation_missing_ledger_entries",
    "Authorized payments requiring ledger entries but missing them"
)


def log_event(event, **fields):
    logger.info(
        json.dumps({
            "timestamp":
                datetime.now(timezone.utc).isoformat(),
            "service": "ledger-worker",
            "event": event,
            **fields
        })
    )


def retry_key(raw_job):
    digest = hashlib.sha256(
        raw_job.encode("utf-8")
    ).hexdigest()

    return f"ledger_retry:{digest}"


def update_operational_metrics():

    LEDGER_QUEUE_DEPTH.set(
        redis_client.llen("ledger_jobs")
    )

    LEDGER_DLQ_DEPTH.set(
        redis_client.llen("ledger_dlq")
    )

    with psycopg.connect(DATABASE_URL) as conn:

        missing = conn.execute(
            """
            SELECT COUNT(*)
            FROM payments p
            LEFT JOIN ledger_entries l
              ON l.payment_id = p.payment_id
            WHERE p.ledger_required = TRUE
              AND p.status = 'AUTHORIZED'
              AND l.payment_id IS NULL
            """
        ).fetchone()[0]

    RECONCILIATION_MISMATCH.set(
        missing
    )


start_http_server(9102)

log_event(
    "ledger_worker_started",
    max_attempts=MAX_ATTEMPTS
)


while True:

    update_operational_metrics()

    raw_job = redis_client.lindex(
        "ledger_jobs",
        0
    )

    if raw_job is None:
        time.sleep(1)
        continue

    key = retry_key(raw_job)

    try:

        job = json.loads(raw_job)

        payment_id = job["payment_id"]
        currency = job["currency"]

        try:
            amount = Decimal(
                str(job["amount"])
            )

        except (
            InvalidOperation,
            ValueError,
            TypeError
        ):
            raise ValueError(
                "Invalid ledger amount"
            )

        if amount <= 0:
            raise ValueError(
                "Ledger amount must be positive"
            )

        with psycopg.connect(
            DATABASE_URL
        ) as conn:

            conn.execute(
                """
                INSERT INTO ledger_entries (
                    payment_id,
                    amount,
                    currency
                )
                VALUES (%s, %s, %s)
                ON CONFLICT (payment_id)
                DO NOTHING
                """,
                (
                    payment_id,
                    amount,
                    currency
                )
            )

            conn.commit()

        redis_client.lpop(
            "ledger_jobs"
        )

        redis_client.delete(key)

        LEDGER_POSTED.inc()

        log_event(
            "ledger_entry_posted",
            payment_id=payment_id,
            amount=str(amount),
            currency=currency
        )

    except Exception as exc:

        LEDGER_FAILURES.inc()

        attempt = redis_client.incr(key)

        redis_client.expire(
            key,
            86400
        )

        log_event(
            "ledger_processing_failed",
            raw_job=raw_job,
            error=str(exc),
            attempt=attempt,
            max_attempts=MAX_ATTEMPTS,
            queue_depth=
                redis_client.llen(
                    "ledger_jobs"
                )
        )

        if attempt >= MAX_ATTEMPTS:

            quarantined = redis_client.lmove(
                "ledger_jobs",
                "ledger_dlq",
                "LEFT",
                "RIGHT"
            )

            redis_client.delete(key)

            LEDGER_DLQ_EVENTS.inc()

            log_event(
                "ledger_event_quarantined",
                raw_job=quarantined,
                reason=str(exc),
                attempts=attempt,
                dlq_depth=
                    redis_client.llen(
                        "ledger_dlq"
                    )
            )

            continue

        time.sleep(2)
