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

ALLOW_UNSAFE_UNKNOWN_RETRY = (
    os.environ.get(
        "ALLOW_UNSAFE_UNKNOWN_RETRY",
        "false",
    ).lower()
    == "true"
)

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

AMBIGUOUS_PAYMENT_OUTCOMES = Counter(
    "fintech_payment_ambiguous_outcomes_total",
    "Payment requests whose provider outcome is unknown"
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



def reconcile_unknown_payment(existing):
    payment_id = str(
        existing["payment_id"]
    )

    log_event(
        "provider_state_lookup_started",
        payment_id=payment_id,
        idempotency_key=
            existing["idempotency_key"],
        current_status=existing["status"],
    )

    try:
        response = requests.get(
            f"{PROVIDER_URL}/authorizations/{payment_id}",
            timeout=2,
        )

        response.raise_for_status()
        provider_state = response.json()

    except requests.RequestException as exc:
        log_event(
            "provider_state_lookup_failed",
            payment_id=payment_id,
            error=str(exc),
        )

        raise HTTPException(
            status_code=503,
            detail=(
                "Provider state could not be verified. "
                "Authorization retry is blocked."
            ),
        )

    active = [
        item
        for item in provider_state.get(
            "authorizations",
            [],
        )
        if item.get("status") == "AUTHORIZED"
    ]

    active_count = len(active)

    log_event(
        "provider_state_lookup_completed",
        payment_id=payment_id,
        active_authorizations=active_count,
        total_provider_records=
            provider_state.get(
                "total_count",
                0,
            ),
    )

    if active_count == 1:
        provider_reference = (
            active[0]["provider_reference"]
        )

        with psycopg.connect(
            DATABASE_URL
        ) as conn:

            conn.execute(
                """
                UPDATE payments
                SET
                    status = 'AUTHORIZED',
                    provider_reference = %s,
                    failure_code = NULL,
                    failure_message = NULL,
                    updated_at = now()
                WHERE payment_id = %s
                """,
                (
                    provider_reference,
                    existing["payment_id"],
                ),
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
                    existing["payment_id"],
                    "payment.reconciled_from_provider_state",
                    Jsonb({
                        "provider_reference":
                            provider_reference,
                        "previous_status":
                            existing["status"],
                    }),
                ),
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
                (existing["payment_id"],),
            )

            conn.commit()

        enqueue_webhook(
            existing["payment_id"],
            "payment.authorized",
        )

        redis_client.rpush(
            "ledger_jobs",
            json.dumps({
                "payment_id":
                    payment_id,
                "amount":
                    str(existing["amount"]),
                "currency":
                    existing["currency"],
            }),
        )

        log_event(
            "payment_reconciled_authorized",
            payment_id=payment_id,
            provider_reference=
                provider_reference,
        )

        return get_by_idempotency_key(
            existing["idempotency_key"]
        )

    if active_count > 1:
        references = [
            item["provider_reference"]
            for item in active
        ]

        with psycopg.connect(
            DATABASE_URL
        ) as conn:

            conn.execute(
                """
                UPDATE payments
                SET
                    status = 'REQUIRES_REVIEW',
                    failure_code =
                        'DUPLICATE_AUTHORIZATION',
                    failure_message =
                        'Multiple active provider authorizations detected',
                    updated_at = now()
                WHERE payment_id = %s
                """,
                (existing["payment_id"],),
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
                    existing["payment_id"],
                    "payment.duplicate_authorization_detected",
                    Jsonb({
                        "active_authorizations":
                            active_count,
                        "provider_references":
                            references,
                    }),
                ),
            )

            conn.commit()

        log_event(
            "duplicate_authorization_detected",
            payment_id=payment_id,
            active_authorizations=
                active_count,
            provider_references=
                references,
        )

        raise HTTPException(
            status_code=409,
            detail={
                "error":
                    "DUPLICATE_AUTHORIZATION",
                "message":
                    (
                        "Multiple active provider "
                        "authorizations detected. "
                        "Human review required."
                    ),
                "payment_id":
                    payment_id,
                "active_authorizations":
                    active_count,
            },
        )

    log_event(
        "provider_state_unresolved",
        payment_id=payment_id,
    )

    raise HTTPException(
        status_code=409,
        detail={
            "error":
                "PAYMENT_OUTCOME_UNKNOWN",
            "message":
                (
                    "No authoritative provider "
                    "authorization was found. "
                    "Do not retry authorization "
                    "automatically."
                ),
            "payment_id":
                payment_id,
        },
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

    unsafe_retry_existing = False

    if existing:
        if (
            existing["status"]
            in {
                "UNKNOWN",
                "REQUIRES_REVIEW",
            }
            and not ALLOW_UNSAFE_UNKNOWN_RETRY
        ):
            return reconcile_unknown_payment(
                existing
            )

        if (
            existing["status"] == "UNKNOWN"
            and ALLOW_UNSAFE_UNKNOWN_RETRY
        ):
            payment_id = existing[
                "payment_id"
            ]

            unsafe_retry_existing = True

            log_event(
                "unsafe_unknown_retry_injected",
                payment_id=str(payment_id),
                idempotency_key=
                    x_idempotency_key,
            )

        else:
            log_event(
                "idempotent_replay",
                payment_id=str(
                    existing["payment_id"]
                ),
                idempotency_key=
                    x_idempotency_key,
                status=existing["status"]
            )

            return existing

    if not unsafe_retry_existing:
        payment_id = uuid.uuid4()

        with psycopg.connect(
            DATABASE_URL
        ) as conn:

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
                    %s, %s, %s, %s,
                    %s, %s, 'PENDING', TRUE
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
                "currency": request.currency.upper(),
                "idempotency_key": x_idempotency_key
            },
            timeout=5
        )

    except requests.Timeout:
        duration_ms = round(
            (time.monotonic() - started) * 1000,
            2
        )

        PROVIDER_TIMEOUTS.inc()
        AMBIGUOUS_PAYMENT_OUTCOMES.inc()

        PROVIDER_LATENCY.observe(
            duration_ms / 1000
        )

        with psycopg.connect(
            DATABASE_URL
        ) as conn:

            conn.execute(
                """
                UPDATE payments
                SET
                    status = 'UNKNOWN',
                    failure_code =
                        'PROVIDER_TIMEOUT_AMBIGUOUS',
                    failure_message =
                        'Provider response timed out; authorization outcome is unknown',
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
                    "payment.authorization_unknown",
                    Jsonb({
                        "duration_ms":
                            duration_ms,
                        "unsafe_retry_enabled":
                            ALLOW_UNSAFE_UNKNOWN_RETRY,
                    })
                )
            )

            conn.commit()

        log_event(
            "payment_authorization_unknown",
            payment_id=str(payment_id),
            idempotency_key=
                x_idempotency_key,
            duration_ms=duration_ms,
            unsafe_retry_enabled=
                ALLOW_UNSAFE_UNKNOWN_RETRY,
        )

        raise HTTPException(
            status_code=504,
            detail={
                "error":
                    "PAYMENT_OUTCOME_UNKNOWN",
                "message":
                    (
                        "Provider response timed out. "
                        "Authorization outcome is "
                        "unknown and must be verified "
                        "before another authorization "
                        "attempt."
                    ),
                "payment_id":
                    str(payment_id),
            },
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
