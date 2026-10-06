from app.models import IncidentInput, TriageResult


def apply_operational_policy(
    incident: IncidentInput,
    result: TriageResult,
) -> TriageResult:

    missing_ledger = incident.metrics.get(
        "fintech_reconciliation_missing_ledger_entries",
        0,
    )

    if (
        result.category == "financial_reconciliation"
        and missing_ledger > 0
    ):
        result.severity = "critical"
        result.jira_draft.priority = "CRITICAL"

    if (
        result.category == "payment_authorization"
        and incident.metrics.get(
            "fintech_payment_authorization_failure_rate",
            0,
        ) >= 0.20
    ):
        result.severity = "critical"
        result.jira_draft.priority = "CRITICAL"

    result.human_approval_required = True
    result.autonomous_remediation_allowed = False

    return result
