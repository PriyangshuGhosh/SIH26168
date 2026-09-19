#include "sih26168/v2x/v2x.hpp"

#include <cassert>
#include <cmath>
#include <filesystem>
#include <fstream>
#include <limits>
#include <memory>
#include <numbers>
#include <string>

using namespace sih26168::v2x;

namespace {

NormalizedV2XMessage makeCam(const std::string& id, double t, double lat, double lon, double ve,
                             double vn) {
    NormalizedV2XMessage m{};
    m.vehicle_id = id;
    m.time.sender_time_s = t;
    m.time.receive_time_s = t + 0.05;
    m.geo = {lat, lon, 920.0};
    m.velocity_enu = {ve, vn, 0.0};
    m.heading_rad = 0.0;
    m.message_type = MessageType::CamLike;
    m.source = MessageSource::TestFixture;
    m.quality = SourceQuality::Medium;
    m.declared_security = SecurityStatus::Unverified;
    m.declared_pos_std_m = 3.0;
    m.declared_vel_std_mps = 0.5;
    return m;
}

LocalNavigationState makeLocal(double t, double lat, double lon, bool gnss) {
    LocalNavigationState s{};
    s.timestamp_s = t;
    s.latitude_deg = lat;
    s.longitude_deg = lon;
    s.altitude_m = 920.0;
    s.v_x = 15.0;
    s.v_y = 0.0;
    s.yaw_rad = 0.0;
    s.position_cov_ne = {{{25.0, 0.0}, {0.0, 25.0}}};
    s.gnss_available = gnss;
    s.valid = true;
    return s;
}

}  // namespace

