#include <jni.h>
#include <string>
#include "idr_engine_api.h"

extern "C" JNIEXPORT jint JNICALL
Java_com_example_member6app_native_EngineBridge_init(JNIEnv* env, jobject /* this */, jstring mapPath, jstring modelPath) {
    const char *map_path = mapPath ? env->GetStringUTFChars(mapPath, nullptr) : "";
    const char *model_path = modelPath ? env->GetStringUTFChars(modelPath, nullptr) : "";
    
    int result = idr_engine_init(map_path, model_path);
    
    if (mapPath) env->ReleaseStringUTFChars(mapPath, map_path);
    if (modelPath) env->ReleaseStringUTFChars(modelPath, model_path);
    
    return result;
}

extern "C" JNIEXPORT void JNICALL
Java_com_example_member6app_native_EngineBridge_shutdown(JNIEnv* env, jobject /* this */) {
    idr_engine_shutdown();
}

extern "C" JNIEXPORT void JNICALL
Java_com_example_member6app_native_EngineBridge_feedImu(JNIEnv* env, jobject /* this */,
        jdouble timestamp, jdouble ax, jdouble ay, jdouble az,
        jdouble gx, jdouble gy, jdouble gz) {
    idr_feed_imu(timestamp, ax, ay, az, gx, gy, gz);
}

extern "C" JNIEXPORT void JNICALL
Java_com_example_member6app_native_EngineBridge_feedGnss(JNIEnv* env, jobject /* this */,
        jdouble timestamp, jdouble lat, jdouble lon, jdouble alt,
        jdouble speed, jdouble hdop, jint num_sats) {
    idr_feed_gnss(timestamp, lat, lon, alt, speed, hdop, num_sats);
}

extern "C" JNIEXPORT jobject JNICALL
Java_com_example_member6app_native_EngineBridge_getCurrentState(JNIEnv* env, jobject /* this */) {
    IDRNavigationOutput out = idr_get_current_state();
    
    jclass outputClass = env->FindClass("com/example/member6app/native/IDRNavigationOutput");
    if (outputClass == nullptr) return nullptr;
    
    jmethodID constructor = env->GetMethodID(outputClass, "<init>", "(DDDDDDI)V");
    if (constructor == nullptr) return nullptr;
    
    jobject obj = env->NewObject(outputClass, constructor,
                                 out.timestamp, out.lat, out.lon,
                                 out.heading_deg, out.speed_m_s, out.confidence, out.is_dead_reckoning);
                                 
    return obj;
}

extern "C" JNIEXPORT jstring JNICALL
Java_com_example_member6app_native_EngineBridge_getLastError(JNIEnv* env, jobject /* this */) {
    const char* err = idr_engine_last_error();
    return env->NewStringUTF(err ? err : "");
}
