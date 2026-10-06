import os
import sqlite3
from datetime import datetime, timezone

from fastapi import FastAPI, Header, Request
from fastapi.responses import JSONResponse


app = FastAPI(title="Merchant Webhook Receiver")

settings = {
    "fail_mode": False
}

DB_PATH = os.getenv(
    "MERCHANT_DB_PATH",
    "/data/merchant.db"
)


def init_db():
    os.makedirs(
        os.path.dirname(DB_PATH),
        exist_ok=True
    )

    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS processed_webhooks (
                idempotency_key TEXT PRIMARY KEY,
                payment_id TEXT NOT NULL,
                event_type TEXT NOT NULL,
                processed_at TEXT NOT NULL
            )
            """
        )
        conn.commit()


init_db()


@app.get("/health")
def health():
    return {
        "status": "ok",
        **settings
    }


@app.get("/admin/stats")
def stats():
    with sqlite3.connect(DB_PATH) as conn:
        processed = conn.execute(
            """
            SELECT COUNT(*)
            FROM processed_webhooks
            """
        ).fetchone()[0]

    return {
        "processed_webhooks": processed,
        "fail_mode": settings["fail_mode"]
    }


@app.post("/admin/fail-mode")
def configure_fail_mode(enabled: bool):
    settings["fail_mode"] = enabled

    return {
        "status": "updated",
        **settings
    }


@app.post("/webhooks/payment")
async def payment_webhook(
    request: Request,
    idempotency_key: str | None = Header(
        default=None,
        alias="Idempotency-Key"
    )
):
    payload = await request.json()

    if settings["fail_mode"]:
        return JSONResponse(
            status_code=500,
            content={
                "error": "MERCHANT_ENDPOINT_FAILURE"
            }
        )

    if not idempotency_key:
        return JSONResponse(
            status_code=400,
            content={
                "error": "IDEMPOTENCY_KEY_REQUIRED"
            }
        )

    payment_id = payload.get("payment_id")
    event_type = payload.get("event_type")

    try:
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute(
                """
                INSERT INTO processed_webhooks (
                    idempotency_key,
                    payment_id,
                    event_type,
                    processed_at
                )
                VALUES (?, ?, ?, ?)
                """,
                (
                    idempotency_key,
                    payment_id,
                    event_type,
                    datetime.now(
                        timezone.utc
                    ).isoformat()
                )
            )

            conn.commit()

        return {
            "received": True,
            "duplicate": False,
            "payment_id": payment_id,
            "event_type": event_type
        }

    except sqlite3.IntegrityError:
        return {
            "received": True,
            "duplicate": True,
            "payment_id": payment_id,
            "event_type": event_type
        }
