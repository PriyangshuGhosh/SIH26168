#pragma once

namespace sih26168::member5 {

/* Canonical navigation speed is metres per second. UI may convert to km/h. */
inline constexpr double kMpsToKmh = 3.6;
inline constexpr double kKmhToMps = 1.0 / 3.6;

inline double mpsToKmh(double speed_mps) { return speed_mps * kMpsToKmh; }
inline double kmhToMps(double speed_kmh) { return speed_kmh * kKmhToMps; }

}  // namespace sih26168::member5
