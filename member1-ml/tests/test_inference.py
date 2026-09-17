from __future__ import annotations

import numpy as np
import pytest

torch = pytest.importorskip("torch", reason="PyTorch is required for the inference contract tests")

from conftest import SPLIT_RULES  # noqa: E402
from src.data.dataset import from_arrays  # noqa: E402
from src.data.splits import make_split  # noqa: E402
from src.data.windowing import window_end_indices  # noqa: E402
from src.inference.predict import predict_contract  # noqa: E402
from src.models.tcn_velocity import build_model, fit_normalization  # noqa: E402

CPU = torch.device("cpu")
MODEL_CFG = {"channels": 8, "kernel_size": 3, "n_blocks": 3, "dropout": 0.1}


@pytest.fixture
def train_val(arrays):
    ds = from_arrays(arrays)
    split = make_split(ds.trip_id, ds.session_id, SPLIT_RULES)
    tr, va = ds.subset(split.masks["train"]), ds.subset(split.masks["val"])
    return tr, va, window_end_indices(tr, 20, 5), window_end_indices(va, 20, 1)


def _point_model(train_val):
    tr, _, e_tr, _ = train_val
    model = build_model("cnn", MODEL_CFG).eval()
    model.set_normalization(*fit_normalization(tr.imu, tr.target[e_tr].astype(np.float64)))
    return model


def _uncertainty_model(train_val):
    tr, _, e_tr, _ = train_val
    model = build_model("cnn", {**MODEL_CFG, "uncertainty": True}).eval()
    model.set_normalization(*fit_normalization(tr.imu, tr.target[e_tr].astype(np.float64)))
    model.set_confidence_reference(2.0)
    return model


def _uncertainty_magnitude_model(train_val):
    """cnn_mag production model: same as _uncertainty_model but with derive_magnitude_channels."""
    tr, _, e_tr, _ = train_val
    cfg = {**MODEL_CFG, "uncertainty": True, "derive_magnitude_channels": True}
    model = build_model("cnn_mag", cfg).eval()
    model.set_normalization(*fit_normalization(tr.imu, tr.target[e_tr].astype(np.float64), derive_magnitude_channels=True))
    model.set_confidence_reference(2.0)
    return model


def test_point_model_contract_has_none_uncertainty_and_confidence(train_val):
    tr, va, e_tr, e_va = train_val
    model = _point_model(train_val)
    ts = va.t_session_s[e_va]
    records = predict_contract(model, va.imu, e_va, 20, ts, device=CPU)
    assert len(records) == len(e_va)
    for r, t in zip(records, ts):
        assert set(r) == {"velocity_mps", "velocity_variance_m2s2", "confidence", "timestamp"}
        assert r["velocity_variance_m2s2"] is None and r["confidence"] is None
        assert isinstance(r["velocity_mps"], float) and r["velocity_mps"] >= 0.0 and np.isfinite(r["velocity_mps"])
        assert r["timestamp"] == pytest.approx(float(t))


def test_uncertainty_model_contract_fields(train_val):
    tr, va, e_tr, e_va = train_val
    model = _uncertainty_model(train_val)
    ts = va.t_session_s[e_va]
    records = predict_contract(model, va.imu, e_va, 20, ts, device=CPU)
    assert len(records) == len(e_va)
    for r in records:
        assert r["velocity_mps"] >= 0.0 and np.isfinite(r["velocity_mps"])
        assert r["velocity_variance_m2s2"] > 0.0 and np.isfinite(r["velocity_variance_m2s2"])
        assert 0.0 < r["confidence"] <= 1.0 and np.isfinite(r["confidence"])


def test_confidence_decreases_as_variance_increases(train_val):
    """Records with larger predictive variance must never have higher confidence (monotonicity end
    to end, through the full predict_contract path, not just the model method in isolation)."""
    model = _uncertainty_model(train_val)
    tr, va, e_tr, e_va = train_val
    ts = va.t_session_s[e_va]
    records = predict_contract(model, va.imu, e_va, 20, ts, device=CPU)
    order = sorted(records, key=lambda r: r["velocity_variance_m2s2"])
    variances = [r["velocity_variance_m2s2"] for r in order]
    confidences = [r["confidence"] for r in order]
    assert all(v1 <= v2 for v1, v2 in zip(variances, variances[1:]))
    assert all(c1 >= c2 for c1, c2 in zip(confidences, confidences[1:]))


