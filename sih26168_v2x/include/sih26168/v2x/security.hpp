#pragma once

#include "sih26168/v2x/config.hpp"
#include "sih26168/v2x/types.hpp"

#include <memory>
#include <string>

namespace sih26168::v2x {

// Cryptographic verification is NOT implemented. A future IEEE 1609.2 / ITS
// provider can implement this interface. MockSecurityProvider never claims
// authentication.
class IV2XSecurityProvider {
public:
    virtual ~IV2XSecurityProvider() = default;
    virtual SecurityStatus evaluate(const NormalizedV2XMessage& msg, const V2XConfig& cfg,
                                    std::string& reason) const = 0;
    virtual std::string name() const = 0;
};

class MockSecurityProvider final : public IV2XSecurityProvider {
public:
    SecurityStatus evaluate(const NormalizedV2XMessage& msg, const V2XConfig& cfg,
                            std::string& reason) const override;
    std::string name() const override { return "mock_unverified"; }
};

std::unique_ptr<IV2XSecurityProvider> makeMockSecurityProvider();

}  // namespace sih26168::v2x
