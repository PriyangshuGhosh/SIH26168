#pragma once

#include "sih26168/v2x/types.hpp"

namespace sih26168::v2x {

struct MessageTiming {
    double message_age_s{0.0};
    double estimated_event_time_s{0.0};
    bool stale{false};
    bool out_of_order{false};
    bool duplicate{false};
};

// age = receive - sender - clock_offset. Positive age means the sample is old
// on the receiver clock. Covariance inflation uses this age, not a heuristic score.
MessageTiming evaluateTiming(const TimestampPair& time, double last_sender_time_s,
                             double max_age_s, double min_dt_s);

double ageInflationScale(double age_s, double time_constant_s);
double timeSyncPositionStdM(double clock_offset_std_s, double speed_mps);

}  // namespace sih26168::v2x
