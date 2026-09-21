# Partner integration policy
Effective: 2026-04-21

Production launch requires security and data-owner approval.
The configured production scopes are the full allowed set.
Do not request write permission for a read-only connector.
Verify a connection with a designated non-sensitive test record.
Record the credential owner and a disable contact in the launch ticket.

## Sandbox exception
A sandbox using only generated samples may start with data-owner approval.
The exception removes security preapproval, not identity requirements.
Sandbox access ends at the configured max_duration_days.
Disable the connection and revoke its credential when the trial ends.
Sending sandbox data to external destinations is not permitted.
Converting a trial to production requires the full production review.

## References
[Identity standard](identity.md) applies to both paths.
[Review queue](../operations/review.md) describes scheduling.
