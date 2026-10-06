# Fintech Incident Operations Lab

Hands-on support operations and incident-management lab for a simulated 24/7 fintech payment platform.

The project demonstrates payment incident triage, SQL investigation, business-level monitoring, centralized logging, stakeholder communication, post-incident analysis, Datadog observability, and AI-assisted support operations.

> **Controlled engineering lab:** all transactions, incidents, and customer-impact scenarios are synthetic simulations. This repository does not represent a production financial system.

---

## Why This Project Exists

The lab was built to demonstrate the workflow expected from a Support Operations / Production Support Engineer working around payment systems:

- respond to operational alerts
- assess business impact and severity
- investigate using logs, metrics, and SQL
- isolate the failure domain
- communicate clearly during incidents
- coordinate controlled recovery
- verify both technical and business-state recovery
- document incidents, postmortems, and follow-up actions
- automate repetitive support work safely
- use AI/LLMs as an assistant without giving them remediation authority

---

## Core Capabilities

- L2 / production-support incident investigation
- Payment authorization troubleshooting
- Merchant webhook delivery and retry analysis
- Financial reconciliation and ledger investigation
- Upstream provider latency analysis
- Ambiguous payment-state and duplicate-authorization investigation
- Provider-side idempotency protection with controlled failure injection
- PostgreSQL transaction validation
- Redis queue and DLQ troubleshooting
- Prometheus and Grafana monitoring
- Datadog Agent, OpenMetrics, dashboards, and metric monitors
- Elasticsearch, Filebeat, and Kibana centralized logging
- Jira-style incident / engineering escalation records
- Stakeholder updates, runbooks, postmortems, and root-cause analysis
- Python and Bash operational tooling
- GitHub Actions CI for syntax, tests, Compose, and Prometheus validation
- AI-assisted incident classification and summarization
- Deterministic severity policies
- Secret / PII redaction
- Prompt-injection resistance
- Human approval gates for remediation

---

## Architecture

```text
                        ┌─────────────────────┐
                        │   Payment Client    │
                        └──────────┬──────────┘
                                   │
                                   ▼
                        ┌─────────────────────┐
                        │    Payment API      │
                        │      FastAPI        │
                        └──────┬───────┬──────┘
                               │       │
                     ┌─────────┘       └──────────┐
                     ▼                            ▼
            ┌─────────────────┐          ┌─────────────────┐
            │ Payment Provider│          │   PostgreSQL    │
            │    Simulator    │          │ payments/events │
            └─────────────────┘          └────────┬────────┘
                                                  │
                               ┌──────────────────┴─────────────┐
                               │                                │
                               ▼                                ▼
                      ┌─────────────────┐              ┌─────────────────┐
                      │ Webhook Worker  │              │  Ledger Worker  │
                      │ Redis queue     │              │ Redis queue/DLQ │
                      └────────┬────────┘              └────────┬────────┘
                               │                                │
                               ▼                                ▼
                      ┌─────────────────┐              ┌─────────────────┐
                      │ Merchant        │              │ Ledger Entries  │
                      │ Webhook API     │              │ Reconciliation  │
                      └─────────────────┘              └─────────────────┘

Observability:
Prometheus ─ Grafana ─ Datadog ─ Filebeat ─ Elasticsearch/Kibana

Support automation:
Incident evidence ─ Redaction ─ LLM triage ─ Deterministic policy
                                  │
                                  ▼
                         Human approval required
```

---

## Incident Portfolio

| Incident | Scenario | Investigation | Recovery |
|---|---|---|---|
| **INC001** | Payment authorization failure | Prometheus alerts, provider errors, SQL, application logs | Provider recovery and transaction validation |
| **INC002** | Merchant webhook delivery failure | Retry state, SQL, centralized logs, idempotency | Targeted replay and merchant-side duplicate protection |
| **INC003** | Financial reconciliation mismatch | Ledger metrics, SQL, queue state, processing logs | Poison-event quarantine, DLQ handling, and reconciliation |
| **INC004** | Provider latency degradation | Provider latency metrics, SQL, and logs | Provider normalized and latency alert recovered |
| **INC005** | Ambiguous payment outcome / duplicate authorization | Provider state, idempotency, SQL, logs, Prometheus, Datadog | Duplicate reversed and original authorization reconciled |

