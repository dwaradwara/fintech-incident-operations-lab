from app.models import IncidentInput, JiraDraft, TriageResult


def _text(incident: IncidentInput) -> str:
    return " ".join(
        [
            incident.title,
            incident.summary,
            *incident.logs,
            *incident.sql_evidence,
        ]
    ).lower()


def triage_with_rules(incident: IncidentInput, redactions: int) -> TriageResult:
    text = _text(incident)
    metrics = incident.metrics

    category = "unknown"
    severity = "medium"
    confidence = 0.60
    component = "unknown"
    failure_domain = "unknown"

    evidence = []
    missing = []
    investigation = []

    if (
        "missing ledger" in text
        or "missing_ledger_entry" in text
        or metrics.get(
            "fintech_reconciliation_missing_ledger_entries",
            0,
        ) > 0
    ):
        category = "financial_reconciliation"
        severity = "critical"
        confidence = 0.98
        component = "ledger-worker"
        failure_domain = "payment-to-ledger pipeline"

        evidence.extend([
            "Authorized payment exists without corresponding ledger entry.",
            "Business-level reconciliation indicates financial state mismatch.",
        ])

        investigation.extend([
            "Check ledger queue depth and DLQ depth.",
            "Identify affected payment IDs with SQL.",
            "Review ledger-worker structured logs.",
            "Check for poison events or repeated processing failures.",
            "Validate payment amount and currency against ledger records.",
        ])

    elif (
        "webhook" in text
        and (
            "failed" in text
            or "http 500" in text
            or "delivery" in text
        )
    ):
        category = "webhook_delivery"
        severity = "high"
        confidence = 0.94
        component = "webhook-worker"
        failure_domain = "merchant webhook delivery"

        evidence.extend([
            "Webhook delivery failures are present.",
            "Payment completion can succeed while downstream notification fails.",
        ])

        investigation.extend([
            "Inspect webhook retry attempts.",
            "Check merchant endpoint HTTP status.",
            "Confirm queue depth and permanent-failure count.",
            "Validate idempotency before replay.",
        ])

    elif (
        "latency" in text
        or metrics.get(
            "fintech_provider_latency_ms",
            0,
        ) >= 2000
    ):
        category = "provider_latency"
        severity = "high"
        confidence = 0.92
        component = "provider-simulator"
        failure_domain = "upstream payment provider"

        evidence.extend([
            "Payment path is responding slowly.",
            "Latency degradation may occur without HTTP failure.",
        ])

        investigation.extend([
            "Compare provider latency with application latency.",
            "Check provider errors and timeouts.",
            "Validate authorization success rate.",
            "Correlate slow payment IDs in centralized logs.",
        ])

    elif (
        "authorization" in text
        and (
            "failure" in text
            or "provider_error" in text
            or "timeout" in text
        )
    ):
        category = "payment_authorization"
        severity = "critical"
        confidence = 0.95
        component = "payment-api"
        failure_domain = "payment authorization / upstream provider"

        evidence.extend([
            "Payment authorization failures are elevated.",
            "Checkout/payment completion is directly affected.",
        ])

        investigation.extend([
            "Measure authorization failure rate.",
            "Check provider HTTP errors and timeouts.",
            "Correlate transaction IDs with provider logs.",
            "Confirm database and Redis health.",
        ])

    else:
        missing.extend([
            "Clear failure signature.",
            "Relevant logs.",
            "Business-impact metric.",
        ])

        investigation.extend([
            "Confirm affected service.",
            "Collect recent logs and metrics.",
            "Determine customer/business impact.",
        ])

    if incident.logs:
        evidence.append(
            f"{len(incident.logs)} log evidence item(s) supplied."
        )
    else:
        missing.append("Recent application logs.")

    if incident.sql_evidence:
        evidence.append(
            f"{len(incident.sql_evidence)} SQL evidence item(s) supplied."
        )
    else:
        missing.append("Transaction-level SQL evidence.")

    stakeholder = (
        f"{severity.upper()} incident under investigation. "
        f"Current evidence points to {failure_domain}. "
        "Impact and scope are being validated. "
        "No autonomous remediation has been performed."
    )

    jira_description = "\n".join([
        f"Incident: {incident.incident_id}",
        f"Category: {category}",
        f"Severity: {severity}",
        f"Component: {component}",
        "",
        "Evidence:",
        *[f"- {item}" for item in evidence],
        "",
        "Recommended investigation:",
        *[f"- {item}" for item in investigation],
        "",
        "Human approval required before remediation.",
    ])

    return TriageResult(
        incident_id=incident.incident_id,
        category=category,
        severity=severity,
        confidence=confidence,
        affected_component=component,
        likely_failure_domain=failure_domain,
        evidence_summary=evidence,
        missing_evidence=missing,
        recommended_investigation=investigation,
        stakeholder_update=stakeholder,
        jira_draft=JiraDraft(
            summary=f"[{severity.upper()}] {incident.title}",
            description=jira_description,
            priority=severity.upper(),
            component=component,
        ),
        engine="rules-fallback-v1",
        human_approval_required=True,
        autonomous_remediation_allowed=False,
        redactions_applied=redactions,
    )
