#ifndef IDR_ENGINE_API_H
#define IDR_ENGINE_API_H

#ifdef __cplusplus
extern "C" {
#endif

#if defined(IDR_ENGINE_STATIC)
#define IDR_API
#elif defined(_WIN32)
#if defined(IDR_ENGINE_EXPORTS)
#define IDR_API __declspec(dllexport)
#else
#define IDR_API __declspec(dllimport)
#endif
#else
#define IDR_API __attribute__((visibility("default")))
#endif

typedef struct {
    double timestamp;
    double lat, lon;
    double heading_deg;
    double speed_m_s;
    int is_dead_reckoning; /* 0 = GNSS-aided, 1 = pure dead reckoning */
    double confidence;
} IDRNavigationOutput;

/* Returns 1 on success, 0 on failure. */
IDR_API int idr_engine_init(const char* map_db_path, const char* onnx_model_path);
IDR_API void idr_engine_shutdown(void);

IDR_API void idr_feed_imu(double timestamp, double ax, double ay, double az, double gx, double gy,
                          double gz);
IDR_API void idr_feed_gnss(double timestamp, double lat, double lon, double alt, double speed,
                           double hdop, int num_sats);

/* Polled by the mobile UI at ~10 Hz. */
IDR_API IDRNavigationOutput idr_get_current_state(void);

/* Diagnostics (stable extras; Member 6 may ignore). Struct layout of
   IDRNavigationOutput is unchanged so existing FFI stays valid.
   Matched lat/lon/heading/confidence are in idr_get_current_state(). */
IDR_API const char* idr_engine_last_error(void);
IDR_API int idr_engine_is_initialized(void);
IDR_API long long idr_get_road_segment_id(void);
IDR_API int idr_is_on_road_network(void);
IDR_API const char* idr_engine_speed_backend(void);

#ifdef __cplusplus
}
#endif

#endif /* IDR_ENGINE_API_H */