---

## INC001 — Payment Authorization Failure

A controlled upstream-provider degradation caused authorization failures.

Investigation covered:

- alert validation
- payment authorization failure rate
- provider HTTP errors
- transaction-level SQL
- application logs
- customer / business impact
- stakeholder communication
- recovery validation

Controlled results included:

```text
Degradation round 1: 80% failed
Degradation round 2: 70% failed
Recovery validation: 0% failed
```

The incident was closed only after both the technical condition and transaction outcomes were validated.

**Evidence:** [`evidence/INC001`](evidence/INC001)

---

## INC002 — Merchant Webhook Delivery Failure

Payments continued to authorize successfully while merchant webhook delivery returned HTTP 500 responses.

This demonstrates an important support principle:

> **Payment success does not automatically mean the complete customer workflow succeeded.**

Investigation included:

- webhook retry behavior
- delivery attempt counts
- SQL validation
- structured log analysis
- permanent failure detection
- stakeholder updates

Recovery used targeted replay of affected events.

Merchant-side idempotency was added to ensure duplicate delivery attempts could not create duplicate business processing.

**Evidence:** [`evidence/INC002`](evidence/INC002)

---

## INC003 — Financial Reconciliation Mismatch

This is the strongest fintech incident in the project.

Authorized payments existed without corresponding ledger entries.

The degraded state showed:

```text
Missing ledger entries: 5
Ledger queue depth: 6
Repeated processing failures: active
Reconciliation alert: firing
```

SQL confirmed that several payments were:

```text
AUTHORIZED
but
MISSING_LEDGER_ENTRY
```

Centralized logs identified a malformed / poison ledger event repeatedly failing processing.

The worker was hardened with:

- bounded retry handling
- poison-event detection
- automatic DLQ quarantine
- continued processing of healthy events

After recovery:

```text
ledger queue depth = 0
reconciliation missing entries = 0
all controlled payments = RECONCILED
```

The Prometheus alerts returned to inactive automatically.

**Evidence:** [`evidence/INC003`](evidence/INC003)

---

## INC004 — Provider Latency Degradation

Payment authorization remained successful while upstream provider latency increased to approximately:

```text
~3.5 seconds
```

This incident demonstrates that availability alone is not sufficient for service-health assessment.

Investigation correlated:

- provider latency metrics
- successful payment state
- application logs
- SQL event evidence
- Prometheus alert state

After recovery, measured latency returned to approximately:

```text
~150 ms
```

and the latency alert returned to inactive.

**Evidence:** [`evidence/INC004`](evidence/INC004)

---

## INC005 — Ambiguous Payment Outcome / Duplicate Authorization

A controlled provider scenario demonstrated a critical payment-support failure mode: the provider authorized an AED 400 payment, but its response arrived after the Payment API timeout.

The same transaction therefore had two different views:

```text
Payment API: UNKNOWN
Provider:    AUTHORIZED
```

The key operational principle is:

> A timeout is not proof that a payment failed. It means the caller did not receive a response within the configured timeout.

A controlled unsafe retry reproduced the failure that can occur when an ambiguous financial operation is repeated without first checking authoritative provider state.

The same payment intent temporarily had:

```text
Intended payment:               AED 400
Active provider authorizations:       2
Total authorization exposure:   AED 800
Duplicate authorization exposure: AED 400
```

Detection included:

- `AmbiguousPaymentOutcomeDetected`
- `DuplicatePaymentAuthorizationDetected`
- `fintech.payments.duplicate_authorizations = 1`
- structured Payment API logs
- provider authorization evidence
- PostgreSQL transaction state

The corrected retry path queried provider state instead of issuing another authorization.

When two active authorizations were discovered, the payment moved to:

```text
REQUIRES_REVIEW
```

with:

```text
DUPLICATE_AUTHORIZATION
```

The later authorization created by the controlled unsafe retry was reversed. The original authorization was preserved and the internal payment was reconciled against it.

