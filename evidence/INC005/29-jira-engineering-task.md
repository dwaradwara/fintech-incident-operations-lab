# Jira Engineering Task

## Title

Prevent duplicate payment authorization after ambiguous provider timeout

## Type

Bug / Reliability Improvement

## Priority

Critical

## Component

Payment API / Provider Integration

## Problem

A payment-provider request can succeed at the provider while the Payment API times out before receiving the response.

If the system treats that timeout as a failed authorization and blindly retries the external financial operation, multiple active provider authorizations can be created for one payment intent.

## Observed Controlled Scenario

Payment:

`checkout-order-70001`

Amount:

`AED 400`

Observed sequence:

1. provider successfully authorized payment
2. response exceeded API timeout
3. internal payment became UNKNOWN
4. unsafe retry repeated authorization
5. provider contained two active AED 400 authorizations
6. duplicate authorization monitoring fired

## Required Behavior

Provider timeouts must not be treated as confirmed authorization failure.

The payment must enter an ambiguous state.

Before another authorization operation can occur, the system must query authoritative provider state.

## Acceptance Criteria

1. A provider request timeout records payment status as `UNKNOWN`.
2. UNKNOWN is distinct from provider decline and provider HTTP failure.
3. Retrying the same idempotency key does not automatically issue another provider authorization.
4. Provider state is queried before any further financial action.
5. Exactly one active provider authorization reconciles the internal payment to `AUTHORIZED`.
6. More than one active provider authorization moves the payment to `REQUIRES_REVIEW`.
7. No automatic reversal is performed when multiple authorizations are discovered.
8. No active provider authorization leaves the payment unresolved and blocks blind retry.
9. Ambiguous outcomes produce operational metrics and alerts.
10. Duplicate provider authorizations produce a critical metric and alert.
11. Recovery validation includes provider state, payment state, ledger state, webhook delivery, and monitor recovery.
12. Human approval is required before selecting an authorization for reversal.

## Monitoring

Prometheus:

- `AmbiguousPaymentOutcomeDetected`
- `DuplicatePaymentAuthorizationDetected`

Datadog:

- `fintech.payments.ambiguous_outcomes.count`
- `fintech.payments.duplicate_authorizations`

## Validation Result

Controlled validation demonstrated:

- ambiguous timeout detected
- unsafe retry created duplicate authorization
- safe retry detected duplicate and blocked further authorization
- payment moved to REQUIRES_REVIEW
- later duplicate authorization reversed
- original authorization preserved
- internal payment reconciled
- ledger reconciled
- webhook delivered
- duplicate metric returned to zero
- incident alerts cleared
