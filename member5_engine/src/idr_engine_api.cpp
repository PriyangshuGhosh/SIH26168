#define IDR_ENGINE_EXPORTS
#include "idr_engine_api.h"
#include "member5/Engine.hpp"

#include <atomic>
#include <mutex>
#include <string>

namespace {

std::mutex g_lifecycle;
std::atomic<sih26168::member5::Engine*> g_engine{nullptr};
std::string g_last_error;

void setError(const char* msg) { g_last_error = msg ? msg : ""; }

void destroyEngineUnlocked() {
    sih26168::member5::Engine* e = g_engine.exchange(nullptr, std::memory_order_acq_rel);
    delete e;
}

}  // namespace

int idr_engine_init(const char* map_db_path, const char* onnx_model_path) {
    try {
        std::lock_guard<std::mutex> lock(g_lifecycle);
        destroyEngineUnlocked();
        auto* engine = new sih26168::member5::Engine();
        if (!engine->start(map_db_path, onnx_model_path)) {
            delete engine;
            setError("engine start failed");
            return 0;
        }
        g_engine.store(engine, std::memory_order_release);
        setError("");
        return 1;
    } catch (const std::exception& ex) {
        setError(ex.what());
        return 0;
    } catch (...) {
        setError("unknown init failure");
        return 0;
    }
}

void idr_engine_shutdown(void) {
    std::lock_guard<std::mutex> lock(g_lifecycle);
    destroyEngineUnlocked();
}

void idr_feed_imu(double timestamp, double ax, double ay, double az, double gx, double gy, double gz) {
    sih26168::member5::Engine* e = g_engine.load(std::memory_order_acquire);
    if (e == nullptr) {
        return;
    }
    sih26168::member5::ImuSample s{timestamp, ax, ay, az, gx, gy, gz};
    e->feedImu(s);
}

void idr_feed_gnss(double timestamp, double lat, double lon, double alt, double speed, double hdop,
                   int num_sats) {
    sih26168::member5::Engine* e = g_engine.load(std::memory_order_acquire);
    if (e == nullptr) {
        return;
    }
    sih26168::member5::GnssSample s{timestamp, lat, lon, alt, speed, hdop, num_sats};
    e->feedGnss(s);
}

IDRNavigationOutput idr_get_current_state(void) {
    sih26168::member5::Engine* e = g_engine.load(std::memory_order_acquire);
    if (e == nullptr) {
        IDRNavigationOutput empty{};
        return empty;
    }
    return e->currentState();
}

const char* idr_engine_last_error(void) { return g_last_error.c_str(); }

int idr_engine_is_initialized(void) {
    return g_engine.load(std::memory_order_acquire) != nullptr ? 1 : 0;
}
