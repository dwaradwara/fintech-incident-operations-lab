# INC002 Stakeholder Update

Status: Investigating

We are investigating failures delivering payment authorization webhooks to a merchant callback endpoint.

Payment authorization itself remains operational. The affected transactions are successfully reaching AUTHORIZED status, but downstream merchant notifications are returning HTTP 500.

Current findings:

- Payment API remains available
- Payment authorization remains successful
- Three merchant webhook deliveries are affected
- Each affected delivery exhausted five retry attempts
- Centralized logs show repeated HTTP 500 responses
- Database records confirm payments are AUTHORIZED while webhook delivery status is FAILED

Impact:

Merchant systems may not receive timely payment authorization notifications, potentially delaying downstream order processing.

Next actions:

- Confirm merchant endpoint recovery
- Replay only failed webhook deliveries
- Validate successful delivery
- Confirm monitoring recovery
