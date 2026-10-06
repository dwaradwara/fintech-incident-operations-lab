# INC005 Root Cause Analysis

## Incident

**Ambiguous Payment Outcome / Duplicate Authorization**

A controlled AED 400 payment authorization succeeded at the upstream provider, but the provider response arrived after the Payment API timeout.

The Payment API therefore could not determine whether the financial operation had succeeded and correctly recorded the payment as:

`UNKNOWN`

During controlled incident injection, an unsafe retry repeated the provider authorization without first establishing authoritative provider state.

This produced two active AED 400 provider authorizations for the same payment intent.

---

## Root Cause

The root cause was **repeating an external financial operation after an ambiguous timeout without first verifying the authoritative provider state**.

The first provider authorization had already succeeded.

However, because the provider delayed its response beyond the Payment API timeout, the caller did not receive confirmation.

The unsafe retry path treated that uncertainty as permission to issue another authorization request.

The provider accepted the second request and created another active authorization for the same payment ID.

The failure sequence was:

```text
Payment request
      ↓
Provider authorizes AED 400
      ↓
Provider response is delayed
      ↓
Payment API times out
      ↓
Internal state = UNKNOWN
      ↓
Unsafe retry bypasses provider-state verification
      ↓
Second provider authorization
      ↓
Two active AED 400 authorizations
