# Receiver integration
Applies to delivery contract revision 3

A stable X-Event-Id identifies one event across all delivery attempts.
Store processed identifiers before acknowledging success.
An acknowledgement lost in transit can cause another delivery.
Verify the signature before applying a business action.
Request a rotated secret through the account settings page.

## Testing
The sample receiver deliberately returns 503 on its first call.
Local tests do not measure production delivery percentiles.
No production delivery-latency dataset accompanies this snapshot.
A retry schedule is a policy, not a percentile guarantee.

## Dashboard
A failed indicator means no acknowledgement was recorded.
It does not prove that the receiver performed no action.
The resend button creates a new delivery of the same event.
