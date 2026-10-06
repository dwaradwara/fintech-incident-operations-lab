# INC002 - Merchant Webhook Delivery Failure

## Incident Type

Controlled production-support simulation.

## Severity

Simulated SEV-2 / High

## Affected Component

Merchant webhook delivery pipeline.

## Executive Summary

Three successfully authorized payments could not be delivered to the merchant callback endpoint because the downstream merchant service returned HTTP 500 responses.

Payment authorization itself remained operational.

The webhook worker retried each affected delivery five times. All three eventually exhausted automatic retry attempts and entered FAILED status.

Centralized structured logging exposed the retry sequence, payment IDs, attempt numbers, HTTP failures and final-failure state.

After the merchant endpoint recovered, only webhook records in FAILED state were deliberately replayed. All three succeeded on attempt six.

A durable consumer-side idempotency control was subsequently added and validated to prevent duplicate business processing under at-least-once delivery semantics.

## Customer / Business Impact

Affected payments: 3

Payment state:
AUTHORIZED

Webhook state during degradation:
FAILED

Attempts per affected webhook:
5 automatic failed attempts

Downstream response:
HTTP 500

Potential business impact:

- merchant systems may not receive payment notifications
- order fulfilment may be delayed
- payment and order state may temporarily diverge
- support contacts may increase

## Detection

Prometheus monitored:

- webhook delivery failures
- webhook retries
- permanent webhook failures

Relevant alerts:

- MerchantWebhookDeliveryFailures
- MerchantWebhookPermanentFailures

## Investigation

The investigation established that:

1. Payment authorization remained successful.
2. PostgreSQL remained available.
3. Redis remained available.
4. The webhook worker remained operational.
5. Merchant callback requests returned HTTP 500.
6. Structured centralized logs showed attempts 1 through 5.
7. Attempt 5 was marked as the final failure.
8. SQL confirmed three AUTHORIZED payments with FAILED webhook delivery state.

## Root Cause

The controlled merchant callback service was placed into failure mode and returned HTTP 500 for webhook requests.

The failure was isolated to the downstream notification path and did not affect payment authorization.

## Retry Behaviour

Each affected webhook followed the configured retry policy.

Attempts:

1 -> HTTP 500
2 -> HTTP 500
3 -> HTTP 500
4 -> HTTP 500
5 -> HTTP 500 / final failure

After recovery, an operator replayed only FAILED deliveries.

Attempt 6 -> HTTP 200

## Controlled Recovery

The merchant endpoint was restored to healthy state.

Only three database records with delivery_status = FAILED were selected for replay.

No successfully delivered historical webhook records were replayed.

Recovery result:

- 3 replayed
- 3 delivered
- HTTP status 200
- attempt_count = 6
- last_error cleared

## Additional Defect Found

During investigation, the webhook worker failed to persist HTTP 500 into last_http_status.

The code used:

response.status_code if response else None

The requests library evaluates Response objects with HTTP 4xx/5xx as false-like.

The implementation was corrected to:

response.status_code if response is not None else None

This ensured HTTP failure status codes were preserved correctly.

## Idempotency Improvement

The webhook sender already supplied a stable Idempotency-Key:

payment_id:event_type

A persistent merchant-side idempotency store was added using SQLite.

The idempotency key is enforced as a unique primary key.

A duplicate delivery using the same key returned:

duplicate = true

while the number of processed business events remained:

1

This establishes at-least-once webhook delivery with consumer-side duplicate protection.

## What Went Well

- Payment authorization remained isolated from webhook failure.
- Retry behaviour operated as designed.
- Centralized structured logs exposed the complete retry history.
- SQL provided exact affected-payment scope.
- Operator replay targeted only FAILED deliveries.
- Recovery was independently verified through logs and SQL.
- Merchant-side idempotency prevented duplicate business processing.

## What Could Be Improved

- Failed webhooks should eventually move to a dedicated DLQ.
- Automated replay tooling should replace direct Redis commands.
- Merchant-specific failure rate dashboards should be added.
- Webhook retry exhaustion should automatically enrich the incident ticket.
- Synthetic merchant callback checks would improve early detection.

## Corrective Actions

| Action | Priority | Status |
|---|---|---|
| Alert on webhook delivery failures | P1 | Completed |
| Alert on exhausted retry attempts | P1 | Completed |
| Preserve HTTP failure status in database | P1 | Completed |
| Controlled replay of FAILED records | P1 | Completed |
| Durable merchant idempotency | P1 | Completed |
| Centralized structured webhook logs | P1 | Completed |
| Add DLQ workflow | P2 | Planned |
| Automate safe replay tooling | P2 | Planned |
| Add incident-ticket enrichment | P2 | Planned |

## Final Status

Resolved.

All three affected webhook deliveries were successfully recovered.

Payments remained AUTHORIZED throughout the incident.

Duplicate-processing protection was subsequently validated successfully.
