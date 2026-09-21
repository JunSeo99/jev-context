# Account lifecycle operations
Current state machine

State progresses active -> deleting -> removed.
Any outward transfer must recheck account state at execution time.
When state is deleting or removed, cancel queued outward transfers.
This applies to webhook retries and export notification email alike.
Do not send one final webhook to announce account deletion.
A cancellation is recorded internally without receiver contact.

## Retained records
Keep the deletion request id in the internal audit trail.
Delivery payloads are removed by the normal deletion job.
Operators cannot reactivate an account after removed.

## UI behavior
Deleting accounts show a read-only progress screen.
Invitations cannot be accepted while deletion is in progress.
The organization name can still appear on an old invoice.
