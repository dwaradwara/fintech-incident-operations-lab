import json
import logging
import os
import time
from datetime import datetime, timezone

import psycopg
import redis
import requests
from prometheus_client import Counter, Gauge, start_http_server


DATABASE_URL = os.environ["DATABASE_URL"]
REDIS_URL = os.environ["REDIS_URL"]
MERCHANT_WEBHOOK_URL = \
    os.environ["MERCHANT_WEBHOOK_URL"]

MAX_ATTEMPTS = 5

redis_client = redis.from_url(
    REDIS_URL,
    decode_responses=True
)

logging.basicConfig(
    level=logging.INFO,
    format="%(message)s"
)

logger = logging.getLogger("webhook-worker")

WEBHOOK_DELIVERED = Counter(
    "fintech_webhook_delivered_total",
    "Successfully delivered merchant webhooks"
)

WEBHOOK_DELIVERY_FAILURES = Counter(
    "fintech_webhook_delivery_failures_total",
    "Failed merchant webhook delivery attempts"
)

WEBHOOK_RETRIES = Counter(
    "fintech_webhook_retries_total",
    "Webhook jobs scheduled for retry"
)

WEBHOOK_PERMANENT_FAILURES = Counter(
    "fintech_webhook_permanent_failures_total",
    "Webhook deliveries that exhausted retry attempts"
)

WEBHOOK_QUEUE_DEPTH = Gauge(
    "fintech_worker_webhook_queue_depth",
    "Current webhook queue depth"
)

start_http_server(9101)



def log_event(event, **fields):
    logger.info(
        json.dumps({
            "timestamp":
                datetime.now(timezone.utc).isoformat(),
            "service": "webhook-worker",
            "event": event,
            **fields
        })
    )


while True:

    WEBHOOK_QUEUE_DEPTH.set(
        redis_client.llen("webhook_jobs")
    )

    result = redis_client.blpop(
        "webhook_jobs",
        timeout=5
    )

    if result is None:
        continue

    _, raw_job = result
    job = json.loads(raw_job)

    payment_id = job["payment_id"]
    event_type = job["event_type"]

    with psycopg.connect(DATABASE_URL) as conn:

        row = conn.execute(
            """
            SELECT
                id,
                attempt_count
            FROM webhook_deliveries
            WHERE payment_id = %s
              AND event_type = %s
            ORDER BY id DESC
            LIMIT 1
            """,
            (
                payment_id,
                event_type
            )
        ).fetchone()

    if row is None:
        log_event(
            "delivery_record_missing",
            payment_id=payment_id,
            event_type=event_type
        )
        continue

    delivery_id = row[0]
    attempt = row[1] + 1

    response = None

    try:
        response = requests.post(
            MERCHANT_WEBHOOK_URL,
            json={
                "payment_id": payment_id,
                "event_type": event_type
            },
            headers={
                "Idempotency-Key":
                    f"{payment_id}:{event_type}"
            },
            timeout=3
        )

        if 200 <= response.status_code < 300:

            with psycopg.connect(
                DATABASE_URL
            ) as conn:

                conn.execute(
                    """
                    UPDATE webhook_deliveries
                    SET
                        delivery_status =
                            'DELIVERED',
                        attempt_count = %s,
                        last_http_status = %s,
                        last_error = NULL,
                        updated_at = now()
                    WHERE id = %s
                    """,
                    (
                        attempt,
                        response.status_code,
                        delivery_id
                    )
                )

                conn.commit()

            WEBHOOK_DELIVERED.inc()

            log_event(
                "webhook_delivered",
                payment_id=payment_id,
                event_type=event_type,
                attempt=attempt,
                http_status=
                    response.status_code
            )

            continue

        error = \
            f"HTTP {response.status_code}"

    except Exception as exc:
        error = str(exc)

    WEBHOOK_DELIVERY_FAILURES.inc()

    final_failure = \
        attempt >= MAX_ATTEMPTS

    with psycopg.connect(DATABASE_URL) as conn:

        conn.execute(
            """
            UPDATE webhook_deliveries
            SET
                delivery_status = %s,
                attempt_count = %s,
                last_http_status = %s,
                last_error = %s,
                updated_at = now()
            WHERE id = %s
            """,
            (
                "FAILED"
                if final_failure
                else "RETRYING",
                attempt,
                response.status_code
                if response is not None
                else None,
                error,
                delivery_id
            )
        )

        conn.commit()

    if final_failure:
        WEBHOOK_PERMANENT_FAILURES.inc()

    log_event(
        "webhook_delivery_failed",
        payment_id=payment_id,
        event_type=event_type,
        attempt=attempt,
        error=error,
        final_failure=final_failure
    )

    if not final_failure:

        WEBHOOK_RETRIES.inc()

        time.sleep(
            min(2 ** attempt, 10)
        )

        redis_client.rpush(
            "webhook_jobs",
            raw_job
        )
