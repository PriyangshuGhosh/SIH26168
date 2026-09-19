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

/* Extra diagnostics. Does not change IDRNavigationOutput layout. */
typedef struct {
    double raw_gnss_speed_mps;
    double ai_speed_mps;
    double ekf_speed_mps;
    double displayed_speed_mps;
    int speed_valid; /* 1 = speed_m_s is a trusted estimate */
    int map_status;  /* 0 unknown, 1 in-region, 2 out-of-region, 3 no package */
    int calibration_status;
    int last_ai_speed_accepted;
    double imu_hz;
    double last_imu_timestamp;
    double last_gnss_timestamp;
} IDRDiagnostics;

/* Returns 1 on success, 0 on failure. */
IDR_API int idr_engine_init(const char* map_db_path, const char* onnx_model_path);
IDR_API void idr_engine_shutdown(void);

IDR_API void idr_feed_imu(double timestamp, double ax, double ay, double az, double gx, double gy,
                          double gz);
/* `speed` is m/s, or NaN when the receiver reports no speed (never 0.0 for "unknown":
   0.0 is a real stationary speed measurement). */
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

/* Map region selection (offline catalog / single roadpack). 1 = in region. */
IDR_API int idr_select_map_for_location(double lat, double lon);
IDR_API int idr_map_covers_location(double lat, double lon);
IDR_API const char* idr_active_map_region_id(void);
IDR_API const char* idr_map_status_message(void);

IDR_API int idr_speed_is_valid(void);
IDR_API const char* idr_speed_reject_reason(void);
IDR_API IDRDiagnostics idr_get_diagnostics(void);

#ifdef __cplusplus
}
#endif

#endif /* IDR_ENGINE_API_H */
