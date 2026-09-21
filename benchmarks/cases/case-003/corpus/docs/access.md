# Resource access and ownership
Current standard, revision 7

A write requires the workspace editor role before reading the body.
Owner identity is taken from the authenticated workspace context.
A request parameter must not override the workspace destination.
Temporary blobs remain private until their record transaction commits.
If record creation fails, enqueue the temporary blob for deletion.

## Counters
Meter committed bytes, not rejected or quarantined bytes.
Size counters use binary bytes internally.
The billing screen may round them for display.

## Other resources
Project icons inherit project visibility.
Deleted folders are hidden from navigation immediately.
Thumbnail cache cleanup is independent of attachment accounting.
