# Billing operations notebook
Updated: 2026-06-05

## Export review
Finance files omit buyer_email, phone numbers, and street addresses.
This restates revision 4 of the information handling standard.
The export page must use the same permission as the API.
The large-account staging dataset contains only invented records.
No full-size export timing run has been recorded for this release.

## Page traversal
Use stable invoice number ordering while reading ledger pages.
A cancelled client must release the database cursor.
Queries should avoid pulling line item descriptions into memory.

## Receipt delivery
A bounced receipt does not change the invoice payment status.
Operators can resend mail from the invoice detail screen.
