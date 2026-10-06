# INC005 Stakeholder Update

## Status

RESOLVED

## Summary

A controlled payment authorization test produced an ambiguous outcome after the upstream provider successfully authorized an AED 400 payment but the response exceeded the Payment API timeout.

An unsafe retry of the same payment intent then created a second active AED 400 provider authorization.

The issue was detected through payment ambiguity and duplicate-authorization monitoring.

## Impact

One synthetic payment intent for AED 400 temporarily had two active provider authorizations.

Total active authorization exposure during the controlled incident was AED 800 for an intended AED 400 payment.

No additional payment intent was created internally because the existing idempotency key continued to identify the original payment record.

## Investigation

The Payment API recorded the transaction as UNKNOWN after the provider response timed out.

Provider-state investigation confirmed that the first authorization had actually succeeded.

A controlled unsafe retry bypassed the provider-state verification path and caused a second provider authorization for the same payment ID.

The corrected retry path then queried authoritative provider state, detected two active authorizations, blocked further authorization attempts, and moved the payment to REQUIRES_REVIEW.

## Resolution

The unsafe retry mode was disabled.

The second authorization created by the retry was identified by timestamp and reversed.

The original provider authorization was preserved.

The Payment API then reconciled the internal payment record against the surviving provider authorization.

Final validation confirmed:

- one active provider authorization
- zero duplicate authorizations
- internal payment status AUTHORIZED
- ledger amount AED 400
- ledger currency AED
- merchant webhook DELIVERED with HTTP 200
- Datadog duplicate-authorization metric returned to zero
- Prometheus incident alerts returned to healthy state

## Current State

The controlled incident is fully recovered.

No autonomous remediation was used to select which authorization to reverse.

The reversal decision was based on provider evidence identifying the later authorization as the one created by the unsafe retry.

## Scope

This incident used synthetic transactions in a controlled engineering lab and does not represent a production financial incident.
