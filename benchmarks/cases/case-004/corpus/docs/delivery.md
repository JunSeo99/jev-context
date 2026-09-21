# Outbound delivery contract
Revision 3, active 2026-03-12

Retry network failures, 429, and all 5xx responses.
Other 4xx responses are terminal; 2xx responses acknowledge delivery.
Redirect responses are terminal and must not be followed.
Attempt counts include the first send; stop at max_attempts.
Use configured backoff for the retry index.
For 429, a valid integer Retry-After replaces backoff, capped by config.
Negative, date-form, or malformed Retry-After uses normal backoff.
The header is ignored for statuses other than 429.

## Receiver deduplication
X-Event-Id is the persisted event id and is unchanged on every attempt.
Delivery remains at-least-once; receivers should deduplicate by that id.
The signature covers the same serialized payload on every attempt.

## Related material
[Lifecycle](lifecycle.md) governs whether a send may begin.
Response bodies are not retained in the delivery dashboard.
