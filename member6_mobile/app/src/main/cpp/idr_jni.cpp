#include <jni.h>

#include "idr_engine_api.h"

#include <mutex>

namespace {
std::mutex g_jni_engine;
}  // namespace

extern "C" {

JNIEXPORT jboolean JNICALL
Java_org_sih26168_idr_EngineBridge_nativeInit(JNIEnv* env, jobject, jstring mapPath, jstring onnxPath) {
    std::lock_guard<std::mutex> lock(g_jni_engine);
    const char* map = env->GetStringUTFChars(mapPath, nullptr);
    const char* onnx = env->GetStringUTFChars(onnxPath, nullptr);
    const int ok = idr_engine_init(map, onnx);
    env->ReleaseStringUTFChars(mapPath, map);
    env->ReleaseStringUTFChars(onnxPath, onnx);
    return ok ? JNI_TRUE : JNI_FALSE;
}

JNIEXPORT void JNICALL Java_org_sih26168_idr_EngineBridge_nativeShutdown(JNIEnv*, jobject) {
    std::lock_guard<std::mutex> lock(g_jni_engine);
    idr_engine_shutdown();
}

JNIEXPORT void JNICALL
Java_org_sih26168_idr_EngineBridge_nativeFeedImu(JNIEnv*, jobject, jdouble t, jdouble ax, jdouble ay,
                                                jdouble az, jdouble gx, jdouble gy, jdouble gz) {
    std::lock_guard<std::mutex> lock(g_jni_engine);
    idr_feed_imu(t, ax, ay, az, gx, gy, gz);
}

JNIEXPORT void JNICALL
Java_org_sih26168_idr_EngineBridge_nativeFeedGnss(JNIEnv*, jobject, jdouble t, jdouble lat, jdouble lon,
                                                 jdouble alt, jdouble speedMps, jdouble hdop, jint sats) {
    std::lock_guard<std::mutex> lock(g_jni_engine);
    idr_feed_gnss(t, lat, lon, alt, speedMps, hdop, sats);
}

JNIEXPORT jboolean JNICALL
Java_org_sih26168_idr_EngineBridge_nativePoll(JNIEnv* env, jobject, jdoubleArray out) {
    if (out == nullptr || env->GetArrayLength(out) < 8) {
        return JNI_FALSE;
    }
    std::lock_guard<std::mutex> lock(g_jni_engine);
    IDRNavigationOutput s = idr_get_current_state();
    jdouble buf[8] = {s.timestamp, s.lat, s.lon, s.heading_deg, s.speed_m_s,
                      static_cast<jdouble>(s.is_dead_reckoning), s.confidence,
                      static_cast<jdouble>(idr_is_on_road_network())};
    env->SetDoubleArrayRegion(out, 0, 8, buf);
    return JNI_TRUE;
}

JNIEXPORT jboolean JNICALL
Java_org_sih26168_idr_EngineBridge_nativeSelectMap(JNIEnv*, jobject, jdouble lat, jdouble lon) {
    std::lock_guard<std::mutex> lock(g_jni_engine);
    return idr_select_map_for_location(lat, lon) ? JNI_TRUE : JNI_FALSE;
}

JNIEXPORT jboolean JNICALL Java_org_sih26168_idr_EngineBridge_nativeMapCovers(JNIEnv*, jobject,
                                                                             jdouble lat, jdouble lon) {
    std::lock_guard<std::mutex> lock(g_jni_engine);
    return idr_map_covers_location(lat, lon) ? JNI_TRUE : JNI_FALSE;
}

JNIEXPORT jboolean JNICALL Java_org_sih26168_idr_EngineBridge_nativeSpeedValid(JNIEnv*, jobject) {
    std::lock_guard<std::mutex> lock(g_jni_engine);
    return idr_speed_is_valid() ? JNI_TRUE : JNI_FALSE;
}

JNIEXPORT jstring JNICALL Java_org_sih26168_idr_EngineBridge_nativeSpeedRejectReason(JNIEnv* env, jobject) {
    std::lock_guard<std::mutex> lock(g_jni_engine);
    return env->NewStringUTF(idr_speed_reject_reason());
}

JNIEXPORT jstring JNICALL Java_org_sih26168_idr_EngineBridge_nativeMapStatus(JNIEnv* env, jobject) {
    std::lock_guard<std::mutex> lock(g_jni_engine);
    return env->NewStringUTF(idr_map_status_message());
}

JNIEXPORT jstring JNICALL Java_org_sih26168_idr_EngineBridge_nativeRegionId(JNIEnv* env, jobject) {
    std::lock_guard<std::mutex> lock(g_jni_engine);
    return env->NewStringUTF(idr_active_map_region_id());
}

JNIEXPORT jboolean JNICALL Java_org_sih26168_idr_EngineBridge_nativeOnRoad(JNIEnv*, jobject) {
    std::lock_guard<std::mutex> lock(g_jni_engine);
    return idr_is_on_road_network() ? JNI_TRUE : JNI_FALSE;
}

JNIEXPORT jlong JNICALL Java_org_sih26168_idr_EngineBridge_nativeRoadSegmentId(JNIEnv*, jobject) {
    std::lock_guard<std::mutex> lock(g_jni_engine);
    return static_cast<jlong>(idr_get_road_segment_id());
}

JNIEXPORT jstring JNICALL Java_org_sih26168_idr_EngineBridge_nativeSpeedBackend(JNIEnv* env, jobject) {
    std::lock_guard<std::mutex> lock(g_jni_engine);
    return env->NewStringUTF(idr_engine_speed_backend());
}

JNIEXPORT jstring JNICALL Java_org_sih26168_idr_EngineBridge_nativeLastError(JNIEnv* env, jobject) {
    std::lock_guard<std::mutex> lock(g_jni_engine);
    return env->NewStringUTF(idr_engine_last_error());
}

JNIEXPORT jboolean JNICALL Java_org_sih26168_idr_EngineBridge_nativeIsInitialized(JNIEnv*, jobject) {
    std::lock_guard<std::mutex> lock(g_jni_engine);
    return idr_engine_is_initialized() ? JNI_TRUE : JNI_FALSE;
}

JNIEXPORT jboolean JNICALL
Java_org_sih26168_idr_EngineBridge_nativeDiagnostics(JNIEnv* env, jobject, jdoubleArray out) {
    if (out == nullptr || env->GetArrayLength(out) < 11) {
        return JNI_FALSE;
    }
    std::lock_guard<std::mutex> lock(g_jni_engine);
    IDRDiagnostics d = idr_get_diagnostics();
    jdouble buf[11] = {d.raw_gnss_speed_mps, d.ai_speed_mps, d.ekf_speed_mps, d.displayed_speed_mps,
                       static_cast<jdouble>(d.speed_valid), static_cast<jdouble>(d.map_status),
                       static_cast<jdouble>(d.calibration_status),
                       static_cast<jdouble>(d.last_ai_speed_accepted), d.imu_hz, d.last_imu_timestamp,
                       d.last_gnss_timestamp};
    env->SetDoubleArrayRegion(out, 0, 11, buf);
    return JNI_TRUE;
}

}  // extern "C"
