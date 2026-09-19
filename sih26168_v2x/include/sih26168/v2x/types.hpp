#pragma once

#include <array>
#include <cstdint>
#include <string>
#include <string_view>

namespace sih26168::v2x {

// Units: seconds, metres, metres/second, radians, degrees as named in fields.
// See docs/V2X_MESSAGE_MODEL.md.

inline constexpr double kEarthRadiusM = 6378137.0;  // WGS84 equatorial, matches Member 3
inline constexpr double kChi2Dof2P95 = 5.991;       // 2-DOF 95% NIS
inline constexpr double kChi2Dof2P99 = 9.210;       // 2-DOF 99% NIS
inline constexpr double kMaxPassengerSpeedMps = 55.0;

enum class MessageType : std::int32_t {
    Unknown = 0,
    CamLike = 1,       // CAM-inspired kinematic broadcast (normalized, not a full ETSI CAM)
    BsmLike = 2,       // SAE J2735 BSM-inspired kinematic broadcast (normalized)
    Relative = 3,      // Explicit relative range/bearing if a future radio provides it
    Replay = 4,
    TestFixture = 5
};

enum class MessageSource : std::int32_t {
    Unknown = 0,
    Simulator = 1,
    Replay = 2,
    Udp = 3,
    TestFixture = 4,
    HardwareObu = 5  // reserved enum; MODE A has no OBU implementation
};

enum class SourceQuality : std::int32_t {
    Unknown = 0,
    Low = 1,
    Medium = 2,
    High = 3
};

// Trust pipeline. AUTHENTICATED is only set by a real security provider.
enum class SecurityStatus : std::int32_t {
    Received = 0,
    Unverified = 1,
    Untrusted = 2,
    Invalid = 3,
    Rejected = 4,
    Stale = 5,
    Validated = 6,
    Authenticated = 7  // cryptographic; MockSecurityProvider never sets this
};

enum class GateDecision : std::int32_t {
    Reject = 0,
    Downweight = 1,
    Accept = 2,
    Unavailable = 3
};

enum class CooperativeKind : std::int32_t {
    None = 0,
    RelativeTransferPosition = 1,  // p_ego = p_remote - r_propagated
    ExplicitRelative = 2,          // range/bearing present in the message
    ClusterConsensus = 3
};

struct GeoPosition {
    double latitude_deg{0.0};
    double longitude_deg{0.0};
    double altitude_m{0.0};
};

// Local East-North-Up. +X east, +Y north, +Z up. Origin is a WGS84 tangent point.
struct EnuVector {
    double east_m{0.0};
    double north_m{0.0};
    double up_m{0.0};
};

struct VehicleDimensions {
    double length_m{0.0};
    double width_m{0.0};
    double height_m{0.0};
    bool valid{false};
};

struct TimestampPair {
    double sender_time_s{0.0};    // time of kinematic sample on sender clock
    double receive_time_s{0.0};   // arrival time on receiver clock
    double clock_offset_s{0.0};   // receiver - sender estimate; 0 if unknown
    double jitter_s{0.0};
};

// Normalized internal V2X message. All transports decode into this type.
struct NormalizedV2XMessage {
    std::string vehicle_id;  // pseudonym, not a persistent identity
    TimestampPair time{};
    GeoPosition geo{};
    EnuVector velocity_enu{};       // m/s, local ENU
    EnuVector acceleration_enu{};   // m/s^2, local ENU
    double heading_rad{0.0};        // 0 = North, increasing toward East (CAM/BSM compass)
    double yaw_rate_rps{0.0};
    VehicleDimensions dimensions{};
    MessageType message_type{MessageType::Unknown};
    MessageSource source{MessageSource::Unknown};
    SourceQuality quality{SourceQuality::Unknown};
    SecurityStatus declared_security{SecurityStatus::Unverified};
    double declared_pos_std_m{5.0};
    double declared_vel_std_mps{1.0};
    bool has_explicit_relative{false};
    EnuVector relative_enu{};  // remote minus ego, if the radio provides ranging
    double relative_std_m{0.0};
};

struct RemoteVehicleState {
    std::string vehicle_id;
    double timestamp_s{0.0};
    GeoPosition geo{};
    EnuVector position_enu{};
    EnuVector velocity_enu{};
    EnuVector acceleration_enu{};
    double heading_rad{0.0};
    double yaw_rate_rps{0.0};
    VehicleDimensions dimensions{};
    MessageType message_type{MessageType::Unknown};
    MessageSource source{MessageSource::Unknown};
    SourceQuality quality{SourceQuality::Unknown};
    SecurityStatus security{SecurityStatus::Received};
    double age_s{0.0};
    double pos_std_m{5.0};
    double vel_std_mps{1.0};
    bool usable{false};
    bool has_explicit_relative{false};
    EnuVector relative_enu{};
    double relative_std_m{0.0};
};

// Ego state consumed by this library. Independent of Member 3 headers.
// Velocity uses Member 3 vehicle-frame convention so a future EKF hook-up
// does not invent a second kinematics model. See docs/ARCHITECTURE.md.
struct LocalNavigationState {
    double timestamp_s{0.0};
    double latitude_deg{0.0};
    double longitude_deg{0.0};
    double altitude_m{0.0};
    double v_x{0.0};  // vehicle +X (Member 3 / Member 2 forward)
    double v_y{0.0};  // vehicle +Y as consumed by Member 3 EKF
    double yaw_rad{0.0};  // 0 = North, increasing toward East
    std::array<std::array<double, 2>, 2> position_cov_ne{{{25.0, 0.0}, {0.0, 25.0}}};
    bool gnss_available{false};
    bool valid{false};
};

struct CooperativeMeasurement {
    double timestamp_s{0.0};
    double north_m{0.0};
    double east_m{0.0};
    double v_north_mps{0.0};
    double v_east_mps{0.0};
    std::array<std::array<double, 2>, 2> position_cov_ne{{{1.0e6, 0.0}, {0.0, 1.0e6}}};
    CooperativeKind kind{CooperativeKind::None};
    MessageSource source{MessageSource::Unknown};
    SourceQuality quality{SourceQuality::Unknown};
    double age_s{0.0};
    int contributing_vehicles{0};
    bool has_position{false};
    bool has_velocity{false};
};

struct CooperativeMeasurementResult {
    GateDecision decision{GateDecision::Unavailable};
    CooperativeMeasurement measurement{};
    double nis{0.0};
    std::string reason{"no_v2x"};
};

struct HealthStatus {
    std::uint64_t received{0};
    std::uint64_t validated{0};
    std::uint64_t rejected{0};
    std::uint64_t stale{0};
    std::uint64_t duplicates{0};
    std::uint64_t out_of_order{0};
    std::uint64_t tracked_vehicles{0};
    bool transport_ok{true};
    std::string transport_name{"none"};
};

inline constexpr std::string_view kLibraryStatus = "MODE_A_SOFTWARE_SIMULATION_ONLY";

}  // namespace sih26168::v2x