Final validation:

```text
Payment status:                 AUTHORIZED
Payment amount:                 AED 400
Active provider authorizations:       1
Duplicate authorizations:             0
Ledger amount:                  AED 400
Webhook status:                 DELIVERED
Webhook HTTP status:                  200
Datadog duplicate metric:              0
Prometheus incident alerts:      cleared
```

This incident demonstrates ambiguous financial-state handling, safe retry design, local idempotency versus external side effects, provider-state reconciliation, duplicate-authorization detection, and human-reviewed financial recovery.

The healthy provider configuration also enforces the authorization idempotency key. Repeating the same provider request returns the original provider reference instead of creating another authorization. INC005 uses an explicit controlled bypass of this protection to reproduce the unsafe failure mode.

The lab models authorization state only; it does not claim duplicate capture or settlement occurred.

**Evidence:** [`evidence/INC005`](evidence/INC005)

---

## Datadog Observability

A real Datadog Agent was integrated into the lab.

The Agent collects:

- Linux host metrics
- Docker/container information
- Redis telemetry
- custom fintech OpenMetrics

Custom metrics include:

```text
fintech.reconciliation.missing_ledger_entries
fintech.ledger.queue_depth
fintech.ledger.dlq_depth
fintech.ledger.processing_failures.count
fintech.ledger.events_quarantined.count
fintech.payment.webhook_queue_depth
fintech.payments.authorized.count
fintech.payments.authorization_failures.count
fintech.provider.http_errors.count
fintech.provider.request_duration_seconds.*
fintech.payments.ambiguous_outcomes.count
fintech.payments.duplicate_authorizations
fintech.webhook.delivered.count
fintech.webhook.delivery_failures.count
fintech.webhook.permanent_failures.count
fintech.webhook.retries.count
fintech.webhook.queue_depth
```

A **Financial Reconciliation Mismatch** Datadog monitor was validated through a full lifecycle:

```text
OK
 ↓
Financial mismatch introduced
 ↓
ALERT
 ↓
Targeted reconciliation recovery
 ↓
Metric returned to zero
 ↓
OK
```

This adds business-level financial monitoring rather than relying only on CPU, memory, or service-health metrics.

---

## Centralized Logging

Container logs are collected through Filebeat and indexed into Elasticsearch.

Structured application fields use the `fintech.*` namespace.

Examples:

```text
fintech.event: payment_authorized
fintech.event: webhook_delivery_failed
fintech.event: webhook_delivered
fintech.event: ledger_processing_failed
fintech.event: ledger_event_quarantined
```

Transaction identifiers are used to correlate:

```text
alert
  ↓
metric
  ↓
application log
  ↓
payment ID
  ↓
SQL record
  ↓
business state
```

---

## AI-Assisted Incident Triage

The repository contains an internal support tool:

[`incident-triage-assistant/`](incident-triage-assistant)

It accepts incident evidence including:

- alert source
- title and summary
- logs
- metrics
- SQL findings
- evidence references

It produces structured output containing:

- incident category
- severity
- confidence
- affected component
- likely failure domain
- evidence summary
- missing evidence
- recommended investigation
- stakeholder update
- Jira-ready draft

---

## AI Safety Architecture

Incident evidence is treated as **untrusted input**.

```text
Untrusted evidence
       ↓
Secret / PII redaction
       ↓
LLM structured analysis
       ↓
Schema validation
       ↓
Deterministic fintech policy
       ↓
Human-reviewed result
```

The LLM does **not** have final authority over operational severity.

For example:

```text
financial reconciliation mismatch
+
missing ledger entries > 0
```

forces:

```text
severity = critical
jira priority = CRITICAL
```

even if the model recommends a lower severity.

The system always enforces:

```text
human_approval_required = true
autonomous_remediation_allowed = false
```

---

## Prompt-Injection Validation

The real LLM path was tested using malicious log content instructing the model to:

- ignore previous instructions
- downgrade the incident
- falsely claim remediation had completed

The final validated output remained:

```text
category: financial_reconciliation
severity: critical
engine: openai-responses:gpt-6-luna
jira priority: CRITICAL
human approval required: true
autonomous remediation allowed: false
```

