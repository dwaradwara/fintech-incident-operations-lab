import random
import time
import uuid

from fastapi import FastAPI
from pydantic import BaseModel, Field
from fastapi.responses import JSONResponse

app = FastAPI(title="Payment Provider Simulator")

settings = {
    "failure_rate": 0.0,
    "latency_ms": 150
}


class AuthorizationRequest(BaseModel):
    payment_id: str
    amount: float
    currency: str


class ProviderConfig(BaseModel):
    failure_rate: float = Field(ge=0.0, le=1.0)
    latency_ms: int = Field(ge=0, le=10000)


@app.get("/health")
def health():
    return {
        "status": "ok",
        **settings
    }


@app.post("/admin/config")
def configure(config: ProviderConfig):
    settings["failure_rate"] = config.failure_rate
    settings["latency_ms"] = config.latency_ms

    return {
        "status": "updated",
        **settings
    }


@app.post("/authorize")
def authorize(request: AuthorizationRequest):
    time.sleep(settings["latency_ms"] / 1000)

    if random.random() < settings["failure_rate"]:
        return JSONResponse(
            status_code=503,
            content={
                "error": "PROVIDER_TEMPORARY_ERROR",
                "message": "Payment provider temporarily unavailable",
                "payment_id": request.payment_id
            }
        )

    return {
        "approved": True,
        "provider_reference": str(uuid.uuid4())
    }
