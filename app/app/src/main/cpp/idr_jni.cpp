#include <jni.h>
#include "idr_engine_api.h"

extern "C" {

JNIEXPORT jint JNICALL
Java_com_example_member6app_native_EngineBridge_init(JNIEnv* env, jobject, jstring mapPath,
                                                     jstring modelPath) {
    const char* map_path = mapPath ? env->GetStringUTFChars(mapPath, nullptr) : "";
    const char* model_path = modelPath ? env->GetStringUTFChars(modelPath, nullptr) : "";
    const int result = idr_engine_init(map_path, model_path);
    if (mapPath) env->ReleaseStringUTFChars(mapPath, map_path);
    if (modelPath) env->ReleaseStringUTFChars(modelPath, model_path);
    return result;
}

JNIEXPORT void JNICALL Java_com_example_member6app_native_EngineBridge_shutdown(JNIEnv*, jobject) {
    idr_engine_shutdown();
}

JNIEXPORT void JNICALL
Java_com_example_member6app_native_EngineBridge_feedImu(JNIEnv*, jobject, jdouble timestamp,
                                                       jdouble ax, jdouble ay, jdouble az, jdouble gx,
                                                       jdouble gy, jdouble gz) {
    idr_feed_imu(timestamp, ax, ay, az, gx, gy, gz);
}

JNIEXPORT void JNICALL
Java_com_example_member6app_native_EngineBridge_feedGnss(JNIEnv*, jobject, jdouble timestamp,
                                                        jdouble lat, jdouble lon, jdouble alt,
                                                        jdouble speed, jdouble hdop, jint num_sats) {
    idr_feed_gnss(timestamp, lat, lon, alt, speed, hdop, num_sats);
}

JNIEXPORT jobject JNICALL
Java_com_example_member6app_native_EngineBridge_getCurrentState(JNIEnv* env, jobject) {
    IDRNavigationOutput out = idr_get_current_state();
    jclass outputClass = env->FindClass("com/example/member6app/native/IDRNavigationOutput");
    if (outputClass == nullptr) return nullptr;
    jmethodID constructor = env->GetMethodID(outputClass, "<init>", "(DDDDDDI)V");
    if (constructor == nullptr) return nullptr;
    return env->NewObject(outputClass, constructor, out.timestamp, out.lat, out.lon, out.heading_deg,
                          out.speed_m_s, out.confidence, out.is_dead_reckoning);
}

JNIEXPORT jstring JNICALL
Java_com_example_member6app_native_EngineBridge_getLastError(JNIEnv* env, jobject) {
    const char* err = idr_engine_last_error();
    return env->NewStringUTF(err ? err : "");
}

JNIEXPORT jboolean JNICALL
Java_com_example_member6app_native_EngineBridge_selectMap(JNIEnv*, jobject, jdouble lat, jdouble lon) {
    return idr_select_map_for_location(lat, lon) ? JNI_TRUE : JNI_FALSE;
}

JNIEXPORT jboolean JNICALL Java_com_example_member6app_native_EngineBridge_speedValid(JNIEnv*,
                                                                                    jobject) {
    return idr_speed_is_valid() ? JNI_TRUE : JNI_FALSE;
}

JNIEXPORT jstring JNICALL
Java_com_example_member6app_native_EngineBridge_speedRejectReason(JNIEnv* env, jobject) {
    return env->NewStringUTF(idr_speed_reject_reason());
}

JNIEXPORT jstring JNICALL Java_com_example_member6app_native_EngineBridge_mapStatus(JNIEnv* env,
                                                                                 jobject) {
    return env->NewStringUTF(idr_map_status_message());
}

JNIEXPORT jstring JNICALL Java_com_example_member6app_native_EngineBridge_regionId(JNIEnv* env,
                                                                                jobject) {
    return env->NewStringUTF(idr_active_map_region_id());
}

JNIEXPORT jboolean JNICALL
Java_com_example_member6app_native_EngineBridge_diagnostics(JNIEnv* env, jobject, jdoubleArray out) {
    if (out == nullptr || env->GetArrayLength(out) < 11) {
        return JNI_FALSE;
    }
    IDRDiagnostics d = idr_get_diagnostics();
    jdouble buf[11] = {d.raw_gnss_speed_mps,
                       d.ai_speed_mps,
                       d.ekf_speed_mps,
                       d.displayed_speed_mps,
                       static_cast<jdouble>(d.speed_valid),
                       static_cast<jdouble>(d.map_status),
                       static_cast<jdouble>(d.calibration_status),
                       static_cast<jdouble>(d.last_ai_speed_accepted),
                       d.imu_hz,
                       static_cast<jdouble>(d.gnss_quality),
                       static_cast<jdouble>(d.simulation)};
    env->SetDoubleArrayRegion(out, 0, 11, buf);
    return JNI_TRUE;
}

JNIEXPORT void JNICALL
Java_com_example_member6app_native_EngineBridge_setSimulation(JNIEnv*, jobject, jboolean enabled) {
    idr_engine_set_simulation(enabled ? 1 : 0);
}

JNIEXPORT jboolean JNICALL Java_com_example_member6app_native_EngineBridge_isSimulation(JNIEnv*,
                                                                                     jobject) {
    return idr_engine_is_simulation() ? JNI_TRUE : JNI_FALSE;
}

}  // extern "C"