def test_timestamps_must_align_with_ends(train_val):
    model = _point_model(train_val)
    tr, va, e_tr, e_va = train_val
    with pytest.raises(ValueError):
        predict_contract(model, va.imu, e_va, 20, va.t_session_s[e_va][:-1], device=CPU)


def test_contract_matches_manual_indexed_prediction(train_val):
    """predict_contract must not duplicate the prediction path: its numbers must equal calling the
    shared predict_indexed_uncertainty function directly (variance = sigma ** 2)."""
    from src.training.train import predict_indexed_uncertainty
    model = _uncertainty_model(train_val)
    tr, va, e_tr, e_va = train_val
    ts = va.t_session_s[e_va]
    records = predict_contract(model, va.imu, e_va, 20, ts, device=CPU)
    mean, sigma = predict_indexed_uncertainty(model, va.imu, e_va, 20, CPU)
    np.testing.assert_allclose([r["velocity_mps"] for r in records], mean)
    np.testing.assert_allclose([r["velocity_variance_m2s2"] for r in records], sigma ** 2)


@pytest.mark.skipif(not torch.cuda.is_available(), reason="regression test for a CUDA-only device-mismatch bug")
def test_contract_works_on_cuda(train_val):
    """predict_contract must not crash when the model lives on a non-CPU device: sigma comes back
    from predict_indexed_uncertainty as a CPU numpy array, and confidence_from_sigma's tensor must
    be moved to wherever the model's buffers are before the two are combined."""
    cuda = torch.device("cuda")
    model = _uncertainty_model(train_val)
    tr, va, e_tr, e_va = train_val
    ts = va.t_session_s[e_va]
    records = predict_contract(model, va.imu, e_va, 20, ts, device=cuda)
    assert len(records) == len(e_va)
    assert all(np.isfinite(r["confidence"]) and 0.0 < r["confidence"] <= 1.0 for r in records)


def test_deterministic_inference(train_val):
    model = _uncertainty_model(train_val)
    tr, va, e_tr, e_va = train_val
    ts = va.t_session_s[e_va]
    r1 = predict_contract(model, va.imu, e_va, 20, ts, device=CPU)
    r2 = predict_contract(model, va.imu, e_va, 20, ts, device=CPU)
    assert r1 == r2


def test_invalid_input_shape_raises(train_val):
    """The model itself is the single enforcement point for the [B, T, 6] input contract -- wrong
    channel count or wrong rank must raise, not silently produce a wrong-shaped output."""
    model = _point_model(train_val)
    with pytest.raises(ValueError):
        model(torch.zeros(4, 20, 5))  # wrong channel count
    with pytest.raises(ValueError):
        model(torch.zeros(4, 5, 20, 6))  # wrong rank


# ------------------------------------------------------------------------------- checkpoint loading


def test_checkpoint_round_trip_preserves_normalization_and_confidence_reference(tmp_path, train_val):
    """Saving and reloading a checkpoint must reproduce the fitted normalisation buffers and the
    confidence reference exactly -- these are the values inference correctness depends on, not just
    the learned weights."""
    from src.training.train import load_checkpoint, save_checkpoint

    model = _uncertainty_model(train_val)
    ckpt = tmp_path / "checkpoint.pt"
    save_checkpoint(ckpt, model, "cnn", {**MODEL_CFG, "uncertainty": True}, extra={"epoch": 1})
    loaded, payload = load_checkpoint(ckpt)
    assert loaded.uncertainty is True
    assert payload["arch"] == "cnn"
    assert torch.allclose(loaded.input_scale, model.input_scale)
    assert loaded.target_mean.item() == pytest.approx(model.target_mean.item())
    assert loaded.target_std.item() == pytest.approx(model.target_std.item())
    assert loaded.confidence_ref_sigma.item() == pytest.approx(model.confidence_ref_sigma.item())


def test_checkpoint_loading_reproduces_predictions(tmp_path, train_val):
    """A reloaded checkpoint must give bit-for-bit-equivalent predictions to the model that was saved."""
    from src.training.train import load_checkpoint, save_checkpoint

    model = _uncertainty_model(train_val)
    tr, va, e_tr, e_va = train_val
    ts = va.t_session_s[e_va]
    before = predict_contract(model, va.imu, e_va, 20, ts, device=CPU)
    ckpt = tmp_path / "checkpoint.pt"
    save_checkpoint(ckpt, model, "cnn", {**MODEL_CFG, "uncertainty": True})
    loaded, _ = load_checkpoint(ckpt)
    after = predict_contract(loaded, va.imu, e_va, 20, ts, device=CPU)
    assert before == after