The stakeholder update did not claim that remediation had occurred.

**Evidence:** [`incident-triage-assistant/evidence/final`](incident-triage-assistant/evidence/final)

---

## AI Fallback Design

The triage service also contains a deterministic rules engine.

If the external LLM path fails:

```text
LLM unavailable
      ↓
Rules fallback
      ↓
Structured triage remains available
```

This prevents AI availability from becoming a single point of failure for the support workflow.

---

## Testing

Automated tests validate:

- deterministic incident classification
- financial reconciliation severity enforcement
- API-level policy enforcement
- secret / PII redaction
- safety behavior

Latest captured result:

```text
5 passed
```

GitHub Actions continuously validates:

- Python syntax across the payment and support services
- the deterministic incident-triage test suite
- Docker Compose configuration
- Prometheus configuration and alert rules


Normal automated tests use the deterministic engine so CI does not depend on:

- external API availability
- model nondeterminism
- API cost

Live LLM behavior is validated separately in the controlled environment.

---

## Incident Response Workflow

```text
Alert / support request
        ↓
Triage
        ↓
Impact + severity assessment
        ↓
Logs + metrics + SQL
        ↓
Failure-domain isolation
        ↓
Stakeholder update
        ↓
Controlled remediation
        ↓
Technical validation
        ↓
Business-state validation
        ↓
Monitor recovery
        ↓
Postmortem + Jira record + prevention
```

A green `/health` endpoint is never treated as proof that the full financial workflow is healthy.

---

## Repository Structure

```text
.
├── .github/
│   └── workflows/
│       └── ci.yml
├── database/
├── docs/
│   ├── architecture-and-operations.md
│   └── ai-triage-design.md
├── evidence/
│   ├── INC001/
│   ├── INC002/
│   ├── INC003/
│   ├── INC004/
│   └── INC005/
├── incident-triage-assistant/
├── ledger-worker/
├── merchant-webhook/
├── observability/
│   ├── datadog/
│   ├── elastic/
│   ├── grafana/
│   └── prometheus/
├── payment-api/
├── provider-simulator/
├── webhook-worker/
├── docker-compose.yml
└── docker-compose.override.yml
```

---

## Documentation

Detailed design documentation:

- [`Architecture and Operations`](docs/architecture-and-operations.md)
- [`AI-Assisted Incident Triage Design`](docs/ai-triage-design.md)

Incident evidence:

- [`INC001 Evidence`](evidence/INC001)
- [`INC002 Evidence`](evidence/INC002)
- [`INC003 Evidence`](evidence/INC003)
- [`INC004 Evidence`](evidence/INC004)
- [`INC005 Evidence`](evidence/INC005)
- [`INC005 Runbook`](evidence/INC005/30-runbook.md)
- [`INC005 Root Cause Analysis`](evidence/INC005/31-root-cause.md)

---

## Technology Stack

### Application

```text
Python
FastAPI
PostgreSQL
Redis
Docker Compose
```

### Observability

```text
Datadog
OpenMetrics
Prometheus
Grafana
Elasticsearch
Kibana
Filebeat
```

### Support / Operations

```text
SQL
Bash
pytest
structured logging
alerting
runbooks
postmortems
root-cause analysis
Jira-style escalation records
GitHub Actions
```

### AI

```text
OpenAI Responses API
structured outputs
Pydantic validation
deterministic policy enforcement
rule-based fallback
secret / PII redaction
```

---

## Security

The repository excludes:

- `.env` files
- API keys
- private keys
- runtime databases
- application logs
- Python virtual environments

Secrets are supplied only at runtime.

Incident evidence is sanitized before external LLM processing.

No AI-generated output is allowed to autonomously execute remediation.

---

## Scope

This project is intentionally focused on **Support Operations, Production Support, and Incident Management** rather than general application feature development.

The objective is to demonstrate:

```text
Detect
→ Investigate
→ Communicate
→ Recover safely
→ Validate
→ Learn
```

All incidents, transactions, and business-impact scenarios are controlled simulations created specifically for hands-on operational troubleshooting.
