#pragma once

#include "sih26168/v2x/config.hpp"
#include "sih26168/v2x/frames.hpp"
#include "sih26168/v2x/measurement.hpp"
#include "sih26168/v2x/security.hpp"
#include "sih26168/v2x/transport.hpp"
#include "sih26168/v2x/types.hpp"
#include "sih26168/v2x/validation.hpp"

#include <memory>
#include <string>
#include <unordered_map>
#include <vector>

namespace sih26168::v2x {

class V2XCore {
public:
    explicit V2XCore(V2XConfig config = V2XConfig{});

    void reset();
    void setTransport(std::unique_ptr<IV2XTransport> transport);
    void setSecurityProvider(std::unique_ptr<IV2XSecurityProvider> provider);
    void lockOrigin(const EnuOrigin& origin);

    void ingest(const NormalizedV2XMessage& message);
    std::size_t pollTransport(double now_s);

    CooperativeMeasurementResult getCooperativeMeasurement(const LocalNavigationState& local);

    std::vector<RemoteVehicleState> remoteVehicles() const;
    const HealthStatus& health() const { return health_; }
    const V2XConfig& config() const { return config_; }
    EnuOrigin origin() const { return origin_; }

private:
    V2XConfig config_{};
    EnuOrigin origin_{};
    std::unique_ptr<IV2XTransport> transport_;
    std::unique_ptr<IV2XSecurityProvider> security_;
    std::unordered_map<std::string, RemoteTrack> tracks_;
    HealthStatus health_{};

    void ingestValidated(const NormalizedV2XMessage& message, const ValidationResult& kin,
                         SecurityStatus security);
    void prune(double now_s);
};

}  // namespace sih26168::v2x