# --------------------------------------------------------------------------------------- ONNX export

onnx = pytest.importorskip("onnx", reason="onnx is required for the ONNX export tests")
onnxruntime = pytest.importorskip("onnxruntime", reason="onnxruntime is required for the ONNX export tests")

from src.data.windowing import gather_windows  # noqa: E402
from src.inference.export_onnx import (  # noqa: E402
    ProductionInferenceModule, compare_pytorch_onnx, export_model, export_production_model,
    load_onnx_session, run_onnx, verify_shapes_and_finite,
)
from src.inference.member2_interface import DECIMATION_FACTOR, PRODUCTION_RAW_WINDOW  # noqa: E402


def test_onnx_export_produces_a_valid_model_file(tmp_path, train_val):
    model = _uncertainty_model(train_val)
    path = export_model(model, 20, tmp_path / "model.onnx")
    assert path.is_file() and path.stat().st_size > 0
    onnx.checker.check_model(str(path))  # structurally valid ONNX graph


def test_onnx_dynamic_batch_shapes_and_finite(tmp_path, train_val):
    model = _uncertainty_model(train_val)
    path = export_model(model, 20, tmp_path / "model.onnx")
    session = load_onnx_session(path)
    report = verify_shapes_and_finite(session, 20, batch_sizes=(1, 4, 17))
    for batch_report in report.values():
        for info in batch_report.values():
            assert info["finite"]


def test_onnx_point_model_has_single_output(tmp_path, train_val):
    model = _point_model(train_val)
    path = export_model(model, 20, tmp_path / "point.onnx")
    session = load_onnx_session(path)
    x = np.random.default_rng(0).standard_normal((4, 20, 6)).astype(np.float32)
    out = run_onnx(session, x)
    assert set(out) == {"velocity_mps"}
    assert np.isfinite(out["velocity_mps"]).all()
    assert (out["velocity_mps"] >= 0.0).all()


def test_onnx_uncertainty_model_has_three_outputs_in_valid_ranges(tmp_path, train_val):
    model = _uncertainty_model(train_val)
    path = export_model(model, 20, tmp_path / "model.onnx")
    session = load_onnx_session(path)
    x = np.random.default_rng(0).standard_normal((32, 20, 6)).astype(np.float32)
    out = run_onnx(session, x)
    assert set(out) == {"velocity_mps", "velocity_variance_m2s2", "confidence"}
    assert np.isfinite(out["velocity_mps"]).all() and (out["velocity_mps"] >= 0.0).all()
    assert np.isfinite(out["velocity_variance_m2s2"]).all() and (out["velocity_variance_m2s2"] > 0.0).all()
    assert np.isfinite(out["confidence"]).all() and ((out["confidence"] > 0.0) & (out["confidence"] <= 1.0)).all()


def test_onnx_invalid_channel_count_raises(tmp_path, train_val):
    model = _uncertainty_model(train_val)
    path = export_model(model, 20, tmp_path / "model.onnx")
    session = load_onnx_session(path)
    bad = np.random.default_rng(0).standard_normal((4, 20, 5)).astype(np.float32)  # 5 channels, not 6
    with pytest.raises(Exception):
        run_onnx(session, bad)


def test_onnx_invalid_window_length_raises(tmp_path, train_val):
    model = _uncertainty_model(train_val)
    path = export_model(model, 20, tmp_path / "model.onnx")  # exported for window=20
    session = load_onnx_session(path)
    bad = np.random.default_rng(0).standard_normal((4, 40, 6)).astype(np.float32)  # wrong window length
    with pytest.raises(Exception):
        run_onnx(session, bad)


def test_onnx_matches_pytorch_on_random_input(tmp_path, train_val):
    model = _uncertainty_model(train_val)
    path = export_model(model, 20, tmp_path / "model.onnx")
    session = load_onnx_session(path)
    x = np.random.default_rng(1).standard_normal((64, 20, 6)).astype(np.float32)
    report = compare_pytorch_onnx(model, session, x, atol=1e-4, rtol=1e-3)
    for name, r in report.items():
        assert r["allclose"], f"{name}: max abs diff {r['max_abs_diff']}"
        assert r["finite_pytorch"] and r["finite_onnx"]