int main() {
    EnuOrigin origin{12.9716, 77.5946, 920.0, true};

    // Coordinate conversion (matches Member 3 spherical approx).
    GeoPosition g{12.9726, 77.5956, 925.0};
    const EnuVector enu = geoToLocalENU(g, origin);
    assert(enu.north_m > 100.0 && enu.north_m < 120.0);
    assert(enu.east_m > 90.0 && enu.east_m < 120.0);
    assert(std::abs(enu.up_m - 5.0) < 1e-9);
    const GeoPosition back = localENUToGeo(enu, origin);
    assert(std::abs(back.latitude_deg - g.latitude_deg) < 1e-9);
    assert(std::abs(back.longitude_deg - g.longitude_deg) < 1e-9);
    double n = 0.0;
    double e = 0.0;
    enuToMember3NorthEast(enu, n, e);
    assert(n == enu.north_m && e == enu.east_m);
    const EnuVector round = member3NorthEastToEnu(n, e, enu.up_m);
    assert(round.east_m == enu.east_m && round.north_m == enu.north_m);

    double ve = 0.0;
    double vn = 0.0;
    vehicleFrameToNavigationEnu(10.0, 0.0, 0.0, ve, vn);
    assert(std::abs(vn - 10.0) < 1e-12 && std::abs(ve) < 1e-12);
    vehicleFrameToNavigationEnu(10.0, 0.0, std::numbers::pi / 2.0, ve, vn);
    assert(std::abs(ve - 10.0) < 1e-12 && std::abs(vn) < 1e-12);
    headingSpeedToEnu(0.0, 20.0, ve, vn);
    assert(std::abs(vn - 20.0) < 1e-12 && std::abs(ve) < 1e-12);
    assert(!validLatitude(100.0) && !validLongitude(200.0));
    assert(finiteNumber(1.0) && !finiteNumber(std::numeric_limits<double>::quiet_NaN()));
    assert(std::abs(wrapPi(3.0 * std::numbers::pi) + std::numbers::pi) < 1e-9 ||
           std::abs(wrapPi(3.0 * std::numbers::pi) - std::numbers::pi) < 1e-9);

    // Timing / age inflation.
    TimestampPair tp{1.0, 1.4, 0.0, 0.0};
    auto timing = evaluateTiming(tp, 0.5, 1.5, 1e-4);
    assert(std::abs(timing.message_age_s - 0.4) < 1e-12);
    assert(!timing.stale);
    tp.receive_time_s = 4.0;
    timing = evaluateTiming(tp, 0.5, 1.5, 1e-4);
    assert(timing.stale);
    assert(ageInflationScale(0.0, 0.2) == 1.0);
    assert(ageInflationScale(0.2, 0.2) > 1.3);

    V2XConfig cfg{};
    cfg.origin_locked = true;
    V2XCore core(cfg);
    core.lockOrigin(origin);

    // NaN / Inf / invalid / empty.
    auto bad = makeCam("r1", 1.0, 12.9716, 77.5946, 0.0, 15.0);
    bad.geo.latitude_deg = std::numeric_limits<double>::quiet_NaN();
    core.ingest(bad);
    bad = makeCam("r1", 1.0, 12.9716, 77.5946, 0.0, 15.0);
    bad.velocity_enu.east_m = std::numeric_limits<double>::infinity();
    core.ingest(bad);
    bad = makeCam("r1", 1.0, 95.0, 77.5946, 0.0, 15.0);
    core.ingest(bad);
    bad = makeCam("r1", 1.0, 12.9716, 77.5946, 0.0, 80.0);
    core.ingest(bad);
    bad = makeCam("", 1.0, 12.9716, 77.5946, 0.0, 15.0);
    core.ingest(bad);
    bad = makeCam("r1", 1.0, 12.9716, 77.5946, 0.0, 15.0);
    bad.declared_pos_std_m = -1.0;
    core.ingest(bad);
    assert(core.remoteVehicles().empty());

    // Valid ingest, duplicate, out-of-order, stale.
    core.ingest(makeCam("r1", 10.0, 12.9717, 77.5946, 0.0, 15.0));
    assert(core.remoteVehicles().size() == 1);
    core.ingest(makeCam("r1", 10.0, 12.9717, 77.5946, 0.0, 15.0));
    assert(core.health().duplicates >= 1);
    core.ingest(makeCam("r1", 9.5, 12.9717, 77.5946, 0.0, 15.0));
    assert(core.health().out_of_order >= 1);
    auto stale = makeCam("r1", 11.0, 12.9717, 77.5946, 0.0, 15.0);
    stale.time.receive_time_s = 20.0;
    core.ingest(stale);
    assert(core.health().stale >= 1);

    // Untrusted security.
    core.reset();
    core.lockOrigin(origin);
    auto untrusted = makeCam("evil", 1.0, 12.9717, 77.5946, 0.0, 15.0);
    untrusted.declared_security = SecurityStatus::Untrusted;
    core.ingest(untrusted);
    assert(core.remoteVehicles().empty());

    // No V2X fallback.
    core.reset();
    core.lockOrigin(origin);
    auto none = core.getCooperativeMeasurement(makeLocal(1.0, 12.9716, 77.5946, false));
    assert(none.decision == GateDecision::Unavailable);
    assert(none.reason == "no_v2x");

    // GNSS-on: snapshot only, no extra GNSS.
    core.reset();
    core.lockOrigin(origin);
    core.ingest(makeCam("lead", 1.0, 12.9718, 77.5946, 0.0, 15.0));
    auto gnss_on = core.getCooperativeMeasurement(makeLocal(1.0, 12.9716, 77.5946, true));
    assert(gnss_on.decision == GateDecision::Unavailable);
    assert(gnss_on.reason == "correlated_with_gnss");

    // GNSS-off after snapshot: relative transfer is observable.
    auto gnss_off = core.getCooperativeMeasurement(makeLocal(2.0, 12.9716, 77.5946, false));
    assert(gnss_off.measurement.has_position);
    assert(gnss_off.decision == GateDecision::Accept ||
           gnss_off.decision == GateDecision::Downweight);
    assert(gnss_off.measurement.kind == CooperativeKind::RelativeTransferPosition ||
           gnss_off.measurement.kind == CooperativeKind::ClusterConsensus);
    assert(gnss_off.measurement.position_cov_ne[0][0] > 0.0);

    // Outlier vehicle should not crash; gating may reject.
    core.ingest(makeCam("outlier", 2.0, 13.05, 77.70, 0.0, 15.0));
    auto gated = core.getCooperativeMeasurement(makeLocal(2.1, 12.9716, 77.5946, false));
    (void)gated;

    // In-memory transport.
    auto mem = std::make_unique<InMemoryV2XTransport>();
    mem->push(makeCam("m1", 3.0, 12.9717, 77.5947, 1.0, 14.0));
    V2XCore core2(cfg);
    core2.lockOrigin(origin);
    core2.setTransport(std::move(mem));
    assert(core2.pollTransport(3.0) == 1);
    assert(core2.remoteVehicles().size() == 1);

    // Simulator determinism.
    SimulatedV2XConfig sc{};
    sc.seed = 7;
    sc.remotes.push_back(SimulatedVehicle{"s1", origin.latitude_deg, origin.longitude_deg, 0.0, 12.0,
                                          0.0, 2.5});
    SimulatedV2XTransport a(sc);
    SimulatedV2XTransport b(sc);
    auto pa = a.poll(1.0);
    auto pb = b.poll(1.0);
    assert(pa.size() == pb.size());
    if (!pa.empty()) {
        assert(std::abs(pa[0].geo.latitude_deg - pb[0].geo.latitude_deg) < 1e-15);
    }

    // Packet loss can yield zero messages.
    sc.packet_loss = 1.0;
    SimulatedV2XTransport lost(sc);
    assert(lost.poll(1.0).empty());

    // Replay JSONL shares ingest path.
    const auto tmp = std::filesystem::temp_directory_path() / "sih26168_v2x_replay.jsonl";
    {
        std::ofstream out(tmp);
        auto m = makeCam("replay1", 4.0, 12.9717, 77.5946, 0.0, 12.0);
        m.source = MessageSource::Replay;
        out << serializeNormalizedJson(m) << "\n";
        out << "{not json\n";
        out << "{\"vehicle_id\":\"bad\",\"latitude_deg\":null}\n";
    }
    ReplayV2XTransport replay(tmp.string());
    assert(replay.ok());
    V2XCore core3(cfg);
    core3.lockOrigin(origin);
    core3.setTransport(std::make_unique<ReplayV2XTransport>(tmp.string()));
    core3.pollTransport(5.0);
    bool found = false;
    for (const auto& rv : core3.remoteVehicles()) {
        if (rv.vehicle_id == "replay1") found = true;
    }
    assert(found);

    // Multi-vehicle tracks.
    core.reset();
    core.lockOrigin(origin);
    core.ingest(makeCam("a", 1.0, 12.9717, 77.5946, 0.0, 15.0));
    core.ingest(makeCam("b", 1.0, 12.97165, 77.59455, 0.2, 14.8));
    core.ingest(makeCam("c", 1.0, 12.97155, 77.59450, -0.1, 15.1));
    assert(core.remoteVehicles().size() == 3);

    // Mahalanobis gating.
    CooperativeMeasurement meas{};
    meas.has_position = true;
    meas.north_m = 0.0;
    meas.east_m = 0.0;
    meas.position_cov_ne = {{{4.0, 0.0}, {0.0, 4.0}}};
    double nis = 0.0;
    std::string reason;
    auto local = makeLocal(1.0, origin.latitude_deg, origin.longitude_deg, false);
    auto d = shouldUseMeasurement(local, origin, meas, cfg, nis, reason);
    assert(d == GateDecision::Accept);
    meas.north_m = 200.0;
    d = shouldUseMeasurement(local, origin, meas, cfg, nis, reason);
    assert(d == GateDecision::Reject);

    // Claimed authenticated is not cryptographic auth.
    MockSecurityProvider mock;
    auto claimed = makeCam("x", 1.0, 12.97, 77.59, 0, 10);
    claimed.declared_security = SecurityStatus::Authenticated;
    std::string sr;
    assert(mock.evaluate(claimed, cfg, sr) == SecurityStatus::Unverified);

    assert(kLibraryStatus.find("SIMULATION") != std::string_view::npos);
    assert(std::string(kAndroidV2XStatus).find("NOT_IMPLEMENTED") != std::string::npos);
    return 0;
}
