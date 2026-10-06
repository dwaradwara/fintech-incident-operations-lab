# Runbook — Ambiguous Payment Outcome / Duplicate Authorization

## Trigger Conditions

Use this runbook when:

- a payment-provider request times out
- payment state is UNKNOWN
- duplicate authorization monitoring fires
- support receives a report of possible duplicate authorization
- internal payment state disagrees with provider state

## Safety Rule

Do not assume that timeout means failure.

Do not automatically repeat the authorization operation.

## Triage

Identify:

- payment ID
- merchant ID
- idempotency key
- amount
- currency
- internal status
- provider reference if available
- incident start time

Check application logs for:

- `payment_authorization_unknown`
- `provider_state_lookup_failed`
- `duplicate_authorization_detected`

## Provider Verification

Query provider state using the original payment/request identifier.

Determine the number of active authorizations.

### Zero Active Authorizations

Keep the payment unresolved.

Do not blindly authorize again unless the approved retry workflow explicitly permits it.

Escalate if authoritative state cannot be established.

### One Active Authorization

Record the provider reference.

Reconcile the internal payment to the provider authorization.

Validate ledger and webhook processing.

### Multiple Active Authorizations

Move the payment to manual review.

Stop further automatic retries.

Record every provider reference, timestamp, amount, and currency.

Do not choose an authorization to reverse without evidence and approval.

## Duplicate Authorization Decision

When evidence establishes which authorization resulted from the unintended retry:

1. preserve the intended/original authorization
2. reverse only the confirmed duplicate
3. retain provider evidence
4. verify the reversal succeeded
5. query provider state again

Expected state after recovery:

`active_authorizations = 1`

## Business Validation

Verify:

- payment status = AUTHORIZED
- exactly one active provider authorization
- provider amount matches payment amount
- provider currency matches payment currency
- ledger entry exists
- ledger amount and currency match
- webhook delivery completed where applicable

## Monitoring Validation

Verify:

- duplicate authorization metric = 0
- reconciliation mismatch = 0
- queue health is normal
- duplicate alert recovered
- ambiguous-event alert recovered after its evaluation window

## Escalation Package

Include:

- payment ID
- idempotency key
- amount/currency
- internal state
- provider references
- authorization timestamps
- SQL evidence
- correlated logs
- relevant metrics
- customer/business impact
- actions already taken
- exact engineering/provider question

## Closure Criteria

Close only when both technical and business state are validated.

A healthy API endpoint alone is insufficient evidence of financial recovery.

## Provider-Side Idempotency

Normal operation requires provider-side idempotency to remain enabled.

A repeated authorization request using the same idempotency key should return the existing authorization rather than create another authorization.

If duplicate-authorization testing is required in this controlled lab, provider-side idempotency may be deliberately disabled for the incident exercise only.

It must be restored immediately after failure injection.