def test_onnx_matches_pytorch_on_real_windows(tmp_path, train_val):
    """PyTorch vs ONNX agreement on real gathered IMU windows, not just synthetic random noise."""
    model = _uncertainty_model(train_val)
    tr, va, e_tr, e_va = train_val
    windows = gather_windows(va.imu, e_va, 20)
    path = export_model(model, 20, tmp_path / "model.onnx")
    session = load_onnx_session(path)
    report = compare_pytorch_onnx(model, session, windows, atol=1e-4, rtol=1e-3)
    for name, r in report.items():
        assert r["allclose"], f"{name}: max abs diff {r['max_abs_diff']}"


def test_onnx_matches_predict_contract_end_to_end(tmp_path, train_val):
    """The full ONNX pipeline (windowing -> ONNX Runtime) must agree with the full PyTorch pipeline
    (windowing -> predict_contract), proving preprocessing/normalisation is applied identically on
    both paths -- the model owns normalisation internally in both cases, so there is no separate
    preprocessing implementation that could drift between them."""
    model = _uncertainty_model(train_val)
    tr, va, e_tr, e_va = train_val
    ts = va.t_session_s[e_va]
    records = predict_contract(model, va.imu, e_va, 20, ts, device=CPU)
    windows = gather_windows(va.imu, e_va, 20)
    path = export_model(model, 20, tmp_path / "model.onnx")
    session = load_onnx_session(path)
    out = run_onnx(session, windows)
    np.testing.assert_allclose(out["velocity_mps"], [r["velocity_mps"] for r in records], atol=1e-4, rtol=1e-3)
    np.testing.assert_allclose(out["velocity_variance_m2s2"], [r["velocity_variance_m2s2"] for r in records], atol=1e-4, rtol=1e-3)
    np.testing.assert_allclose(out["confidence"], [r["confidence"] for r in records], atol=1e-4, rtol=1e-3)


def test_onnx_deterministic_inference(tmp_path, train_val):
    model = _uncertainty_model(train_val)
    path = export_model(model, 20, tmp_path / "model.onnx")
    session = load_onnx_session(path)
    x = np.random.default_rng(2).standard_normal((8, 20, 6)).astype(np.float32)
    out1 = run_onnx(session, x)
    out2 = run_onnx(session, x)
    for name in out1:
        np.testing.assert_array_equal(out1[name], out2[name])


# ------------------------------------------------------------------------- production 100Hz ONNX


def test_export_production_model_requires_window_that_decimates_to_200():
    """A checkpoint whose native window isn't 20 can't honestly be served behind a 200-sample
    (2 s @ 100 Hz) production input without either a 400-sample buffer or retraining -- must raise,
    not silently export a mismatched graph."""
    model = build_model("cnn", MODEL_CFG).eval()  # normalization defaults are fine; never runs forward
    with pytest.raises(ValueError):
        ProductionInferenceModule(model, native_window=40)


def test_production_onnx_export_accepts_raw_100hz_window_shape(tmp_path, train_val):
    model = _uncertainty_model(train_val)
    path = export_production_model(model, tmp_path / "production.onnx")
    assert path.is_file() and path.stat().st_size > 0
    onnx.checker.check_model(str(path))
    session = load_onnx_session(path)
    x = np.random.default_rng(0).standard_normal((4, PRODUCTION_RAW_WINDOW, 6)).astype(np.float32)
    out = run_onnx(session, x)
    assert set(out) == {"velocity_mps", "velocity_variance_m2s2", "confidence"}
    assert out["velocity_mps"].shape == (4,)
    assert np.isfinite(out["velocity_mps"]).all() and (out["velocity_mps"] >= 0.0).all()
    assert np.isfinite(out["velocity_variance_m2s2"]).all() and (out["velocity_variance_m2s2"] > 0.0).all()


def test_production_onnx_matches_decimate_then_native_onnx(tmp_path, train_val):
    """The production graph (raw 200-sample input, decimated inside the graph) must agree with
    manually decimating first and running the existing native 20-sample export -- proving the graph's
    internal decimation is exactly src.inference.member2_interface.decimate, not a reimplementation."""
    from src.inference.member2_interface import decimate

    model = _uncertainty_model(train_val)
    native_path = export_model(model, 20, tmp_path / "native.onnx")
    production_path = export_production_model(model, tmp_path / "production.onnx")
    native_session = load_onnx_session(native_path)
    production_session = load_onnx_session(production_path)

    raw = np.random.default_rng(2).standard_normal((8, PRODUCTION_RAW_WINDOW, 6)).astype(np.float32)
    decimated = np.stack([decimate(w) for w in raw])

    production_out = run_onnx(production_session, raw)
    native_out = run_onnx(native_session, decimated)
    for name in native_out:
        np.testing.assert_allclose(production_out[name], native_out[name], atol=1e-5, rtol=1e-4)


