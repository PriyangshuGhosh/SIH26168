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
    /* Clears any persisted internal state (e.g. a stateful estimator's recurrent hidden state).
       Default no-op: only meaningful for a stateful backend (GruStreamingSpeedEstimator). Engine
       calls this on load (fresh estimator, so normally redundant with construction -- kept explicit
       for robustness) and whenever Member 2 reports CalibrationStatus::INVALID (the one condition
       Engine::handleImu already special-cases as a discontinuity). */
    virtual void reset() {}
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

/* Stateful streaming candidate (docs/gru_velocity.md, member1-ml/scripts/train_gru_streaming.py).
   Loads an ONNX graph with two inputs (a single decimated IMU sample [1,1,6] and the previous
   recurrent hidden state [layers,1,hidden]) and four outputs (velocity_mps, velocity_variance_m2s2,
   confidence, the next hidden state) -- e.g.
   member1-ml/experiments/m1_gru_stream2_gru_w20/streaming.onnx. predict() is called by Engine with
   the same raw [T,6] tail-of-window layout as OnnxSpeedEstimator (requiredWindowSamples() stays
   >= 8 so Engine's existing model_T_ clamp is untouched); this estimator uses only the LAST sample
   of that window (the causal "keep the most recent real sample of every N" convention already used
   throughout this codebase -- see docs/production_100hz.md) and feeds it through the recurrent
   graph, carrying hidden state across calls in impl_ until reset(). NOT independently build/test
   verified in the environment this was written in -- see docs/gru_velocity.md "C++ integration"
   before enabling in a real build. */
class GruStreamingSpeedEstimator final : public ISpeedEstimator {
public:
    GruStreamingSpeedEstimator();
    ~GruStreamingSpeedEstimator() override;
    bool load(const std::string& model_path) override;
    SpeedEstimate predict(const float* samples_t6, int n_samples) override;
    int requiredWindowSamples() const override;
    const char* backendName() const override { return "onnxruntime_gru_streaming"; }
    const char* lastError() const override;
    void reset() override;

private:
    struct Impl;
    Impl* impl_{nullptr};
};
#endif

}  // namespace sih26168::member5
