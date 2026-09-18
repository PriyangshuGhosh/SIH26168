#include <jni.h>

#include "idr_engine_api.h"

extern "C" {

JNIEXPORT jboolean JNICALL
Java_org_sih26168_idr_EngineBridge_nativeInit(JNIEnv* env, jobject, jstring mapPath, jstring onnxPath) {
    const char* map = env->GetStringUTFChars(mapPath, nullptr);
    const char* onnx = env->GetStringUTFChars(onnxPath, nullptr);
    const int ok = idr_engine_init(map, onnx);
    env->ReleaseStringUTFChars(mapPath, map);
    env->ReleaseStringUTFChars(onnxPath, onnx);
    return ok ? JNI_TRUE : JNI_FALSE;
}

JNIEXPORT void JNICALL Java_org_sih26168_idr_EngineBridge_nativeShutdown(JNIEnv*, jobject) {
    idr_engine_shutdown();
}

JNIEXPORT void JNICALL
Java_org_sih26168_idr_EngineBridge_nativeFeedImu(JNIEnv*, jobject, jdouble t, jdouble ax, jdouble ay,
                                                jdouble az, jdouble gx, jdouble gy, jdouble gz) {
    idr_feed_imu(t, ax, ay, az, gx, gy, gz);
}

JNIEXPORT void JNICALL
Java_org_sih26168_idr_EngineBridge_nativeFeedGnss(JNIEnv*, jobject, jdouble t, jdouble lat, jdouble lon,
                                                 jdouble alt, jdouble speedMps, jdouble hdop, jint sats) {
    idr_feed_gnss(t, lat, lon, alt, speedMps, hdop, sats);
}

JNIEXPORT jboolean JNICALL
Java_org_sih26168_idr_EngineBridge_nativePoll(JNIEnv* env, jobject, jdoubleArray out) {
    if (out == nullptr || env->GetArrayLength(out) < 7) {
        return JNI_FALSE;
    }
    IDRNavigationOutput s = idr_get_current_state();
    jdouble buf[7] = {s.timestamp, s.lat, s.lon, s.heading_deg, s.speed_m_s,
                      static_cast<jdouble>(s.is_dead_reckoning), s.confidence};
    env->SetDoubleArrayRegion(out, 0, 7, buf);
    return JNI_TRUE;
}

JNIEXPORT jboolean JNICALL
Java_org_sih26168_idr_EngineBridge_nativeSelectMap(JNIEnv*, jobject, jdouble lat, jdouble lon) {
    return idr_select_map_for_location(lat, lon) ? JNI_TRUE : JNI_FALSE;
}

JNIEXPORT jboolean JNICALL Java_org_sih26168_idr_EngineBridge_nativeSpeedValid(JNIEnv*, jobject) {
    return idr_speed_is_valid() ? JNI_TRUE : JNI_FALSE;
}

JNIEXPORT jstring JNICALL Java_org_sih26168_idr_EngineBridge_nativeSpeedRejectReason(JNIEnv* env, jobject) {
    return env->NewStringUTF(idr_speed_reject_reason());
}

JNIEXPORT jstring JNICALL Java_org_sih26168_idr_EngineBridge_nativeMapStatus(JNIEnv* env, jobject) {
    return env->NewStringUTF(idr_map_status_message());
}

JNIEXPORT jstring JNICALL Java_org_sih26168_idr_EngineBridge_nativeRegionId(JNIEnv* env, jobject) {
    return env->NewStringUTF(idr_active_map_region_id());
}

JNIEXPORT jboolean JNICALL Java_org_sih26168_idr_EngineBridge_nativeOnRoad(JNIEnv*, jobject) {
    return idr_is_on_road_network() ? JNI_TRUE : JNI_FALSE;
}

JNIEXPORT jboolean JNICALL
Java_org_sih26168_idr_EngineBridge_nativeDiagnostics(JNIEnv* env, jobject, jdoubleArray out) {
    if (out == nullptr || env->GetArrayLength(out) < 9) {
        return JNI_FALSE;
    }
    IDRDiagnostics d = idr_get_diagnostics();
    jdouble buf[9] = {d.raw_gnss_speed_mps, d.ai_speed_mps, d.ekf_speed_mps, d.displayed_speed_mps,
                      static_cast<jdouble>(d.speed_valid), static_cast<jdouble>(d.map_status),
                      static_cast<jdouble>(d.calibration_status), static_cast<jdouble>(d.last_ai_speed_accepted),
                      d.imu_hz};
    env->SetDoubleArrayRegion(out, 0, 9, buf);
    return JNI_TRUE;
}

}  // extern "C"
