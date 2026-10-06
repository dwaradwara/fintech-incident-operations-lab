# Incident Stakeholder Update

Status: Investigating

We are investigating elevated payment authorization failures affecting checkout transactions.

The payment API and supporting platform components remain available. Investigation has isolated the degradation to the upstream payment authorization provider, which is returning intermittent HTTP 503 responses.

Impact:
A significant percentage of new authorization attempts are failing.

Actions underway:
- Monitoring authorization success and failure rates
- Identifying affected payment transactions
- Confirming upstream provider behaviour
- Preparing controlled recovery validation

No evidence currently indicates a PostgreSQL, Redis, or internal application availability issue.

Next update will follow after mitigation and recovery validation.
