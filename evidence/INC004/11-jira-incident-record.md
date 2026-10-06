# Payment Provider Latency Degradation

## Type

Incident

## Priority

High / Simulated SEV-2

## Component

Payment Authorization / External Provider

## Summary

Payment authorization remained successful but upstream provider latency increased to approximately 3.5 seconds.

## Impact

15 controlled transactions remained AUTHORIZED but experienced significant authorization latency.

Customer-facing payment confirmation would have been substantially slower.

## Detection

Prometheus:

ProviderLatencyHigh

State:
firing

## Investigation

Application and infrastructure dependencies remained healthy.

Kibana showed successful payment authorization events with provider latency above 3 seconds.

No corresponding increase occurred in:

- provider HTTP errors
- provider timeouts
- authorization failures

## Root Cause

Controlled upstream provider latency degradation.

## Recovery

Provider latency restored to approximately 150 ms.

10 recovery transactions completed successfully.

Recovery latency:

- Average: 154.71 ms
- Minimum: 152.59 ms
- Maximum: 160.65 ms

ProviderLatencyHigh returned to inactive.
