#include "sih26168/v2x/security.hpp"

namespace sih26168::v2x {

SecurityStatus MockSecurityProvider::evaluate(const NormalizedV2XMessage& msg, const V2XConfig& cfg,
                                              std::string& reason) const {
    // MODE A: no cryptography. Never upgrades a message to Authenticated.
    switch (msg.declared_security) {
        case SecurityStatus::Rejected:
        case SecurityStatus::Invalid:
        case SecurityStatus::Untrusted:
            if (cfg.reject_untrusted) {
                reason = "declared_untrusted";
                return SecurityStatus::Rejected;
            }
            reason = "untrusted_allowed";
            return SecurityStatus::Untrusted;
        case SecurityStatus::Authenticated:
            if (cfg.allow_claimed_authenticated_simulation) {
                reason = "claimed_authenticated_simulation_only";
                return SecurityStatus::Unverified;
            }
            reason = "claimed_auth_ignored";
            return SecurityStatus::Unverified;
        case SecurityStatus::Unverified:
        case SecurityStatus::Received:
        case SecurityStatus::Validated:
        case SecurityStatus::Stale:
        default:
            if (cfg.reject_unverified) {
                reason = "unverified_rejected";
                return SecurityStatus::Rejected;
            }
            reason = "unverified_mock";
            return SecurityStatus::Unverified;
    }
}

std::unique_ptr<IV2XSecurityProvider> makeMockSecurityProvider() {
    return std::make_unique<MockSecurityProvider>();
}

}  // namespace sih26168::v2x
