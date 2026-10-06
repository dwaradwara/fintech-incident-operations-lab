# INC005 Postmortem — Ambiguous Payment Outcome and Duplicate Authorization

## Executive Summary

A controlled upstream timeout created an ambiguous payment state.

The provider successfully authorized an AED 400 payment but delayed the response long enough for the Payment API to time out.

The Payment API correctly recorded the transaction as UNKNOWN because a transport timeout does not prove that the provider rejected or failed to process the authorization.

A deliberately enabled unsafe retry path then repeated the provider authorization before verifying authoritative provider state.

The provider accepted the second request and created a second active authorization for the same payment intent.

The corrected safe path subsequently detected the duplicate, stopped further authorization attempts, required human review, reversed only the later authorization, and reconciled the internal payment to the original authorization.

## Customer / Business Impact

Controlled synthetic scope:

- intended payment amount: AED 400
- intended payment intents: 1
- active provider authorizations during incident: 2
- temporary authorization exposure: AED 800
- duplicate authorization exposure: AED 400

This lab models authorization state only. It does not claim that two settlement or capture operations occurred.

## Detection

The incident was detected through business-level telemetry.

Prometheus:

- `AmbiguousPaymentOutcomeDetected`
- `DuplicatePaymentAuthorizationDetected`

Datadog:

- `fintech.payments.duplicate_authorizations = 1`

Application logs:

- `payment_authorization_unknown`
- `unsafe_unknown_retry_injected`
- `provider_state_lookup_started`
- `provider_state_lookup_completed`
- `duplicate_authorization_detected`

## Root Cause

The underlying failure mode was incorrect handling of an ambiguous provider response.

The provider committed the authorization before the Payment API received the response.

The network/request timeout therefore described only the transport result:

> the caller did not receive a response within the configured timeout.

It did not establish the business result:

> whether the provider had authorized the payment.

The duplicate was created when an unsafe retry bypassed authoritative provider-state verification and issued the financial operation again.

## Why Local Idempotency Was Not Sufficient

The PostgreSQL payment table contains a unique idempotency key.

That prevented creation of a second local payment intent.

However, local database idempotency alone cannot prevent repeated side effects at an external payment provider if the application sends the authorization operation more than once.

The same internal payment ID was therefore able to accumulate two provider authorizations during the deliberately unsafe retry.

## Contributing Factors

1. Provider authorization was committed before the delayed response was returned.
2. The caller used a shorter timeout than the simulated post-authorization response delay.
3. The controlled unsafe retry path allowed UNKNOWN state to trigger another provider authorization.
4. The simulated provider intentionally did not reject repeated authorization requests for the same payment intent.
5. Provider state had to be treated as authoritative after the ambiguous response.

## Containment

The unsafe retry feature was disabled.

Provider latency was restored to its healthy configuration.

The same idempotent request was then processed through the safe path.

Instead of issuing another authorization, the Payment API queried provider state.

Two active authorizations were discovered.

The payment moved to:

`REQUIRES_REVIEW`

and the API returned HTTP 409 rather than performing another financial action.

## Recovery

Provider evidence was ordered by authorization timestamp.

The earlier authorization was identified as the original successful payment operation.

The later authorization was identified as the one created by the controlled unsafe retry.

Only the later authorization was reversed.

After reversal, provider state showed exactly one active authorization.

The Payment API queried provider state again and reconciled the internal payment to the surviving original authorization.

Normal downstream processing then produced the ledger entry and merchant webhook.

## Final Validation

Provider:

- active authorizations: 1
- duplicate authorizations: 0
- duplicate authorization: REVERSED
- original authorization: AUTHORIZED

Payment database:

- status: AUTHORIZED
- amount: AED 400
- currency: AED
- provider reference: original authorization
- failure code: NULL

Ledger:

- amount: AED 400
- currency: AED

Webhook:

- event type: payment.authorized
- status: DELIVERED
- HTTP status: 200

Monitoring:

- Datadog duplicate-authorization gauge: 0
- Prometheus incident alerts: cleared

## Corrective Design

The corrected state model treats provider timeouts as ambiguous:

`PENDING -> UNKNOWN`

rather than incorrectly assuming:

`PENDING -> FAILED`

For UNKNOWN or REQUIRES_REVIEW payments, retry processing first performs provider-state verification.

Decision logic:

- exactly one active authorization -> reconcile to AUTHORIZED
- multiple active authorizations -> REQUIRES_REVIEW
- no authoritative authorization -> remain unresolved and block blind automatic authorization retry

## Preventive Controls

- persist the payment intent before provider interaction
- maintain unique local idempotency keys
- use provider-side idempotency where supported
- treat transport timeouts as ambiguous financial outcomes
- query authoritative provider state before retrying a financial operation
- alert on ambiguous payment outcomes
- alert on duplicate provider authorizations
- require human review when multiple active authorizations exist
- correlate payment IDs, provider references, logs, metrics, and SQL records during investigation

## Key Operational Lesson

A timeout is not a payment result.

It proves that the caller did not receive a response within the timeout window.

Before repeating a financial operation, support and engineering teams must establish authoritative provider state.
