# Architecture and Operations

## Purpose

This controlled lab models the operational support workflow of a fintech payment platform.

The focus is not feature development. The focus is incident detection, technical investigation, business-impact validation, stakeholder communication, controlled recovery, and post-incident improvement.

## Transaction Flow

A normal payment follows this path:

1. A client sends a payment request to the Payment API.
2. The Payment API calls the simulated upstream payment provider.
3. The provider returns an authorization result.
4. The Payment API persists payment and event state in PostgreSQL.
5. Authorized payments generate asynchronous webhook and ledger work.
6. Redis queues those jobs.
7. The webhook worker delivers merchant notifications.
8. The ledger worker creates the corresponding financial ledger entry.
9. Reconciliation verifies that authorized payments and ledger records agree.

This creates separate operational domains:

- payment authorization
- merchant notification
- financial ledger processing
- reconciliation
- upstream-provider performance

A failure in one domain does not necessarily mean the others have failed.

## Support Principle: Technical Health vs Business Health

A service returning HTTP 200 or passing a health endpoint does not prove that the payment workflow is healthy.

The lab therefore validates both:

### Technical state

- process/container availability
- HTTP health
- queue state
- metrics
- logs
- dependency health

### Business state

- payment authorization status
- webhook delivery status
- ledger presence
- payment-to-ledger reconciliation
- provider response latency

INC002 demonstrates this distinction because a payment can remain AUTHORIZED while merchant notification fails.

INC003 demonstrates it again because an application can remain technically available while financial records are incomplete.

## Observability

### Prometheus

Prometheus collects application and business metrics including:

- authorization outcomes
- provider latency
- webhook failures
- webhook queue depth
- ledger processing failures
- ledger queue depth
- DLQ depth
- reconciliation mismatches
- ambiguous payment outcomes
- duplicate provider authorizations

Alert rules identify operational degradation and business-state failures.

### Grafana

Grafana provides operational visualization over Prometheus telemetry.

### Datadog

A real Datadog Agent collects host/container information and custom OpenMetrics.

The Financial Reconciliation Mismatch monitor was validated through a controlled:

OK → ALERT → recovery → OK

cycle.

### Elasticsearch and Filebeat

Filebeat collects Docker container logs and sends them to Elasticsearch.

Structured application fields use the `fintech.*` namespace to support incident correlation.

Examples include:

- `payment_authorized`
- `webhook_delivery_failed`
- `webhook_delivered`
- `ledger_processing_failed`
- `ledger_event_quarantined`

## Database Investigation

PostgreSQL is used as an authoritative source when validating transaction and reconciliation state.

Typical investigation queries correlate:

- payment ID
- idempotency key
- payment status
- payment amount
- currency
- webhook state
- ledger amount
- ledger currency
- reconciliation outcome

SQL evidence is captured with the incident rather than relying only on application logs.

## Queue Operations

Redis supports asynchronous webhook and ledger jobs.

Operational investigation includes:

- queue depth
- retry behavior
- failed events
- poison events
- DLQ state
- replay safety

Replays use specific affected transaction identifiers rather than indiscriminate queue reprocessing.

## Incident Lifecycle

The controlled incident workflow is:

1. Detect an alert or support signal.
2. Confirm the symptom.
3. Assess customer/business impact.
4. Determine severity.
5. Collect logs, metrics and SQL evidence.
6. Correlate transaction identifiers across systems.
7. Isolate the probable failure domain.
8. Communicate current facts to stakeholders.
9. Apply a controlled recovery action.
10. Validate technical recovery.
11. Validate business-state recovery.
12. Confirm alerts return to healthy state.
13. Document root cause or confirmed contributing condition.
14. Record preventive actions and follow-up work.

## Incident Scope

### INC001 — Payment Authorization Failure

Focus:

- upstream failure
- authorization success/failure rates
- provider errors
- transaction impact
- recovery validation

### INC002 — Merchant Webhook Delivery Failure

Focus:

- HTTP 500 delivery failures
- retry lifecycle
- permanent failure
- safe replay
- merchant idempotency

### INC003 — Financial Reconciliation Mismatch

Focus:

- authorized payments missing ledger entries
- queue starvation
- poison event handling
- DLQ quarantine
- reconciliation validation

### INC004 — Provider Latency Degradation

Focus:

- successful but slow transactions
- latency-based alerting
- business impact without availability loss
- recovery validation

### INC005 — Ambiguous Payment Outcome / Duplicate Authorization

Focus:

- provider authorization succeeds while the caller times out
- internal `UNKNOWN` payment state
- authoritative provider-state lookup
- controlled unsafe-retry reproduction
- duplicate provider authorization detection
- `REQUIRES_REVIEW` containment
- evidence-based human reversal decision
- preservation of the original authorization
- payment, ledger, and webhook reconciliation
- Datadog and Prometheus recovery validation

## Recovery Safety

The lab avoids broad destructive recovery actions.

Operational recovery principles include:

- identify exact affected records
- preserve evidence before remediation
- prefer replay over manual data fabrication
- validate idempotency where applicable
- treat payment-provider timeouts as ambiguous until authoritative state is known
- block blind retries of financial operations after ambiguous outcomes
- require evidence before choosing an authorization for reversal
- verify both technical and business state afterward
- require human approval for AI-generated recommendations

## Evidence

Each incident contains supporting artifacts such as:

- alert state
- metrics
- SQL output
- centralized logs
- stakeholder update
- postmortem
- Jira-style incident record

All evidence represents synthetic transactions generated within this controlled lab.
