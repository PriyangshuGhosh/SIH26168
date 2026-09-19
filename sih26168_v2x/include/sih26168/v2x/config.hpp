#pragma once

#include "sih26168/v2x/types.hpp"

namespace sih26168::v2x {

struct V2XConfig {
    double origin_latitude_deg{12.9716};   // default Bangalore-ish tangent; overridden by first ego fix
    double origin_longitude_deg{77.5946};
    double origin_altitude_m{920.0};
    bool origin_locked{false};

    double max_speed_mps{kMaxPassengerSpeedMps};
    double max_accel_mps2{12.0};
    double max_yaw_rate_rps{1.5};
    double max_message_age_s{1.5};
    double downweight_age_s{0.40};
    double min_dt_s{1.0e-4};
    double track_timeout_s{3.0};

    double reject_jump_m{80.0};
    double max_rel_process_std_mps{4.0};
    double relative_snapshot_max_age_s{30.0};
    double age_time_constant_s{0.20};
    double clock_offset_std_s{0.020};

    double nis_accept{kChi2Dof2P95};
    double nis_reject{kChi2Dof2P99};
    double downweight_scale{4.0};

    bool reject_untrusted{true};
    bool reject_unverified{false};
    bool allow_claimed_authenticated_simulation{false};

    double min_pos_std_m{1.0};
    double max_pos_std_m{50.0};
    double quality_low_scale{2.5};
    double quality_medium_scale{1.0};
    double quality_high_scale{0.7};

    int max_vehicles{32};
};

}  // namespace sih26168::v2x
