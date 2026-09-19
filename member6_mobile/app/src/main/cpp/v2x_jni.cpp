#include <jni.h>

#include "sih26168/v2x/android_adapter.hpp"
#include "sih26168/v2x/v2x.hpp"

#include <memory>
#include <mutex>
#include <string>
#include <vector>

namespace {
std::mutex g_v2x;
std::unique_ptr<sih26168::v2x::V2XCore> g_core;
std::vector<sih26168::v2x::RemoteVehicleState> g_remotes;
sih26168::v2x::CooperativeMeasurementResult g_coop{};
sih26168::v2x::HealthStatus g_health{};
}  // namespace

extern "C" {

JNIEXPORT jstring JNICALL Java_org_sih26168_idr_V2vBridge_nativeLibraryStatus(JNIEnv* env, jobject) {
    return env->NewStringUTF(std::string(sih26168::v2x::kLibraryStatus).c_str());
}

JNIEXPORT jstring JNICALL Java_org_sih26168_idr_V2vBridge_nativeAndroidAdapterStatus(JNIEnv* env, jobject) {
    return env->NewStringUTF(sih26168::v2x::kAndroidV2XStatus);
}

JNIEXPORT jboolean JNICALL
Java_org_sih26168_idr_V2vBridge_nativeStartSimulated(JNIEnv* env, jobject, jdouble lat, jdouble lon) {
    std::lock_guard<std::mutex> lock(g_v2x);
    sih26168::v2x::V2XConfig cfg{};
    cfg.origin_locked = true;
    g_core = std::make_unique<sih26168::v2x::V2XCore>(cfg);
    g_core->lockOrigin(sih26168::v2x::EnuOrigin{lat, lon, 0.0, true});
    sih26168::v2x::SimulatedV2XConfig sc{};
    sc.origin_lat_deg = lat;
    sc.origin_lon_deg = lon;
    sc.remotes.push_back({"lead_sim", lat + 0.00018, lon, 0.0, 16.0, 0.0, 3.0});
    sc.remotes.push_back({"trail_sim", lat - 0.00012, lon + 0.00008, 1.2, 12.0, 0.0, 4.0});
    g_core->setTransport(sih26168::v2x::makeSimulatedTransport(sc));
    g_remotes.clear();
    return JNI_TRUE;
}

JNIEXPORT void JNICALL Java_org_sih26168_idr_V2vBridge_nativeStop(JNIEnv*, jobject) {
    std::lock_guard<std::mutex> lock(g_v2x);
    g_core.reset();
    g_remotes.clear();
}

JNIEXPORT void JNICALL Java_org_sih26168_idr_V2vBridge_nativePoll(JNIEnv*, jobject, jdouble nowS) {
    std::lock_guard<std::mutex> lock(g_v2x);
    if (!g_core) {
        return;
    }
    g_core->pollTransport(nowS);
    g_remotes = g_core->remoteVehicles();
    g_health = g_core->health();
}

JNIEXPORT void JNICALL Java_org_sih26168_idr_V2vBridge_nativeUpdateLocal(
    JNIEnv*, jobject, jdouble t, jdouble lat, jdouble lon, jdouble vx, jdouble vy, jdouble yawRad,
    jboolean gnssAvailable) {
    std::lock_guard<std::mutex> lock(g_v2x);
    if (!g_core) {
        return;
    }
    sih26168::v2x::LocalNavigationState local{};
    local.timestamp_s = t;
    local.latitude_deg = lat;
    local.longitude_deg = lon;
    local.v_x = vx;
    local.v_y = vy;
    local.yaw_rad = yawRad;
    local.gnss_available = gnssAvailable == JNI_TRUE;
    local.valid = true;
    g_coop = g_core->getCooperativeMeasurement(local);
}

JNIEXPORT jint JNICALL Java_org_sih26168_idr_V2vBridge_nativeRemoteCount(JNIEnv*, jobject) {
    std::lock_guard<std::mutex> lock(g_v2x);
    return static_cast<jint>(g_remotes.size());
}

JNIEXPORT jstring JNICALL
Java_org_sih26168_idr_V2vBridge_nativeCopyRemote(JNIEnv* env, jobject, jint index, jdoubleArray out) {
    std::lock_guard<std::mutex> lock(g_v2x);
    if (index < 0 || static_cast<size_t>(index) >= g_remotes.size() || out == nullptr ||
        env->GetArrayLength(out) < 8) {
        return env->NewStringUTF("");
    }
    const auto& r = g_remotes[static_cast<size_t>(index)];
    jdouble buf[8] = {r.geo.latitude_deg, r.geo.longitude_deg, r.heading_rad, r.velocity_enu.east_m,
                      r.velocity_enu.north_m, r.age_s, r.pos_std_m, r.usable ? 1.0 : 0.0};
    env->SetDoubleArrayRegion(out, 0, 8, buf);
    return env->NewStringUTF(r.vehicle_id.c_str());
}

JNIEXPORT jstring JNICALL
Java_org_sih26168_idr_V2vBridge_nativeCoop(JNIEnv* env, jobject, jdoubleArray out) {
    std::lock_guard<std::mutex> lock(g_v2x);
    if (out == nullptr || env->GetArrayLength(out) < 6) {
        return env->NewStringUTF("unavailable");
    }
    jdouble buf[6] = {static_cast<jdouble>(g_coop.decision),
                      g_coop.nis,
                      static_cast<jdouble>(g_coop.measurement.contributing_vehicles),
                      g_coop.measurement.north_m,
                      g_coop.measurement.east_m,
                      g_coop.measurement.age_s};
    env->SetDoubleArrayRegion(out, 0, 6, buf);
    return env->NewStringUTF(g_coop.reason.c_str());
}

JNIEXPORT jstring JNICALL Java_org_sih26168_idr_V2vBridge_nativeHealth(JNIEnv* env, jobject, jlongArray out) {
    std::lock_guard<std::mutex> lock(g_v2x);
    if (out != nullptr && env->GetArrayLength(out) >= 7) {
        jlong buf[7] = {static_cast<jlong>(g_health.received),
                        static_cast<jlong>(g_health.validated),
                        static_cast<jlong>(g_health.rejected),
                        static_cast<jlong>(g_health.stale),
                        static_cast<jlong>(g_health.duplicates),
                        static_cast<jlong>(g_health.out_of_order),
                        static_cast<jlong>(g_health.tracked_vehicles)};
        env->SetLongArrayRegion(out, 0, 7, buf);
    }
    return env->NewStringUTF(g_health.transport_name.c_str());
}

}  // extern "C"
