#pragma once

#include "sih26168/v2x/config.hpp"
#include "sih26168/v2x/types.hpp"

#include <string>

namespace sih26168::v2x {

struct ValidationResult {
    SecurityStatus disposition{SecurityStatus::Invalid};
    std::string reason;
    double age_s{0.0};
    bool duplicate{false};
    bool out_of_order{false};
};

bool isFiniteMessage(const NormalizedV2XMessage& msg);
double speedMagnitude(const EnuVector& v);
double accelMagnitude(const EnuVector& a);

ValidationResult validateKinematics(const NormalizedV2XMessage& msg, const V2XConfig& cfg,
                                    double last_sender_time_s, const GeoPosition* last_geo);

}  // namespace sih26168::v2x
