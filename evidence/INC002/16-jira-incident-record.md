# Merchant Webhook Delivery Failures

## Type
Incident

## Priority
High / Simulated SEV-2

## Component
Webhook Delivery

## Summary

Merchant webhook endpoint returned HTTP 500 for successfully authorized payments.

## Impact

3 payment transactions were successfully AUTHORIZED but their downstream merchant notifications failed.

Each webhook exhausted 5 automatic delivery attempts.

## Evidence

- Payment state: AUTHORIZED
- Webhook state: FAILED
- HTTP response: 500
- Attempts: 5
- Structured logs contain payment ID and retry sequence
- SQL confirms exact affected delivery records

## Root Cause

Downstream merchant callback endpoint was unavailable for business requests and returned HTTP 500.

## Recovery

Merchant endpoint recovered.

Only FAILED webhook records were replayed.

All three succeeded on attempt 6 with HTTP 200.

## Corrective Actions

- Durable consumer-side idempotency implemented
- HTTP failure-code persistence corrected
- Webhook failure monitoring implemented
- Permanent failure monitoring implemented
- DLQ and automated replay tooling proposed
