# Fintech Incident Operations Lab

Hands-on support operations and incident-management lab for a simulated 24/7 fintech payment platform.

The project demonstrates alert-driven incident response, payment and ledger investigation, SQL analysis, centralized logging, business-level monitoring, stakeholder communication, postmortems, Jira-style escalation records, safe recovery procedures, and AI-assisted incident triage.

> This is a controlled engineering lab using synthetic transactions and simulated failures. It does not represent a production financial system.

## What This Project Demonstrates

- L2 / production support incident ownership
- Payment authorization troubleshooting
- Merchant webhook delivery and retry investigation
- Financial reconciliation and ledger analysis
- Upstream provider latency investigation
- SQL-based transaction validation
- Prometheus and Grafana monitoring
- Datadog Agent, OpenMetrics, dashboards and metric monitors
- Elasticsearch, Filebeat and Kibana-style centralized log investigation
- Redis-backed asynchronous processing
- Structured stakeholder updates
- Jira-style incident and engineering escalation records
- Post-incident reviews and preventive actions
- Python/Bash operational tooling
- AI/LLM-assisted incident triage with deterministic safety policies
- Human approval gates for remediation

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
                      │ Merchant       │              │ Ledger Entries  │
                      │ Webhook API    │              │ Reconciliation │
                      └─────────────────┘              └─────────────────┘

Observability:
Prometheus ─ Grafana ─ Datadog ─ Filebeat ─ Elasticsearch/Kibana

Support automation:
Incident evidence ─ Redaction ─ LLM triage ─ Deterministic policy
                                  │
                                  ▼
                         Human approval required
