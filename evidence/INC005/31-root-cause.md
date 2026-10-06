# INC005 Root Cause Analysis

## Incident

**Ambiguous Payment Outcome / Duplicate Authorization**

A controlled AED 400 payment authorization succeeded at the upstream provider, but the provider response arrived after the Payment API timeout.

The Payment API therefore could not determine whether the financial operation had succeeded and correctly recorded the payment as `UNKNOWN`.

During controlled incident injection, an unsafe retry repeated the provider authorization without first establishing authoritative provider state.

This produced two active AED 400 provider authorizations for the same payment intent.

## Root Cause

The root cause was **repeating an external financial operation after an ambiguous timeout without first verifying authoritative provider state**.

The first provider authorization had already succeeded.

However, because the provider delayed its response beyond the Payment API timeout, the caller did not receive confirmation.

The unsafe retry path treated that uncertainty as permission to issue another authorization request.

The provider accepted the repeated operation and created a second active authorization for the same payment ID.

The failure sequence was:

1. Payment intent created.
2. Provider received the AED 400 authorization request.
3. Provider successfully committed the authorization.
4. Provider response was intentionally delayed.
5. Payment API exceeded its request timeout.
6. Internal payment state became `UNKNOWN`.
7. Unsafe retry bypassed provider-state verification.
8. The authorization request was sent again.
9. Provider created a second active AED 400 authorization.
10. Duplicate-authorization monitoring detected the condition.

## Triggering Condition

The controlled incident used approximately:

- normal provider processing latency: 150 ms
- post-authorization response delay: 6000 ms
- Payment API timeout: 5000 ms

The critical detail is that the provider committed the authorization **before** delaying its response.

Therefore the two states were different:

- transport result: `TIMEOUT`
- financial result: `AUTHORIZED`

A transport timeout was not evidence that the financial operation failed.

## Why the Payment State Was Ambiguous

A request timeout establishes only that the caller did not receive a response before its timeout expired.

It does not establish whether the remote system processed the request.

For payment operations, treating `TIMEOUT` as equivalent to `FAILED` is unsafe.

The correct state is `UNKNOWN` until the authoritative provider state can be verified.

## Why Local Idempotency Was Not Enough

The PostgreSQL payments table enforced a unique local idempotency key.

That successfully prevented creation of a second internal payment intent for `checkout-order-70001`.

The database therefore still contained only one logical payment.

However, local idempotency did not automatically protect the external provider side effect.

The unsafe retry reused the existing payment ID and invoked the external authorization operation again.

The simulated provider did not enforce provider-side idempotency for that repeated request.

The resulting state was:

- internal payment intents: 1
- provider authorization records: 2
- active provider authorizations: 2

This demonstrates that local database idempotency and external operation idempotency are separate controls.

## Contributing Factors

1. The provider committed the authorization before returning its HTTP response.
2. The response delay exceeded the caller timeout.
3. The resulting financial outcome was ambiguous.
4. Controlled unsafe-retry mode permitted an `UNKNOWN` payment to call the provider again.
5. Provider state was not checked before the unsafe retry.
6. The simulated provider accepted the repeated authorization request.
7. Provider-side idempotency was intentionally absent for this failure scenario.

## Detection

The incident was detected through business-level telemetry.

Prometheus alerts:

- `AmbiguousPaymentOutcomeDetected`
- `DuplicatePaymentAuthorizationDetected`

Datadog metric:

- `fintech.payments.duplicate_authorizations = 1`

Application evidence included:

- `payment_authorization_unknown`
- `unsafe_unknown_retry_injected`
- `provider_state_lookup_started`
- `provider_state_lookup_completed`
- `duplicate_authorization_detected`

Provider evidence confirmed:

- total authorization records: 2
- active authorizations: 2
- amount per authorization: AED 400

## Business Impact

Controlled synthetic scope:

- intended payment amount: AED 400
- intended payment intents: 1
- active provider authorizations during incident: 2
- temporary authorization exposure: AED 800
- duplicate authorization exposure: AED 400

This incident models authorization state only.

It does **not** claim that two captures or settlements occurred.

## Containment

Unsafe retry mode was disabled.

Provider latency was restored to normal.

The same payment request was then processed through the corrected path.

Instead of issuing another financial operation, the Payment API queried authoritative provider state.

Two active authorizations were discovered.

The payment was moved to `REQUIRES_REVIEW` with failure code `DUPLICATE_AUTHORIZATION`.

The API returned HTTP 409 and blocked any further automatic authorization attempts.

## Recovery Decision

The provider authorization records were compared using their timestamps.

The earlier authorization was identified as the original successful financial operation.

The later authorization was identified as the authorization created by the controlled unsafe retry.

Only the later authorization was selected for reversal.

The decision was evidence-based and required human review.

## Recovery

The duplicate authorization was reversed.

After reversal, provider state showed:

- total provider authorization records: 2
- active authorizations: 1
- reversed authorizations: 1
- duplicate authorizations: 0

The original provider authorization remained active.

The Payment API then queried provider state again.

Because exactly one active authorization remained, the internal payment was reconciled to `AUTHORIZED` using the original provider reference.

Downstream processing then completed successfully.

## Permanent Corrective Control

Provider timeouts are handled as ambiguous financial outcomes.

The intended state transition is:

`PENDING -> UNKNOWN -> provider-state verification`

The subsequent decision is deterministic.

### Exactly One Active Authorization

If provider lookup returns exactly one active authorization:

`UNKNOWN -> AUTHORIZED`

The internal payment is reconciled to the provider reference.

### Multiple Active Authorizations

If provider lookup returns multiple active authorizations:

`UNKNOWN -> REQUIRES_REVIEW`

Further financial operations are blocked.

Human investigation is required.

### No Confirmed Authorization

If no authoritative provider authorization can be established, the payment remains unresolved.

The system does not blindly repeat the authorization operation.

## Provider-Side Idempotency Control

After the incident, the provider simulator was hardened to enforce the authorization idempotency key during normal operation.

When the same idempotency key is submitted again while its original authorization remains active, the provider returns the existing provider reference instead of creating another authorization.

Validated behavior:

- first authorization: creates provider authorization
- repeated authorization: `idempotent_replay = true`
- provider reference remains unchanged
- duplicate authorization count remains zero

Provider-side idempotency is enabled by default.

INC005 can only reproduce the unsafe duplicate condition when this protection is explicitly disabled as a controlled failure-injection mechanism.

This complements the Payment API's verify-provider-state-before-retry rule.

## Preventive Controls

The incident established the following controls:

- persist the payment intent before provider interaction
- enforce local idempotency keys
- use provider-side idempotency where supported
- treat provider timeouts as ambiguous outcomes
- verify authoritative provider state before repeating financial operations
- block blind retries while transaction state is uncertain
- alert on ambiguous payment outcomes
- alert on duplicate provider authorizations
- move multiple-authorization cases to manual review
- require evidence before choosing an authorization for reversal
- correlate payment IDs, provider references, SQL, logs, and metrics during investigation

## Recovery Validation

Final validation confirmed:

- payment status: `AUTHORIZED`
- payment amount: AED 400
- active provider authorizations: 1
- duplicate authorizations: 0
- ledger amount: AED 400
- ledger currency: AED
- webhook status: `DELIVERED`
- webhook HTTP status: 200
- Datadog duplicate metric: 0
- Prometheus incident alerts: cleared

## Primary Operational Lesson

**A timeout is not a payment result.**

It means the caller did not receive a response within the timeout window.

Before repeating a financial operation, the system must establish authoritative provider state.

Blind retry of an ambiguous financial operation can create duplicate external side effects even when the local application has idempotency controls.
