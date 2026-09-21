# Invoice CSV contract
Status: current, 2026-06-02

Exports are an account-level administrative capability.
Require the account_admin role and bind every page to that account.
Date range length is the difference between to and from, in UTC days.
Read the tier limit from [billing settings](../settings/billing.toml).
A request beyond that limit is rejected, never silently shortened.

## Rows and columns
Closed invoices may be included when allow_closed is true.
Voided invoices are excluded regardless of the include_closed flag.
Amounts remain integer minor units; currency is a three-letter code.
Column order is number, issued_on, amount_minor, currency.
The previous customer-contact column is not part of the new contract.
See the [information handling standard](handling.md) for all exports.

## Downloads
Keep the existing attachment filename format.
A comma is always the delimiter, even for localized interfaces.
