#pragma once

#include "member2/calibration_types.h"
#include "member5/fusion_types.h"

namespace sih26168::member5 {

/* Temporary kinematic stand-in until Member 3 delivers EKFFusionEngine.
   Same NavigationState contract; swap the implementation, keep this header. */
class StubFusionEngine {
public:
    void reset();
    void predict(const sih26168::member2::AlignedIMUFrame& imu,
                 sih26168::member3::NavigationMode mode);
    void updateGnss(double timestamp, double lat, double lon, double alt, double speed);
    void updateAiSpeed(double timestamp, double v_x, double variance);
    const sih26168::member3::NavigationState& state() const { return state_; }

private:
    sih26168::member3::NavigationState state_{};
    bool have_time_{false};
    double last_t_{0.0};
    bool have_ai_{false};
    double ai_vx_{0.0};
    bool have_gnss_speed_{false};
    double gnss_vx_{0.0};
};

}  // namespace sih26168::member5
