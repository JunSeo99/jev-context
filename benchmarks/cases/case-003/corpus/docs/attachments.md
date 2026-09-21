# Attachment intake
Effective: 2026-04-08

Accept PDF and ZIP only after extension and detected format agree.
Enforce compressed-byte, expanded-byte, and entry limits from config.
Check the expanded size before extracting archive contents.
Nested archives are rejected; directory entries count toward the limit.
Path traversal and absolute archive member paths are rejected.
A ZIP failing any archive rule returns 422 with code invalid_archive.

## Transport
Count streamed bytes; Content-Length alone is not a limit check.
A compressed-byte limit violation returns 413 with code too_large.
A detected-format mismatch returns 415 with code unsupported.
[Desktop responses](desktop.md) describe envelope compatibility.

## Preview
Password-protected PDFs can be stored but have no inline preview.
The icon should remain visible when a preview is unavailable.
All intake also follows [resource access](access.md).
