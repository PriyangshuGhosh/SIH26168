#include "member5/SpeedEstimator.hpp"

#include <algorithm>
#include <cmath>
#include <cstring>
#include <string>
#include <vector>

#if defined(IDR_WITH_ONNXRUNTIME)
#include <onnxruntime_cxx_api.h>
#include <memory>
#endif

namespace sih26168::member5 {

bool MockSpeedEstimator::load(const std::string&) {
    have_v_ = false;
    v_mps_ = 0.0f;
    return true;
}

SpeedEstimate MockSpeedEstimator::predict(const float* samples_t6, int n_samples) {
    SpeedEstimate out;
    if (samples_t6 == nullptr || n_samples <= 0) {
        return out;
    }
    /* samples_t6's accelerometer channels are Member 2's AlignedIMUFrame values verbatim, i.e.
       already m/s^2 (Engine::handleImu no longer rescales them -- see the unit note there). */
    double tail_ax_mps2 = 0.0;
    double sum_gyro = 0.0;
    const int tail = std::min(n_samples, 5);
    for (int i = 0; i < n_samples; ++i) {
        const double ax_mps2 = static_cast<double>(samples_t6[i * 6 + 0]);
        sum_gyro += std::abs(static_cast<double>(samples_t6[i * 6 + 5]));
        if (i >= n_samples - tail) {
            tail_ax_mps2 += ax_mps2;
        }
    }
    constexpr double kInferDt = 0.10; /* engine stride 10 at 100 Hz */
    const double mean_gyro = sum_gyro / n_samples;
    const double ax_tail_mps2 = tail_ax_mps2 / static_cast<double>(tail);
    /* ~0.8 m/s²: separates standstill/cruise coast from meaningful accel/brake. */
    const bool quasi_static = std::abs(ax_tail_mps2) < 0.8 && mean_gyro < 0.15;
    if (quasi_static) {
        if (!have_v_) {
            v_mps_ = 0.0f;
            have_v_ = true;
        }
    } else if (!have_v_) {
        v_mps_ = static_cast<float>(std::max(0.0, ax_tail_mps2 * kInferDt));
        have_v_ = true;
    } else {
        v_mps_ = static_cast<float>(
            std::max(0.0, static_cast<double>(v_mps_) + ax_tail_mps2 * kInferDt));
    }
    out.velocity_mps = v_mps_;
    out.variance_m2s2 = 0.05f;
    out.valid = true;
    return out;
}

#if defined(IDR_WITH_ONNXRUNTIME)

namespace {

std::string lowerCopy(std::string s) {
    for (char& c : s) {
        if (c >= 'A' && c <= 'Z') {
            c = static_cast<char>(c - 'A' + 'a');
        }
    }
    return s;
}

bool nameIs(const std::string& n, const char* a) { return lowerCopy(n) == a; }

/* Substring match: Member 1's real production output is "velocity_variance_m2s2"
   (member1-ml/src/inference/export_onnx.py::OUTPUT_NAMES_UNCERTAINTY), which is not exactly
   "velocity_variance" or "variance" -- an exact-match check would silently miss it and fall back
   to the hardcoded default variance below, discarding Member 1's real uncertainty output. */
bool nameContains(const std::string& n, const char* needle) {
    return lowerCopy(n).find(needle) != std::string::npos;
}

}  // namespace

struct OnnxSpeedEstimator::Impl {
    Ort::Env env{ORT_LOGGING_LEVEL_WARNING, "idr_speed"};
    Ort::SessionOptions opts;
    std::unique_ptr<Ort::Session> session;
    std::vector<float> input;
    std::vector<int64_t> shape;
    bool time_major{true}; /* [B, T, 6] vs [B, 6, T] */
    int T{200};
    int C{6};
    std::string input_name{"imu_window"};
    std::vector<std::string> output_names;
    std::string last_error;
};

OnnxSpeedEstimator::OnnxSpeedEstimator() : impl_(new Impl()) {
    impl_->opts.SetIntraOpNumThreads(1);
    impl_->opts.SetGraphOptimizationLevel(GraphOptimizationLevel::ORT_ENABLE_EXTENDED);
}

OnnxSpeedEstimator::~OnnxSpeedEstimator() { delete impl_; }

int OnnxSpeedEstimator::requiredWindowSamples() const {
    return impl_ != nullptr ? impl_->T : 200;
}

const char* OnnxSpeedEstimator::lastError() const {
    return impl_ != nullptr ? impl_->last_error.c_str() : "";
}

bool OnnxSpeedEstimator::load(const std::string& model_path) {
    impl_->last_error.clear();
    impl_->session.reset();
    if (model_path.empty()) {
        impl_->last_error = "empty ONNX path";
        return false;
    }
    try {
#ifdef _WIN32
        const std::wstring wpath(model_path.begin(), model_path.end());
        impl_->session = std::make_unique<Ort::Session>(impl_->env, wpath.c_str(), impl_->opts);
#else
        impl_->session = std::make_unique<Ort::Session>(impl_->env, model_path.c_str(), impl_->opts);
#endif
        if (impl_->session->GetInputCount() < 1) {
            impl_->last_error = "ONNX model has no inputs";
            impl_->session.reset();
            return false;
        }
        Ort::AllocatorWithDefaultOptions alloc;
        {
            auto in_name = impl_->session->GetInputNameAllocated(0, alloc);
            impl_->input_name = in_name.get();
        }
        auto type_info = impl_->session->GetInputTypeInfo(0);
        auto tinfo = type_info.GetTensorTypeAndShapeInfo();
        auto dims = tinfo.GetShape();
        if (dims.size() != 3) {
            impl_->last_error =
                "ONNX input rank must be 3 ([B,T,6] Member 1 layout, or [B,6,T])";
            impl_->session.reset();
            return false;
        }
        const int64_t d1 = dims[1];
        const int64_t d2 = dims[2];
        if (d2 == 6 || d2 == -1) {
            impl_->time_major = true;
            impl_->C = 6;
            impl_->T = (d1 > 0) ? static_cast<int>(d1) : 200;
        } else if (d1 == 6) {
            impl_->time_major = false;
            impl_->C = 6;
            impl_->T = (d2 > 0) ? static_cast<int>(d2) : 200;
        } else {
            impl_->last_error = "ONNX input must have a channel axis of size 6";
            impl_->session.reset();
            return false;
        }
        if (impl_->T < 8 || impl_->T > 400) {
            impl_->last_error = "ONNX window T out of range (100 Hz live: typically 200 = 2 s)";
            impl_->session.reset();
            return false;
        }
        impl_->shape = {1, impl_->time_major ? impl_->T : impl_->C,
                        impl_->time_major ? impl_->C : impl_->T};
        impl_->input.assign(static_cast<std::size_t>(impl_->T * impl_->C), 0.0f);

        impl_->output_names.clear();
        const std::size_t nout = impl_->session->GetOutputCount();
        if (nout < 1) {
            impl_->last_error = "ONNX model has no outputs";
            impl_->session.reset();
            return false;
        }
        for (std::size_t i = 0; i < nout; ++i) {
            auto on = impl_->session->GetOutputNameAllocated(i, alloc);
            impl_->output_names.emplace_back(on.get());
        }
        return true;
    } catch (const Ort::Exception& ex) {
        impl_->last_error = std::string("ONNX load failed: ") + ex.what();
        impl_->session.reset();
        return false;
    } catch (...) {
        impl_->last_error = "ONNX load failed (unknown exception)";
        impl_->session.reset();
        return false;
    }
}

SpeedEstimate OnnxSpeedEstimator::predict(const float* samples_t6, int n_samples) {
    SpeedEstimate out;
    if (impl_->session == nullptr || samples_t6 == nullptr || n_samples <= 0) {
        return out;
    }
    const int T = impl_->T;
    const int use = std::min(n_samples, T);
    const int src0 = std::max(0, n_samples - use);
    std::fill(impl_->input.begin(), impl_->input.end(), 0.0f);
    for (int i = 0; i < use; ++i) {
        const float* row = samples_t6 + (src0 + i) * 6;
        const int dst_t = T - use + i;
        if (impl_->time_major) {
            std::memcpy(impl_->input.data() + dst_t * 6, row, 6 * sizeof(float));
        } else {
            for (int c = 0; c < 6; ++c) {
                impl_->input[static_cast<std::size_t>(c * T + dst_t)] = row[c];
            }
        }
    }

    Ort::MemoryInfo mem = Ort::MemoryInfo::CreateCpu(OrtArenaAllocator, OrtMemTypeDefault);
    Ort::Value tensor = Ort::Value::CreateTensor<float>(mem, impl_->input.data(), impl_->input.size(),
                                                        impl_->shape.data(), impl_->shape.size());
    std::vector<const char*> in_names{impl_->input_name.c_str()};
    std::vector<const char*> out_names;
    out_names.reserve(impl_->output_names.size());
    for (const auto& n : impl_->output_names) {
        out_names.push_back(n.c_str());
    }
    try {
        auto outputs = impl_->session->Run(Ort::RunOptions{nullptr}, in_names.data(), &tensor, 1,
                                           out_names.data(), out_names.size());
        float vel = 0.0f;
        float sigma = -1.0f;
        float var = -1.0f;
        bool have_vel = false;
        for (std::size_t i = 0; i < outputs.size(); ++i) {
            const float v = *outputs[i].GetTensorData<float>();
            const std::string& nm = impl_->output_names[i];
            if (nameIs(nm, "velocity_mps") || nameIs(nm, "estimated_velocity")) {
                vel = v;
                have_vel = true;
            } else if (nameIs(nm, "uncertainty")) {
                sigma = v;
            } else if (nameContains(nm, "variance")) {
                var = v;
            }
        }
        if (!have_vel && !outputs.empty()) {
            vel = *outputs[0].GetTensorData<float>();
            have_vel = true;
            if (outputs.size() > 1 && var < 0.0f && sigma < 0.0f) {
                /* Ambiguous second output: treat as sigma if name unknown. */
                sigma = *outputs[1].GetTensorData<float>();
            }
        }
        if (!have_vel || !std::isfinite(vel) || vel < 0.0f) {
            return out;
        }
        out.velocity_mps = vel;
        if (var > 0.0f && std::isfinite(var)) {
            out.variance_m2s2 = var;
        } else if (sigma > 0.0f && std::isfinite(sigma)) {
            out.variance_m2s2 = sigma * sigma;
        } else {
            out.variance_m2s2 = 0.05f;
        }
        out.valid = true;
    } catch (...) {
        out.valid = false;
    }
    return out;
}

#endif

}  // namespace sih26168::member5
