#pragma once

namespace sih26168::v2x {

// MODE A: DESIGNED only. Not implemented. Not a C-V2X/OBU adapter.
// A future Android layer would own lifecycle and feed NormalizedV2XMessage
// into V2XCore. This header is a boundary comment, not a radio driver.
inline constexpr const char* kAndroidV2XStatus =
    "DESIGNED_NOT_IMPLEMENTED_MODE_A_SIMULATION_ONLY";

}  // namespace sih26168::v2x
