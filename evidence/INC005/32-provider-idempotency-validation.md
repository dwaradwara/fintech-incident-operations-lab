# Provider-Side Idempotency Validation

## Purpose

Validate the permanent defensive control added after INC005.

In normal operation, repeated authorization requests using the same provider idempotency key must return the original authorization instead of creating a second external financial side effect.

## Test

The same authorization request was submitted twice with:

- payment ID: `idempotency-test-001`
- amount: AED 400
- idempotency key: `checkout-idem-001`
- provider idempotency enforcement: enabled

## Result

The first request created an authorization.

The second request returned:

`idempotent_replay = true`

Both responses returned the same provider reference:

`22c3f85f-8d9a-4450-b0ec-8f43adcab610`

Provider duplicate inspection returned:

- duplicate payment count: 0
- duplicate authorizations: 0

## Control

Normal provider behavior:

`enforce_idempotency = true`

A repeated authorization with the same idempotency key returns the existing active authorization instead of creating another one.

## Controlled Failure Injection

INC005 remains reproducible only when provider-side idempotency is deliberately disabled:

`enforce_idempotency = false`

This bypass exists solely for controlled incident simulation.

Production-safe behavior keeps provider-side idempotency enabled.

## Operational Lesson

Local idempotency protects the internal payment intent.

Provider-side idempotency protects the external financial side effect.

For payment authorization, both controls are valuable.
