# Non-human access standard
Active revision 5

Shared integrations must use a service account owned by the workspace.
Personal API keys must never be entered into shared connector settings.
The setup operator needs the workspace administrator role.
Store credentials in the secret store, not in tickets or screenshots.
Rotation follows the configured credential interval.

## Offboarding
Changing the human setup operator must not break a service account.
Removing an integration revokes its credential and scheduled jobs.
A disabled connection cannot be re-enabled without an owner check.

## Directory housekeeping
Display names may be updated without rotating a credential.
Group membership changes are logged by the directory service.
Emergency access is tracked under a separate incident procedure.
