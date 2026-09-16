#include "member5/SpeedEstimator.hpp"

#include <algorithm>
#include <cmath>

#if defined(IDR_WITH_ONNXRUNTIME)
#include <onnxruntime_cxx_api.h>
#include <memory>
#include <vector>
#endif

namespace sih26168::member5 {

bool MockSpeedEstimator::load(const std::string&) {
    have_v_ = false;
    v_mps_ = 0.0f;
    return true;
}

SpeedEstimate MockSpeedEstimator::predict(const float* imu_window) {
    SpeedEstimate out;
    if (imu_window == nullptr) {
        return out;
    }
    double sum_all = 0.0;
    double sum_tail = 0.0;
    constexpr int kTail = 10;
    for (int i = 0; i < 200; ++i) {
        const double ax = static_cast<double>(imu_window[i]);
        sum_all += ax;
        if (i >= 200 - kTail) {
            sum_tail += ax;
        }
    }
    if (!have_v_) {
        v_mps_ = static_cast<float>(std::max(0.0, (sum_all / 200.0) * 2.0));
        have_v_ = true;
    } else {
        const double ax_tail = sum_tail / static_cast<double>(kTail);
        v_mps_ = static_cast<float>(std::max(0.0, static_cast<double>(v_mps_) + ax_tail * 0.10));
    }
    out.velocity_mps = v_mps_;
    out.variance_m2s2 = 0.05f;
    out.valid = true;
    return out;
}

#if defined(IDR_WITH_ONNXRUNTIME)

struct OnnxSpeedEstimator::Impl {
    Ort::Env env{ORT_LOGGING_LEVEL_WARNING, "idr_speed"};
    Ort::SessionOptions opts;
    std::unique_ptr<Ort::Session> session;
    std::vector<float> input;
    std::array<int64_t, 3> shape{1, 6, 200};
};

OnnxSpeedEstimator::OnnxSpeedEstimator() : impl_(new Impl()) {
    impl_->opts.SetIntraOpNumThreads(1);
    impl_->opts.SetGraphOptimizationLevel(GraphOptimizationLevel::ORT_ENABLE_EXTENDED);
    impl_->input.resize(6 * 200);
}

OnnxSpeedEstimator::~OnnxSpeedEstimator() { delete impl_; }

bool OnnxSpeedEstimator::load(const std::string& model_path) {
    if (model_path.empty()) {
        return false;
    }
    try {
#ifdef _WIN32
        const std::wstring wpath(model_path.begin(), model_path.end());
        impl_->session = std::make_unique<Ort::Session>(impl_->env, wpath.c_str(), impl_->opts);
#else
        impl_->session = std::make_unique<Ort::Session>(impl_->env, model_path.c_str(), impl_->opts);
#endif
        return true;
    } catch (...) {
        impl_->session.reset();
        return false;
    }
}

SpeedEstimate OnnxSpeedEstimator::predict(const float* imu_window) {
    SpeedEstimate out;
    if (impl_->session == nullptr || imu_window == nullptr) {
        return out;
    }
    std::copy(imu_window, imu_window + 6 * 200, impl_->input.begin());
    Ort::MemoryInfo mem = Ort::MemoryInfo::CreateCpu(OrtArenaAllocator, OrtMemTypeDefault);
    Ort::Value tensor = Ort::Value::CreateTensor<float>(mem, impl_->input.data(), impl_->input.size(),
                                                        impl_->shape.data(), impl_->shape.size());
    static const char* in_names[] = {"imu_window"};
    static const char* out_names[] = {"estimated_velocity", "velocity_variance"};
    try {
        auto outputs = impl_->session->Run(Ort::RunOptions{nullptr}, in_names, &tensor, 1, out_names, 2);
        out.velocity_mps = *outputs[0].GetTensorMutableData<float>();
        out.variance_m2s2 = *outputs[1].GetTensorMutableData<float>();
        out.valid = true;
    } catch (...) {
        out.valid = false;
    }
    return out;
}

#endif

}  // namespace sih26168::member5
