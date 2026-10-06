import json
import logging
import os
import time
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from prometheus_client import (
    Counter,
    Histogram,
    Gauge,
    generate_latest,
    CONTENT_TYPE_LATEST,
)
from fastapi.responses import Response

import psycopg
import redis
import requests
from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import Response
from prometheus_client import Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST
from pydantic import BaseModel, Field
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb


DATABASE_URL = os.environ["DATABASE_URL"]
REDIS_URL = os.environ["REDIS_URL"]
PROVIDER_URL = os.environ["PROVIDER_URL"]

app = FastAPI(title="Fintech Payment Operations API")

redis_client = redis.from_url(
    REDIS_URL,
    decode_responses=True
)

logging.basicConfig(
    level=logging.INFO,
    format="%(message)s"
)

logger = logging.getLogger("payment-api")

PAYMENTS_CREATED = Counter(
    "fintech_payments_created_total",
    "Total payment requests accepted"
)

PAYMENTS_AUTHORIZED = Counter(
    "fintech_payment_authorizations_total",
    "Successful payment authorizations"
)

PAYMENT_AUTH_FAILURES = Counter(
    "fintech_payment_authorization_failures_total",
    "Failed payment authorizations"
)

PROVIDER_ERRORS = Counter(
    "fintech_provider_http_errors_total",
    "Upstream provider HTTP errors"
)

PROVIDER_TIMEOUTS = Counter(
    "fintech_provider_timeouts_total",
    "Upstream provider timeouts"
)

PROVIDER_LATENCY = Histogram(
    "fintech_provider_request_duration_seconds",
    "Payment provider request duration",
    buckets=(0.1, 0.25, 0.5, 1, 2, 3, 5, 10)
)

WEBHOOK_QUEUE_DEPTH = Gauge(
    "fintech_webhook_queue_depth",
    "Current Redis webhook queue depth"
)


def log_event(event, **fields):
    logger.info(
        json.dumps({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "service": "payment-api",
            "event": event,
            **fields
        })
    )


class PaymentRequest(BaseModel):
    merchant_id: str
    customer_id: str
    amount: Decimal = Field(gt=0)
    currency: str = Field(min_length=3, max_length=3)


def get_by_idempotency_key(key):
    with psycopg.connect(
        DATABASE_URL,
        row_factory=dict_row
    ) as conn:

        return conn.execute(
            """
            SELECT
                payment_id,
                idempotency_key,
                merchant_id,
                customer_id,
                amount,
                currency,
                status,
                provider_reference,
                failure_code,
                failure_message,
                created_at,
                updated_at
            FROM payments
            WHERE idempotency_key = %s
            """,
            (key,)
        ).fetchone()


def enqueue_webhook(payment_id, event_type):
    redis_client.rpush(
        "webhook_jobs",
        json.dumps({
            "payment_id": str(payment_id),
            "event_type": event_type
        })
    )


@app.get("/health")
def health():
    return {
        "status": "ok",
        "service": "payment-api"
    }


@app.get("/ready")
def ready():
    try:
        with psycopg.connect(DATABASE_URL) as conn:
            conn.execute("SELECT 1")

        redis_client.ping()

        return {
            "status": "ready",
            "database": "ok",
            "redis": "ok"
        }

    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail=str(exc)
        )


@app.get("/metrics")
def metrics():
    WEBHOOK_QUEUE_DEPTH.set(
        redis_client.llen("webhook_jobs")
    )

    return Response(
        content=generate_latest(),
        media_type=CONTENT_TYPE_LATEST
    )


