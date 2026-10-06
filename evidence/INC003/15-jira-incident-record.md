# Financial Reconciliation Mismatch

## Type

Incident

## Priority

Critical / Simulated SEV-1

## Component

Ledger Processing

## Summary

Authorized payments were missing corresponding ledger records because a malformed event blocked the ledger queue.

## Impact

5 authorized payments temporarily had no ledger entry.

Queue depth reached 6.

Payment authorization remained operational.

## Detection

Prometheus alerts:

- ReconciliationMismatchDetected
- LedgerQueueBacklog
- LedgerProcessingFailures

## Technical Evidence

Kibana repeatedly showed:

- event: ledger_processing_failed
- payment_id: poison-event-001
- error: Invalid ledger amount
- queue depth: 6

SQL showed five AUTHORIZED payments with MISSING_LEDGER_ENTRY.

## Root Cause

The ledger worker had unlimited retries on the queue-head event.

A malformed event therefore caused head-of-line blocking.

## Mitigation

The poison event was atomically moved to the DLQ.

Valid events then processed normally.

## Recovery

- queue depth: 0
- reconciliation missing entries: 0
- all affected payments reconciled
- alerts returned inactive

## Permanent Fix

Ledger worker updated with:

- maximum 3 attempts
- retry tracking
- automatic DLQ quarantine
- structured quarantine logs
- DLQ monitoring

Validation with a second malformed event confirmed valid payments behind it continued processing normally.
