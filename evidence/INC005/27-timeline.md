# INC005 Timeline

All timestamps are UTC.

## 11:17:17

The provider successfully created the first AED 400 authorization for payment:

`d4999f69-8660-481c-b7f7-e89b71c1e405`

Provider reference:

`80937d56-4a8a-4a09-9558-46449d0e47b1`

The provider intentionally delayed its response after committing the authorization.

The Payment API exceeded its five-second request timeout and recorded the payment outcome as UNKNOWN.

This established the ambiguous state:

- internal system: UNKNOWN
- provider: AUTHORIZED

## 11:20:18

Controlled incident mode allowed an unsafe retry of the same idempotency key and payment ID.

The provider created a second AED 400 authorization.

Provider reference:

`94d29ba4-3611-4e68-b5e0-9e72997e9911`

The Payment API again timed out without receiving the successful provider response.

## 11:20:25

Prometheus reported both critical conditions:

- AmbiguousPaymentOutcomeDetected
- DuplicatePaymentAuthorizationDetected

Datadog received:

`fintech.payments.duplicate_authorizations = 1`

Provider state showed:

- total authorization records: 2
- active authorizations: 2
- intended amount: AED 400
- active authorization exposure: AED 800

## Containment

Unsafe retry mode was disabled and provider response latency was restored to normal.

A retry through the corrected path performed provider-state lookup instead of issuing another authorization.

The system detected two active authorizations, returned HTTP 409, and moved the internal payment to:

`REQUIRES_REVIEW`

with failure code:

`DUPLICATE_AUTHORIZATION`

## 11:24:31

The later authorization created by the unsafe retry was reversed.

The original authorization remained active.

Provider state became:

- total records: 2
- active authorizations: 1
- duplicate authorizations: 0

## 11:24:45

The Payment API queried authoritative provider state again.

Exactly one active authorization remained.

The internal payment was reconciled to:

`AUTHORIZED`

using the original provider reference.

## Recovery Validation

Final checks confirmed:

- payment amount: AED 400
- payment status: AUTHORIZED
- active provider authorizations: 1
- duplicate authorizations: 0
- ledger amount: AED 400
- webhook delivery: DELIVERED
- webhook HTTP status: 200
- Datadog duplicate metric: 0
- Prometheus incident alerts: cleared
