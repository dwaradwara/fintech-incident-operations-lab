from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_health():
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["autonomous_remediation"] is False


def test_reconciliation_incident():
    payload = {
        "incident_id": "INC003",
        "source": "datadog",
        "title": "Financial reconciliation mismatch",
        "summary": (
            "Five AUTHORIZED payments are missing ledger entries."
        ),
        "logs": [
            (
                'ledger_processing_failed '
                'error="Invalid ledger amount" '
                'payment_id="poison-event-001"'
            )
        ],
        "metrics": {
            "fintech_reconciliation_missing_ledger_entries": 5,
            "fintech_ledger_queue_depth": 6,
            "fintech_ledger_dlq_depth": 0
        },
        "sql_evidence": [
            (
                "checkout-order-50001 "
                "AUTHORIZED "
                "MISSING_LEDGER_ENTRY"
            )
        ],
        "references": [
            "evidence/INC003/04-reconciliation-degraded.txt"
        ]
    }

    response = client.post(
        "/triage",
        json=payload,
    )

    assert response.status_code == 200

    result = response.json()

    assert result["category"] == "financial_reconciliation"
    assert result["severity"] == "critical"
    assert result["affected_component"] == "ledger-worker"
    assert result["confidence"] >= 0.90

    assert result["human_approval_required"] is True
    assert result["autonomous_remediation_allowed"] is False


def test_financial_reconciliation_policy_is_critical():
    from app.models import JiraDraft, TriageResult, IncidentInput
    from app.policy import apply_operational_policy

    incident = IncidentInput(
        incident_id="POLICY-001",
        source="datadog",
        title="Financial reconciliation mismatch",
        summary="Authorized payment missing ledger entry.",
        metrics={
            "fintech_reconciliation_missing_ledger_entries": 1
        },
    )

    model_result = TriageResult(
        incident_id="POLICY-001",
        category="financial_reconciliation",
        severity="high",
        confidence=0.88,
        affected_component="ledger-worker",
        likely_failure_domain="ledger processing",
        evidence_summary=[],
        missing_evidence=[],
        recommended_investigation=[],
        stakeholder_update="Mismatch under investigation.",
        jira_draft=JiraDraft(
            summary="Investigate mismatch",
            description="Evidence under investigation.",
            priority="High",
            component="ledger-worker",
        ),
        engine="test-llm",
    )

    result = apply_operational_policy(
        incident,
        model_result,
    )

    assert result.severity == "critical"
    assert result.jira_draft.priority == "CRITICAL"
    assert result.human_approval_required is True
    assert result.autonomous_remediation_allowed is False


def test_api_applies_policy_to_llm_result(monkeypatch):
    from app.models import JiraDraft, TriageResult

    def fake_llm(incident, redactions):
        return TriageResult(
            incident_id=incident.incident_id,
            category="financial_reconciliation",
            severity="medium",
            confidence=0.95,
            affected_component="ledger-worker",
            likely_failure_domain="unconfirmed",
            evidence_summary=[],
            missing_evidence=[],
            recommended_investigation=[],
            stakeholder_update="Under investigation.",
            jira_draft=JiraDraft(
                summary="Investigate mismatch",
                description="Mismatch detected.",
                priority="Medium",
                component="ledger-worker",
            ),
            engine="test-llm",
            redactions_applied=redactions,
        )

    monkeypatch.setenv(
        "TRIAGE_ENGINE",
        "llm",
    )

    monkeypatch.setattr(
        "app.main.triage_with_llm",
        fake_llm,
    )

    response = client.post(
        "/triage",
        json={
            "incident_id": "POLICY-API-001",
            "source": "datadog",
            "title": "Financial reconciliation mismatch",
            "summary": "Authorized payment missing ledger entry.",
            "metrics": {
                "fintech_reconciliation_missing_ledger_entries": 1
            },
        },
    )

    assert response.status_code == 200

    result = response.json()

    assert result["severity"] == "critical"
    assert result["jira_draft"]["priority"] == "CRITICAL"
    assert result["human_approval_required"] is True
    assert result["autonomous_remediation_allowed"] is False
