# INC001 - Payment Authorization Failure Spike

## Incident Type

Controlled production-support simulation.

## Severity

Simulated SEV-1 / Critical

## Affected Service

Payment authorization / checkout transaction path.

## Executive Summary

A controlled upstream payment-provider degradation caused a significant increase in payment authorization failures while the Payment API, PostgreSQL, Redis, and provider health endpoint remained available.

Business-level Prometheus metrics detected the issue through elevated payment authorization failure rate and upstream HTTP errors.

The degradation was isolated to the provider authorization path through correlation of application logs, payment metrics, health checks, and SQL transaction data.

After the upstream provider was restored to its healthy configuration, ten recovery-validation transactions completed successfully with a 0% failure rate and both critical monitoring alerts returned to inactive state.

## Customer / Business Impact

Two controlled degradation rounds were executed.

### Degradation Round 1

- Total payment attempts: 20
- Authorized: 4
- Failed: 16
- Failure rate: 80.00%

### Degradation Round 2

- Total payment attempts: 30
- Authorized: 9
- Failed: 21
- Failure rate: 70.00%

### Combined Degradation

- Total payment attempts: 50
- Authorized: 13
- Failed: 37
- Overall controlled degradation failure rate: 74.00%

Customers represented by these simulated requests would have experienced intermittent checkout failures.

## Detection

The incident was detected through business-level metrics rather than infrastructure availability.

Firing alerts:

- HighPaymentAuthorizationFailureRate
- ProviderHttpErrorsDetected

Prometheus remained healthy and continued scraping the Payment API.

The Payment API readiness endpoint remained healthy.

The provider health endpoint also remained healthy.

This demonstrated that component health checks alone were insufficient to identify the customer-impacting failure.

## Technical Symptoms

Observed symptoms included:

- Increased HTTP 502 responses returned by the Payment API
- Upstream provider HTTP 503 responses
- Increased `fintech_payment_authorization_failures_total`
- Increased `fintech_provider_http_errors_total`
- Payment records entering `PROVIDER_ERROR`
- Authorization success and failure occurring concurrently

## Investigation

The investigation followed this sequence:

1. Confirmed critical Prometheus alerts.
2. Measured recent authorization failure rate.
3. Checked Payment API readiness.
4. Checked upstream provider health endpoint.
5. Confirmed PostgreSQL and Redis remained available.
6. Reviewed Payment API structured logs.
7. Identified upstream HTTP 503 provider responses.
8. Queried PostgreSQL for affected transaction IDs and payment states.
9. Confirmed failures were isolated to provider authorization requests.

## Root Cause

The controlled payment-provider simulator was configured with a 70% authorization failure rate.

The provider remained network-reachable and continued returning a healthy `/health` response, but a significant portion of authorization requests returned HTTP 503.

This created partial upstream service degradation rather than a complete dependency outage.

## Contributing Factors

- Provider health checks only confirmed service reachability, not transaction success.
- Payment authorization depended on an external provider.
- The original alert used a one-minute evaluation window that was too short for the manual incident workflow used in the lab.

## Monitoring Improvement

During the incident exercise, the authorization-failure monitor was tuned from a one-minute window to a two-minute evaluation window.

The corrected rule successfully transitioned:

inactive → pending → firing → inactive

This reduced the possibility of missing a sustained degradation during investigation.

## Remediation

The upstream provider configuration was restored to:

- Failure rate: 0%
- Simulated latency: 150 ms

No database, Redis, or Payment API restart was required.

## Recovery Validation

Ten unique payment transactions were submitted after mitigation.

Results:

- Total payments: 10
- Authorized: 10
- Failed: 0
- Failure rate: 0.00%

Both critical alerts subsequently returned to:

- state: inactive
- health: ok

## What Went Well

- Business-level monitoring detected degradation despite healthy infrastructure checks.
- Structured logs exposed upstream HTTP status and payment IDs.
- SQL provided an exact transaction-level blast radius.
- Idempotency controls remained intact.
- No database or Redis failure occurred.
- Alert recovery provided independent confirmation after mitigation.

## What Could Be Improved

- External dependency health checks should include transaction-level or synthetic validation.
- Alert windows require tuning based on expected traffic volume and operational response time.
- Provider-specific dashboards should expose error ratio and latency together.
- Automated incident enrichment could attach affected-payment counts and recent provider errors to the incident ticket.

## Corrective Actions

| Action | Priority | Status |
|---|---|---|
| Maintain business-level authorization failure monitor | P1 | Completed |
| Maintain provider HTTP error monitor | P1 | Completed |
| Tune failure-rate alert evaluation window | P1 | Completed |
| Add centralized searchable logs | P1 | Planned |
| Add synthetic provider transaction check | P2 | Planned |
| Add automated incident evidence collection | P2 | Planned |
| Integrate incident creation/update workflow with Jira | P2 | Planned |
| Add AI-assisted incident summarization | P2 | Planned |

## Evidence

Evidence is stored under:

`evidence/INC001/`

Key evidence includes:

- pre-incident monitoring state
- firing Prometheus alerts
- SQL blast-radius queries
- affected payment records
- structured Payment API logs
- health-versus-business-impact evidence
- recovery monitoring state
- recovery operations summary
- measured incident impact
- transaction timestamps

## Final Status

Resolved.

Recovery validation succeeded with a 0% failure rate across ten post-mitigation payment attempts.

Both critical incident alerts returned to inactive state.
