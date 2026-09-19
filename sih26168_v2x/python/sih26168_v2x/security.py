from __future__ import annotations

from .types import NormalizedV2XMessage, SecurityStatus, V2XConfig


class MockSecurityProvider:
    """No cryptography. Never authenticates. MODE A simulation only."""

    def evaluate(self, msg: NormalizedV2XMessage, cfg: V2XConfig) -> tuple[SecurityStatus, str]:
        dec = msg.declared_security
        if dec in (SecurityStatus.REJECTED, SecurityStatus.INVALID, SecurityStatus.UNTRUSTED):
            if cfg.reject_untrusted:
                return SecurityStatus.REJECTED, "declared_untrusted"
            return SecurityStatus.UNTRUSTED, "untrusted_allowed"
        if dec == SecurityStatus.AUTHENTICATED:
            return SecurityStatus.UNVERIFIED, "claimed_auth_ignored"
        if cfg.reject_unverified:
            return SecurityStatus.REJECTED, "unverified_rejected"
        return SecurityStatus.UNVERIFIED, "unverified_mock"
