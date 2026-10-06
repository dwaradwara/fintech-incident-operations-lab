# INC001 - Payment Authorization Failure Spike

## Classification

Severity: Simulated SEV-1 / Critical

Service:
Payment authorization

## Detection

The incident was detected by business-level monitoring.

Firing monitors:

- HighPaymentAuthorizationFailureRate
- ProviderHttpErrorsDetected

Infrastructure and health endpoints remained available while payment authorization failures increased significantly.

## Customer Impact

Customers experienced failed checkout/payment authorization attempts.

Successful and failed requests occurred concurrently, indicating partial upstream provider degradation rather than a complete platform outage.

## Initial Assessment

Payment API: reachable
PostgreSQL: reachable
Redis: reachable
Webhook infrastructure: reachable
Payment provider health endpoint: reachable
Payment authorization requests: degraded

## Working Hypothesis

The failure domain is the upstream payment provider authorization path.

Application logs show HTTP 503 responses from the provider while the local application and supporting infrastructure remain healthy.

## Immediate Action

Escalate as a payment-provider degradation incident.

Continue monitoring authorization failure rate, provider HTTP errors, and affected transaction volume while mitigation is performed.
