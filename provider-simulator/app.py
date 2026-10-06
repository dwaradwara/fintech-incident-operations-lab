import random
import threading
import time
import uuid
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse, Response
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    Counter,
    Gauge,
    generate_latest,
)
from pydantic import BaseModel, Field


app = FastAPI(title="Payment Provider Simulator")


settings = {
    "failure_rate": 0.0,
    "latency_ms": 150,
    "post_authorization_delay_ms": 0,
    "enforce_idempotency": True,
}


authorization_lock = threading.Lock()
authorizations = []


PROVIDER_AUTHORIZATIONS = Counter(
    "fintech_provider_authorizations_total",
    "Total successful provider authorizations",
)

PROVIDER_DUPLICATE_AUTHORIZATIONS = Gauge(
    "fintech_provider_duplicate_authorizations",
    "Number of active duplicate provider authorizations",
)

PROVIDER_IDEMPOTENT_REPLAYS = Counter(
    "fintech_provider_idempotent_replays_total",
    "Authorization requests safely replayed using provider-side idempotency",
)


class AuthorizationRequest(BaseModel):
    payment_id: str
    amount: float
    currency: str
    idempotency_key: str | None = None


class ProviderConfig(BaseModel):
    failure_rate: float = Field(ge=0.0, le=1.0)
    latency_ms: int = Field(ge=0, le=10000)
    post_authorization_delay_ms: int = Field(
        default=0,
        ge=0,
        le=15000,
    )
    enforce_idempotency: bool = True


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def active_duplicate_count():
    counts = {}

    with authorization_lock:
        for item in authorizations:
            if item["status"] != "AUTHORIZED":
                continue

            payment_id = item["payment_id"]

            counts[payment_id] = (
                counts.get(payment_id, 0) + 1
            )

    return sum(
        count - 1
        for count in counts.values()
        if count > 1
    )


def refresh_duplicate_metric():
    PROVIDER_DUPLICATE_AUTHORIZATIONS.set(
        active_duplicate_count()
    )


@app.get("/health")
def health():
    return {
        "status": "ok",
        **settings,
        "active_duplicate_authorizations":
            active_duplicate_count(),
    }


@app.get("/metrics")
def metrics():
    refresh_duplicate_metric()

    return Response(
        content=generate_latest(),
        media_type=CONTENT_TYPE_LATEST,
    )


@app.post("/admin/config")
def configure(config: ProviderConfig):
    settings["failure_rate"] = config.failure_rate
    settings["latency_ms"] = config.latency_ms
    settings["post_authorization_delay_ms"] = (
        config.post_authorization_delay_ms
    )
    settings["enforce_idempotency"] = (
        config.enforce_idempotency
    )

    return {
        "status": "updated",
        **settings,
    }


@app.get("/admin/authorizations")
def list_authorizations(
    payment_id: str | None = None,
):
    with authorization_lock:
        items = list(authorizations)

    if payment_id:
        items = [
            item
            for item in items
            if item["payment_id"] == payment_id
        ]

    return {
        "count": len(items),
        "authorizations": items,
    }



@app.get("/authorizations/{payment_id}")
def authorization_state(payment_id: str):
    with authorization_lock:
        items = [
            dict(item)
            for item in authorizations
            if item["payment_id"] == payment_id
        ]

    active = [
        item
        for item in items
        if item["status"] == "AUTHORIZED"
    ]

    return {
        "payment_id": payment_id,
        "total_count": len(items),
        "active_count": len(active),
        "authorizations": items,
    }


@app.get("/admin/duplicates")
def list_duplicates():
    grouped = {}

    with authorization_lock:
        for item in authorizations:
            if item["status"] != "AUTHORIZED":
                continue

            grouped.setdefault(
                item["payment_id"],
                [],
            ).append(item)

    duplicates = [
        {
            "payment_id": payment_id,
            "authorization_count": len(items),
            "provider_references": [
                item["provider_reference"]
                for item in items
            ],
            "amounts": [
                item["amount"]
                for item in items
            ],
            "currency": items[0]["currency"],
        }
        for payment_id, items in grouped.items()
        if len(items) > 1
    ]

    return {
        "duplicate_payment_count":
            len(duplicates),
        "duplicate_authorizations":
            active_duplicate_count(),
        "payments":
            duplicates,
    }


@app.post(
    "/admin/reverse/{provider_reference}"
)
def reverse_authorization(
    provider_reference: str,
):
    with authorization_lock:
        for item in authorizations:
            if (
                item["provider_reference"]
                == provider_reference
            ):
                if item["status"] == "REVERSED":
                    return {
                        "status": "already_reversed",
                        "provider_reference":
                            provider_reference,
                    }

                item["status"] = "REVERSED"
                item["reversed_at"] = utc_now()

                refresh_needed = True
                break
        else:
            refresh_needed = False

    if not refresh_needed:
        raise HTTPException(
            status_code=404,
            detail="Provider authorization not found",
        )

    refresh_duplicate_metric()

    return {
        "status": "reversed",
        "provider_reference":
            provider_reference,
    }


@app.post("/admin/reset-authorizations")
def reset_authorizations():
    with authorization_lock:
        authorizations.clear()

    refresh_duplicate_metric()

    return {
        "status": "reset",
        "authorization_count": 0,
    }


@app.post("/authorize")
def authorize(
    request: AuthorizationRequest,
):
    # Simulates ordinary provider/network latency
    # before the payment decision.
    time.sleep(
        settings["latency_ms"] / 1000
    )

    # Provider-side idempotency protection.
    #
    # In normal operation, replaying the same idempotency
    # key returns the original authorization instead of
    # creating another external financial side effect.
    #
    # INC005 can still be reproduced by deliberately
    # setting enforce_idempotency=false.
    if (
        settings["enforce_idempotency"]
        and request.idempotency_key
    ):
        with authorization_lock:
            existing = next(
                (
                    dict(item)
                    for item in authorizations
                    if (
                        item["idempotency_key"]
                        == request.idempotency_key
                        and item["status"]
                        == "AUTHORIZED"
                    )
                ),
                None,
            )

        if existing:
            PROVIDER_IDEMPOTENT_REPLAYS.inc()

            return {
                "approved": True,
                "provider_reference":
                    existing["provider_reference"],
                "idempotent_replay": True,
            }

    if (
        random.random()
        < settings["failure_rate"]
    ):
        return JSONResponse(
            status_code=503,
            content={
                "error":
                    "PROVIDER_TEMPORARY_ERROR",
                "message":
                    "Payment provider temporarily unavailable",
                "payment_id":
                    request.payment_id,
            },
        )

    # Critical INC005 behavior:
    # the provider commits the authorization BEFORE
    # the response is delayed back to the caller.
    provider_reference = str(uuid.uuid4())

    record = {
        "provider_reference":
            provider_reference,
        "payment_id":
            request.payment_id,
        "idempotency_key":
            request.idempotency_key,
        "amount":
            request.amount,
        "currency":
            request.currency,
        "status":
            "AUTHORIZED",
        "authorized_at":
            utc_now(),
        "reversed_at":
            None,
    }

    with authorization_lock:
        authorizations.append(record)

    PROVIDER_AUTHORIZATIONS.inc()
    refresh_duplicate_metric()

    # This delay creates the ambiguous-state scenario:
    # authorization succeeded, but the client may timeout
    # before receiving the response.
    if (
        settings[
            "post_authorization_delay_ms"
        ]
        > 0
    ):
        time.sleep(
            settings[
                "post_authorization_delay_ms"
            ]
            / 1000
        )

    return {
        "approved": True,
        "provider_reference":
            provider_reference,
        "idempotent_replay": False,
    }
