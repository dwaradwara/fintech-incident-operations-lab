# INC004 - Upstream Payment Provider Latency Degradation

## Incident Type

Controlled production-support simulation.

## Severity

Simulated SEV-2 / High

## Affected Component

Upstream payment authorization provider.

## Executive Summary

Payment authorization latency increased significantly while authorization success remained healthy.

The upstream provider continued returning successful HTTP responses, and all controlled payment transactions remained AUTHORIZED, but provider response latency increased from the normal ~150 ms range to approximately 3.5 seconds.

Business latency monitoring detected the degradation through the ProviderLatencyHigh Prometheus alert.

Centralized Elasticsearch/Kibana logs were used to identify individual successful payment transactions with multi-second provider latency.

After the upstream provider returned to normal operating latency, ten recovery transactions completed successfully with an average provider latency of 154.71 ms.

The ProviderLatencyHigh alert subsequently returned to inactive state.

## Customer / Business Impact

The payment path remained functional.

However, customers represented by the controlled traffic would have experienced significantly slower checkout and payment confirmation.

Potential impact included:

- slow checkout experience
- increased customer abandonment
- repeated client retries
- higher support contact volume
- degraded merchant conversion

## Detection

Prometheus detected elevated provider p95 latency.

Alert:

ProviderLatencyHigh

The alert transitioned to:

firing

while payment authorization failure metrics remained healthy.

## Investigation

The investigation confirmed:

- Payment API remained available
- PostgreSQL remained available
- Redis remained available
- payment authorization remained successful
- provider HTTP errors did not increase
- provider timeouts did not increase
- all 15 controlled degradation transactions were AUTHORIZED
- Kibana showed provider latency around 3.5 seconds on individual payment IDs

The issue was therefore isolated to upstream response latency rather than application availability or provider HTTP failure.

## Root Cause

The controlled payment-provider simulator was configured with an authorization response latency of approximately 3500 ms.

The provider remained reachable and returned HTTP 200 responses.

This represented performance degradation rather than an availability outage.

## Mitigation

Provider response latency was restored to approximately 150 ms.

No Payment API, PostgreSQL, Redis, webhook or ledger restart was required.

## Recovery Validation

Ten fresh transactions were submitted after mitigation.

Measured provider latency:

- Transactions: 10
- Average: 154.71 ms
- Minimum: 152.59 ms
- Maximum: 160.65 ms

All recovery transactions completed successfully.

Prometheus monitoring subsequently reported:

ProviderLatencyHigh:
- state: inactive
- health: ok

## What Went Well

- Latency monitoring detected degradation despite HTTP success.
- Payment success and performance were monitored independently.
- Kibana provided transaction-level latency evidence.
- Payment IDs enabled correlation between logs and database records.
- Recovery was validated with fresh transaction traffic.
- Monitoring independently confirmed recovery.

## What Could Be Improved

- Add latency SLOs for the payment authorization path.
- Add provider-specific p50, p95 and p99 dashboard panels.
- Add synthetic payment-provider latency monitoring.
- Add automated incident enrichment with recent slow payment IDs.
- Consider provider failover or circuit-breaking strategy for severe latency degradation.

## Corrective Actions

| Action | Priority | Status |
|---|---|---|
| Provider latency histogram | P1 | Completed |
| Provider p95 latency alert | P1 | Completed |
| Structured payment latency logs | P1 | Completed |
| Kibana latency investigation | P1 | Completed |
| Recovery transaction validation | P1 | Completed |
| Provider latency dashboard | P2 | Planned |
| Synthetic provider monitoring | P2 | Planned |
| Automated incident enrichment | P2 | Planned |

## Final Status

Resolved.

Provider latency returned to the normal operating range and the latency alert returned to inactive state.
