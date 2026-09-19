# Security boundary

**NOT IMPLEMENTED:** IEEE 1609.2, PKI, or any cryptographic verification.

`IV2XSecurityProvider` / `MockSecurityProvider`:

- Maps declared status.
- Rejects `untrusted` / `invalid` / `rejected` when `reject_untrusted` (default).
- **Never** sets `Authenticated`.
- A message that *claims* authenticated is treated as unverified.

Malformed JSON and NaN/Inf inputs must not crash the library (host tests).

Do not claim messages are secure. Privacy: pseudonyms, no long-term identity, in-memory tracks, timeout.
