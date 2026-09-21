# Desktop integration notes
Supported integration: versions 2.4 and later

Desktop 2.4 requires {"error": code} for all upload failures.
Web and desktop 2.5+ receive {"error": {"code": code}}.
Keep the documented HTTP status for every client version.
Older clients receive the same content validation as web clients.
The compatibility rule changes the envelope only.
Desktop 2.4's upload dialog may suggest splitting a rejected file.

## Copy for support
All clients share validation; only error object shape differs.
Ask for client version and error code, not the original attachment.
No measured file-size distribution is included in these notes.
The sample files in development are unrelated to production volume.

## Release packaging
Auto-update requires a signed package and a stable network connection.
Offline clients retry their update check on the next launch.