@app.post("/payments")
def create_payment(
    request: PaymentRequest,
    x_idempotency_key: str = Header(...)
):
    existing = get_by_idempotency_key(
        x_idempotency_key
    )

    if existing:
        log_event(
            "idempotent_replay",
            payment_id=str(existing["payment_id"]),
            idempotency_key=x_idempotency_key,
            status=existing["status"]
        )

        return existing

    payment_id = uuid.uuid4()

    with psycopg.connect(DATABASE_URL) as conn:
        result = conn.execute(
            """
            INSERT INTO payments (
                payment_id,
                idempotency_key,
                merchant_id,
                customer_id,
                amount,
                currency,
                status,
                ledger_required
            )
            VALUES (
                %s, %s, %s, %s, %s, %s, 'PENDING', TRUE
            )
            ON CONFLICT (idempotency_key)
            DO NOTHING
            RETURNING payment_id
            """,
            (
                payment_id,
                x_idempotency_key,
                request.merchant_id,
                request.customer_id,
                request.amount,
                request.currency.upper()
            )
        ).fetchone()

        conn.commit()

    if result is None:
        return get_by_idempotency_key(
            x_idempotency_key
        )

    PAYMENTS_CREATED.inc()

    log_event(
        "payment_created",
        payment_id=str(payment_id),
        merchant_id=request.merchant_id,
        amount=str(request.amount),
        currency=request.currency.upper()
    )

    started = time.monotonic()

    try:
        response = requests.post(
            f"{PROVIDER_URL}/authorize",
            json={
                "payment_id": str(payment_id),
                "amount": float(request.amount),
                "currency": request.currency.upper()
            },
            timeout=5
        )

    except requests.Timeout:
        duration_ms = round(
            (time.monotonic() - started) * 1000,
            2
        )

        PAYMENT_AUTH_FAILURES.inc()
        PROVIDER_TIMEOUTS.inc()
        PROVIDER_LATENCY.observe(
            duration_ms / 1000
        )

        with psycopg.connect(DATABASE_URL) as conn:
            conn.execute(
                """
                UPDATE payments
                SET
                    status = 'PROVIDER_TIMEOUT',
                    failure_code = 'PROVIDER_TIMEOUT',
                    failure_message =
                        'Provider request exceeded timeout',
                    updated_at = now()
                WHERE payment_id = %s
                """,
                (payment_id,)
            )

            conn.execute(
                """
                INSERT INTO payment_events (
                    payment_id,
                    event_type,
                    event_payload
                )
                VALUES (%s, %s, %s)
                """,
                (
                    payment_id,
                    "payment.provider_timeout",
                    Jsonb({
                        "duration_ms": duration_ms
                    })
                )
            )

            conn.commit()

        log_event(
            "provider_timeout",
            payment_id=str(payment_id),
            duration_ms=duration_ms
        )

        raise HTTPException(
            status_code=504,
            detail="Payment provider timed out"
        )

    duration_ms = round(
        (time.monotonic() - started) * 1000,
        2
    )

    if response.status_code != 200:

        PAYMENT_AUTH_FAILURES.inc()
        PROVIDER_ERRORS.inc()
        PROVIDER_LATENCY.observe(
            duration_ms / 1000
        )

        with psycopg.connect(DATABASE_URL) as conn:
            conn.execute(
                """
                UPDATE payments
                SET
                    status = 'PROVIDER_ERROR',
                    failure_code = 'PROVIDER_HTTP_ERROR',
                    failure_message = %s,
                    updated_at = now()
                WHERE payment_id = %s
                """,
                (
                    response.text[:500],
                    payment_id
                )
            )

            conn.execute(
                """
                INSERT INTO payment_events (
                    payment_id,
                    event_type,
                    event_payload
                )
                VALUES (%s, %s, %s)
                """,
                (
                    payment_id,
                    "payment.provider_error",
                    Jsonb({
                        "http_status":
                            response.status_code,
                        "duration_ms":
                            duration_ms
                    })
                )
            )

            conn.execute(
                """
                INSERT INTO webhook_deliveries (
                    payment_id,
                    event_type,
                    delivery_status
                )
                VALUES (
                    %s,
                    'payment.provider_error',
                    'PENDING'
                )
                """,
                (payment_id,)
            )

            conn.commit()

        enqueue_webhook(
            payment_id,
            "payment.provider_error"
        )

        log_event(
            "provider_error",
            payment_id=str(payment_id),
            http_status=response.status_code,
            duration_ms=duration_ms
        )

        raise HTTPException(
            status_code=502,
            detail="Upstream payment provider error"
        )

    provider_result = response.json()

    provider_reference = \
        provider_result["provider_reference"]

    PAYMENTS_AUTHORIZED.inc()
    PROVIDER_LATENCY.observe(
        duration_ms / 1000
    )

    with psycopg.connect(DATABASE_URL) as conn:

        conn.execute(
            """
            UPDATE payments
            SET
                status = 'AUTHORIZED',
                provider_reference = %s,
                updated_at = now()
            WHERE payment_id = %s
            """,
            (
                provider_reference,
                payment_id
            )
        )

        conn.execute(
            """
            INSERT INTO payment_events (
                payment_id,
                event_type,
                event_payload
            )
            VALUES (%s, %s, %s)
            """,
            (
                payment_id,
                "payment.authorized",
                Jsonb({
                    "provider_reference":
                        provider_reference,
                    "provider_latency_ms":
                        duration_ms
                })
            )
        )

        conn.execute(
            """
            INSERT INTO webhook_deliveries (
                payment_id,
                event_type,
                delivery_status
            )
            VALUES (
                %s,
                'payment.authorized',
                'PENDING'
            )
            """,
            (payment_id,)
        )

        conn.commit()

    enqueue_webhook(
        payment_id,
        "payment.authorized"
    )

    redis_client.rpush(
        "ledger_jobs",
        json.dumps({
            "payment_id": str(payment_id),
            "amount": str(request.amount),
            "currency": request.currency.upper()
        })
    )

    log_event(
        "ledger_job_enqueued",
        payment_id=str(payment_id),
        amount=str(request.amount),
        currency=request.currency.upper()
    )

    log_event(
        "payment_authorized",
        payment_id=str(payment_id),
        provider_reference=provider_reference,
        provider_latency_ms=duration_ms
    )

    return get_by_idempotency_key(
        x_idempotency_key
    )


@app.get("/payments/{payment_id}")
def get_payment(payment_id: uuid.UUID):

    with psycopg.connect(
        DATABASE_URL,
        row_factory=dict_row
    ) as conn:

        payment = conn.execute(
            """
            SELECT *
            FROM payments
            WHERE payment_id = %s
            """,
            (payment_id,)
        ).fetchone()

    if not payment:
        raise HTTPException(
            status_code=404,
            detail="Payment not found"
        )

    return payment


@app.get("/ops/summary")
def ops_summary():

    with psycopg.connect(
        DATABASE_URL,
        row_factory=dict_row
    ) as conn:

        payments = conn.execute(
            """
            SELECT
                status,
                COUNT(*) AS payment_count
            FROM payments
            GROUP BY status
            ORDER BY status
            """
        ).fetchall()

        webhooks = conn.execute(
            """
            SELECT
                delivery_status,
                COUNT(*) AS delivery_count
            FROM webhook_deliveries
            GROUP BY delivery_status
            ORDER BY delivery_status
            """
        ).fetchall()

    return {
        "payments": payments,
        "webhooks": webhooks,
        "redis_webhook_queue_depth":
            redis_client.llen("webhook_jobs")
    }
