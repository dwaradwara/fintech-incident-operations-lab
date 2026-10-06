# INC003 - Financial Reconciliation Mismatch Caused by Poison Ledger Event

## Incident Type

Controlled production-support simulation.

## Severity

Simulated SEV-1 / Critical

## Affected Component

Payment-to-ledger processing pipeline.

## Executive Summary

A malformed ledger event became stuck at the head of the ledger processing queue.

The Payment API remained available and continued authorizing transactions, but subsequent valid ledger events could not be processed because the worker repeatedly retried the malformed event.

This caused authorized payment records to exist without corresponding ledger entries.

Business-level reconciliation monitoring detected the mismatch while infrastructure health remained normal.

The malformed event was isolated through centralized logs and moved to a dead-letter queue.

The valid events then processed successfully and financial reconciliation returned to zero missing entries.

The ledger worker was subsequently hardened with bounded retries and automatic DLQ quarantine to prevent future poison events from causing head-of-line blocking.

## Business Impact

Five authorized payments temporarily lacked corresponding ledger records.

Affected state:

- Payment status: AUTHORIZED
- Ledger status: MISSING
- Queue depth: 6
- Missing ledger entries: 5

The issue represented a financial data-integrity problem rather than an application availability outage.

## Detection

Three Prometheus alerts fired:

- ReconciliationMismatchDetected
- LedgerQueueBacklog
- LedgerProcessingFailures

Metrics during degradation included:

- ledger queue depth: 6
- reconciliation missing entries: 5
- repeated processing failures
- DLQ depth: 0

## Investigation

Centralized Elasticsearch/Kibana logs showed repeated failures processing the same event:

payment_id: poison-event-001
amount: NOT_A_NUMBER
error: Invalid ledger amount

SQL confirmed five AUTHORIZED payments were missing ledger entries.

The worker process itself remained running.

## Root Cause

The ledger consumer processed events strictly from the queue head.

A malformed event containing a non-numeric amount repeatedly failed validation.

Because the original worker had no bounded retry policy or automatic DLQ handling, the malformed event remained at the queue head and blocked all valid events behind it.

## Immediate Mitigation

The poison event was atomically moved from:

ledger_jobs

to:

ledger_dlq

using Redis LMOVE.

No valid payment or ledger records were deleted or modified.

Once the poison event was quarantined, the five valid events processed normally.

## Recovery Validation

All six test payments from checkout-order-50000 through checkout-order-50005 reconciled successfully.

Recovered state:

- ledger queue depth: 0
- DLQ depth: 1
- missing ledger entries: 0
- reconciliation alerts: inactive

## Permanent Corrective Action

The ledger worker was updated with:

- maximum retry count: 3
- per-event retry tracking
- automatic DLQ quarantine
- structured quarantine logging
- DLQ metrics
- continued processing of valid events after quarantine

A second malformed event was then injected to validate the permanent fix.

Results:

- processing failures: 3
- quarantined events: 1
- queue depth: 0
- DLQ depth: 2
- reconciliation mismatch: 0

A legitimate transaction behind the malformed event remained fully reconciled.

## Permanent-Fix Validation

checkout-order-50006:

- Payment status: AUTHORIZED
- Payment amount: 325.25 AED
- Ledger amount: 325.25 AED
- Reconciliation status: RECONCILED

Kibana showed:

event: ledger_event_quarantined
reason: Invalid ledger amount
attempts: 3
dlq_depth: 2

## What Went Well

- Business reconciliation monitoring detected a non-availability financial failure.
- SQL provided exact transaction-level blast radius.
- Kibana identified the poison event.
- Valid transactions were preserved.
- Atomic DLQ quarantine restored processing.
- Permanent bounded-retry logic prevented recurrence.
- Financial reconciliation returned to zero mismatch.

## What Could Be Improved

- DLQ events should automatically create operational tickets.
- DLQ replay should use a dedicated controlled tool.
- Event schema validation should occur before queue insertion.
- Reconciliation checks should include amount and currency mismatches, not only missing records.
- A dashboard should expose queue depth, DLQ depth, failures and mismatch count together.

## Corrective Actions

| Action | Priority | Status |
|---|---|---|
| Reconciliation mismatch monitoring | P1 | Completed |
| Ledger queue backlog monitoring | P1 | Completed |
| Processing-failure monitoring | P1 | Completed |
| Centralized structured ledger logs | P1 | Completed |
| Manual poison-event quarantine | P1 | Completed |
| Bounded retry policy | P1 | Completed |
| Automatic DLQ quarantine | P1 | Completed |
| DLQ metrics | P1 | Completed |
| Pre-ingestion schema validation | P2 | Planned |
| Automated DLQ replay tooling | P2 | Planned |
| Automatic Jira incident enrichment | P2 | Planned |

## Final Status

Resolved.

Financial reconciliation returned to zero mismatches.

The permanent fix was validated successfully with an additional malformed event.