def test_production_onnx_matches_pytorch_production_wrapper(tmp_path, train_val):
    model = _uncertainty_model(train_val)
    path = export_production_model(model, tmp_path / "production.onnx")
    session = load_onnx_session(path)
    x = np.random.default_rng(3).standard_normal((5, PRODUCTION_RAW_WINDOW, 6)).astype(np.float32)
    wrapper = ProductionInferenceModule(model).eval()
    with torch.no_grad():
        velocity, variance, confidence = wrapper(torch.as_tensor(x))
    out = run_onnx(session, x)
    np.testing.assert_allclose(out["velocity_mps"], velocity.numpy(), atol=1e-4, rtol=1e-3)
    np.testing.assert_allclose(out["velocity_variance_m2s2"], variance.numpy(), atol=1e-4, rtol=1e-3)
    np.testing.assert_allclose(out["confidence"], confidence.numpy(), atol=1e-4, rtol=1e-3)


def test_production_onnx_wrong_raw_window_length_raises(tmp_path, train_val):
    model = _uncertainty_model(train_val)
    path = export_production_model(model, tmp_path / "production.onnx")
    session = load_onnx_session(path)
    bad = np.random.default_rng(0).standard_normal((2, 199, 6)).astype(np.float32)  # not 200
    with pytest.raises(Exception):
        run_onnx(session, bad)


def test_production_onnx_works_end_to_end_with_magnitude_channel_model(tmp_path, train_val):
    """The actual production model (cnn_mag, derive_magnitude_channels=True) exported through the
    SAME production path used by every other candidate: raw [B, 200, 6] @ 100 Hz in, decimated to
    [B, 20, 6] inside the graph, magnitude channels derived internally by the model (not the
    ONNX-export code) -- confirms the two features compose correctly end to end."""
    model = _uncertainty_magnitude_model(train_val)
    path = export_production_model(model, tmp_path / "production_mag.onnx")
    onnx.checker.check_model(str(path))
    session = load_onnx_session(path)
    x = np.random.default_rng(5).standard_normal((6, PRODUCTION_RAW_WINDOW, 6)).astype(np.float32)
    out = run_onnx(session, x)
    assert set(out) == {"velocity_mps", "velocity_variance_m2s2", "confidence"}
    assert np.isfinite(out["velocity_mps"]).all() and (out["velocity_mps"] >= 0.0).all()
    assert np.isfinite(out["velocity_variance_m2s2"]).all() and (out["velocity_variance_m2s2"] > 0.0).all()

    wrapper = ProductionInferenceModule(model).eval()
    with torch.no_grad():
        velocity, variance, confidence = wrapper(torch.as_tensor(x))
    np.testing.assert_allclose(out["velocity_mps"], velocity.numpy(), atol=1e-4, rtol=1e-3)
    np.testing.assert_allclose(out["velocity_variance_m2s2"], variance.numpy(), atol=1e-4, rtol=1e-3)


def test_predict_contract_production_matches_predict_contract_on_decimated_window(train_val):
    from src.inference.predict import predict_contract_production
    from src.inference.member2_interface import decimate

    model = _uncertainty_model(train_val)
    raw = np.random.default_rng(4).standard_normal((PRODUCTION_RAW_WINDOW, 6)).astype(np.float32)
    record = predict_contract_production(model, raw, timestamp=42.0, device=CPU)
    assert record["timestamp"] == pytest.approx(42.0)
    assert record["velocity_mps"] >= 0.0 and record["velocity_variance_m2s2"] > 0.0

    decimated = decimate(raw)
    expected = predict_contract(model, decimated, np.array([19]), 20, np.array([42.0]), device=CPU)[0]
    assert record == expected


# ---------------------------------------------------------------------------------------- benchmark


def test_pytorch_cpu_latency_is_positive_and_finite(train_val):
    from src.inference.benchmark import pytorch_cpu_latency_ms

    model = _point_model(train_val)
    latency = pytorch_cpu_latency_ms(model, 20, n_warmup=2, n_repeats=5)
    assert latency > 0.0 and np.isfinite(latency)


def test_onnx_model_size_and_param_count_are_positive(tmp_path, train_val):
    from src.inference.benchmark import model_size_bytes
    from src.models.tcn_velocity import count_parameters

    model = _uncertainty_model(train_val)
    path = export_model(model, 20, tmp_path / "model.onnx")
    assert model_size_bytes(path) > 0
    assert count_parameters(model) > 0
