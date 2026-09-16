#pragma once

#include <string>
#include <utility>

namespace sih26168::member5 {

struct SpeedEstimate {
    float velocity_mps{0.0f};
    float variance_m2s2{0.05f};
    bool valid{false};
};

class ISpeedEstimator {
public:
    virtual ~ISpeedEstimator() = default;
    virtual bool load(const std::string& model_path) = 0;
    /* imu_window: row-major [6, 200] = channel-major 100 Hz aligned IMU. */
    virtual SpeedEstimate predict(const float* imu_window) = 0;
    virtual const char* backendName() const = 0;
};

class MockSpeedEstimator final : public ISpeedEstimator {
public:
    bool load(const std::string&) override;
    SpeedEstimate predict(const float* imu_window) override;
    const char* backendName() const override { return "mock_integrator"; }

private:
    bool have_v_{false};
    float v_mps_{0.0f};
};

#if defined(IDR_WITH_ONNXRUNTIME)
class OnnxSpeedEstimator final : public ISpeedEstimator {
public:
    OnnxSpeedEstimator();
    ~OnnxSpeedEstimator() override;
    bool load(const std::string& model_path) override;
    SpeedEstimate predict(const float* imu_window) override;
    const char* backendName() const override { return "onnxruntime"; }

private:
    struct Impl;
    Impl* impl_{nullptr};
};
#endif

}  // namespace sih26168::member5
