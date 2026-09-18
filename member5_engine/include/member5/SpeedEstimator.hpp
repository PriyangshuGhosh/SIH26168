#pragma once

#include <string>

namespace sih26168::member5 {

struct SpeedEstimate {
    float velocity_mps{0.0f};
    float variance_m2s2{0.05f};
    bool valid{false};
};

/* Member 1 live contract (100 Hz): causal windows of aligned IMU at the
   native IMU rate. Layout [T, 6], channels [ax, ay, az, gx, gy, gz].
   Default T=200 (2 s at 100 Hz). Exported graphs may use [B, T, 6] or
   [B, 6, T]. Uncertainty from ONNX is sigma (m/s) unless named as variance;
   this wrapper converts sigma to variance for Member 3. */
class ISpeedEstimator {
public:
    virtual ~ISpeedEstimator() = default;
    virtual bool load(const std::string& model_path) = 0;
    virtual SpeedEstimate predict(const float* samples_t6, int n_samples) = 0;
    virtual int requiredWindowSamples() const { return 200; }
    virtual const char* backendName() const = 0;
    virtual const char* lastError() const { return ""; }
};

class MockSpeedEstimator final : public ISpeedEstimator {
public:
    bool load(const std::string&) override;
    SpeedEstimate predict(const float* samples_t6, int n_samples) override;
    int requiredWindowSamples() const override { return 200; }
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
    SpeedEstimate predict(const float* samples_t6, int n_samples) override;
    int requiredWindowSamples() const override;
    const char* backendName() const override { return "onnxruntime"; }
    const char* lastError() const override;

private:
    struct Impl;
    Impl* impl_{nullptr};
};
#endif

}  // namespace sih26168::member5
