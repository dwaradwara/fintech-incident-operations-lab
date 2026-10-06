import os

from fastapi import FastAPI

from app.llm import triage_with_llm
from app.models import IncidentInput, TriageResult
from app.policy import apply_operational_policy
from app.redaction import redact_text
from app.rules import triage_with_rules


app = FastAPI(
    title="Fintech Incident Triage Assistant",
    version="0.3.0",
)


@app.get("/health")
def health():
    return {
        "status": "ok",
        "service": "incident-triage-assistant",
        "configured_engine": os.environ.get(
            "TRIAGE_ENGINE",
            "rules",
        ),
        "autonomous_remediation": False,
    }


def sanitize_incident(
    incident: IncidentInput,
) -> tuple[IncidentInput, int]:

    redactions = 0

    incident.title, count = redact_text(incident.title)
    redactions += count

    incident.summary, count = redact_text(incident.summary)
    redactions += count

    sanitized_logs = []

    for item in incident.logs:
        clean, count = redact_text(item)
        sanitized_logs.append(clean)
        redactions += count

    incident.logs = sanitized_logs

    sanitized_sql = []

    for item in incident.sql_evidence:
        clean, count = redact_text(item)
        sanitized_sql.append(clean)
        redactions += count

    incident.sql_evidence = sanitized_sql

    return incident, redactions


@app.post("/triage", response_model=TriageResult)
def triage(incident: IncidentInput):

    incident, redactions = sanitize_incident(
        incident
    )

    requested_engine = os.environ.get(
        "TRIAGE_ENGINE",
        "rules",
    ).lower()

    if requested_engine == "llm":
        try:
            result = triage_with_llm(
                incident,
                redactions,
            )
        except Exception:
            result = triage_with_rules(
                incident,
                redactions,
            )
    else:
        result = triage_with_rules(
            incident,
            redactions,
        )

    return apply_operational_policy(
        incident,
        result,
    )
