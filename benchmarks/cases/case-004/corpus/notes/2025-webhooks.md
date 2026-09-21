# Webhook beta retrospective
Archived; revision 3 supersedes retry decisions

The beta retried only server errors at a fixed sixty seconds.
It created a new event header on each HTTP attempt.
Rate-limit responses were shown as permanent failures.
Attempts were not bounded because the queue had a seven-day expiry.
A deletion-complete webhook was proposed but never shipped.

## Other work
The dashboard gained a copy-ID button.
Event types were sorted alphabetically in the create dialog.
JSON examples now use two spaces for indentation.
The old receiver sandbox was removed after the beta ended.
