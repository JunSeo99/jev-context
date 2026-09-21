# Information handling standard
Status: active, revision 4

## Transfer boundaries
Downloadable finance files must not contain personal contact fields.
This includes buyer_email, phone numbers, and street addresses.
The rule applies to all roles, including account administrators.
Account identifiers are retained in internal audit records only.

## Events
Record actor, account, requested interval, and exported row count.
Never attach CSV contents to an audit event or error report.
Empty exports still emit an event with a row count of zero.

## Office operations
Paper receipts are shredded after scanning has been verified.
Badge replacements go through the facilities mailbox.
Questions about account exports are tracked with the billing team.
