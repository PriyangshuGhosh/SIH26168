from __future__ import annotations

import numpy as np
import pytest

torch = pytest.importorskip("torch", reason="PyTorch is required for the Milestone 2 model tests")

from conftest import SPLIT_RULES  # noqa: E402
from src.data.augmentation import build_augmentation  # noqa: E402
from src.data.dataset import LeakageError, from_arrays  # noqa: E402
from src.data.splits import make_split  # noqa: E402
from src.data.windowing import gather_windows, window_end_indices  # noqa: E402
from src.models.tcn_velocity import VelocityNet, build_model, count_parameters, fit_normalization, log_var_to_sigma  # noqa: E402
from src.training.losses import heteroscedastic_gaussian_nll, make_loss, make_uncertainty_loss  # noqa: E402
from src.training.train import (  # noqa: E402
    load_checkpoint, predict_indexed, predict_indexed_uncertainty, predict_windows, predict_windows_uncertainty,
    save_checkpoint, seed_everything, train_model,
)

MODEL_CFGS = {
    "cnn": {"channels": 8, "kernel_size": 5, "n_blocks": 2, "dropout": 0.1},
    "tcn": {"channels": 8, "kernel_size": 3, "dilations": [1, 2, 4, 8], "dropout": 0.1},
}
UNCERTAINTY_MODEL_CFGS = {a: {**c, "uncertainty": True} for a, c in MODEL_CFGS.items()}
TRAIN_CFG = {"batch_size": 32, "eval_batch_size": 64, "max_epochs": 3, "lr": 3e-3, "weight_decay": 1e-2,
             "warmup_epochs": 1, "min_lr_ratio": 0.1, "grad_clip_norm": 1.0, "loss": "huber", "huber_delta_mps": 1.0,
             "early_stopping_patience": 5, "min_delta_mps": 0.0, "amp": "off"}
NLL_TRAIN_CFG = {**TRAIN_CFG, "loss": "nll", "warmup_loss": "huber", "nll_warmup_epochs": 1}
AUGMENT_FN = build_augmentation("so3", {"probability": 1.0, "max_angle_deg": 180.0}, {"probability": 1.0, "max_angle_deg": 180.0})
CPU = torch.device("cpu")


@pytest.fixture(autouse=True)
def _seed():
    seed_everything(0)
    yield
    torch.use_deterministic_algorithms(False)


def _model(arch: str) -> VelocityNet:
    return build_model(arch, MODEL_CFGS[arch]).eval()


@pytest.fixture
def windows(arrays):
    ds = from_arrays(arrays)
    split = make_split(ds.trip_id, ds.session_id, SPLIT_RULES)
    tr, va = ds.subset(split.masks["train"]), ds.subset(split.masks["val"])
    e_tr, e_va = window_end_indices(tr, 20, 5), window_end_indices(va, 20, 1)
    return {"train_x": gather_windows(tr.imu, e_tr, 20), "train_y": tr.target[e_tr].astype(np.float64),
            "val_x": gather_windows(va.imu, e_va, 20), "val_y": va.target[e_va].astype(np.float64),
            "train_imu": tr.imu, "val_ds": va, "val_ends": e_va}


# ----------------------------------------------------------------------------- model

@pytest.mark.parametrize("arch", ["cnn", "tcn"])
@pytest.mark.parametrize("t", [20, 40])
def test_forward_shape_and_finite(arch, t):
    model = _model(arch)
    out = model(torch.randn(5, t, 6))
    assert out.shape == (5,) and torch.isfinite(out).all()


@pytest.mark.parametrize("arch", ["cnn", "tcn"])
def test_rejects_wrong_input_shape(arch):
    model = _model(arch)
    for bad in (torch.randn(2, 20, 7), torch.randn(2, 6, 20)[:, :, :5], torch.randn(20, 6)):
        with pytest.raises(ValueError):
            model(bad)


@pytest.mark.parametrize("arch", ["cnn", "tcn"])
def test_per_step_features_are_causal(arch):
    """Feature at step t must not change when inputs after t change (eval mode)."""
    model = _model(arch)
    x = torch.randn(3, 40, 6)
    t = 17
    x2 = x.clone()
    x2[:, t + 1:] = torch.randn_like(x2[:, t + 1:]) * 50
    torch.testing.assert_close(model.features(x)[:, :, :t + 1], model.features(x2)[:, :, :t + 1])
    assert not torch.allclose(model.features(x)[:, :, t + 1:], model.features(x2)[:, :, t + 1:])


def test_tcn_prediction_equals_streaming_prefix():
    """TCN output for a window equals the last-step output of any longer history ending at the same point."""
    model = _model("tcn")
    x = torch.randn(2, 60, 6)
    full = model.blocks((x / model.input_scale).transpose(1, 2))[:, :, 39]
    prefix = model.blocks((x[:, :40] / model.input_scale).transpose(1, 2))[:, :, -1]
    torch.testing.assert_close(full, prefix)


def test_tcn_receptive_field_covers_window():
    assert build_model("tcn", {"channels": 32, "kernel_size": 3, "dilations": [1, 2, 4, 8], "dropout": 0.1}).receptive_field >= 40


def test_output_depends_on_input():
    model = _model("tcn")
    x = torch.randn(1, 20, 6)
    x2 = x.clone()
    x2[:, -1, 0] += 10
    assert not torch.allclose(model(x), model(x2))


def test_models_are_small():
    for arch, cfg in (("cnn", {"channels": 32, "kernel_size": 5, "n_blocks": 3, "dropout": 0.1}),
                      ("tcn", {"channels": 32, "kernel_size": 3, "dilations": [1, 2, 4, 8], "dropout": 0.1})):
        assert count_parameters(build_model(arch, cfg)) < 100_000


def test_normalization_fit_and_rotation_consistency(windows):
    scale, mean, std = fit_normalization(windows["train_imu"], windows["train_y"])
    assert scale.shape == (6,) and np.all(scale > 0)
    assert np.all(scale[:3] == scale[0]) and np.all(scale[3:] == scale[3])  # shared per sensor (rotation-safe)
    assert mean == pytest.approx(windows["train_y"].mean()) and std == pytest.approx(windows["train_y"].std())
    model = _model("cnn")
    model.set_normalization(scale, mean, std)
    assert torch.allclose(model.target_mean, torch.tensor(mean, dtype=torch.float32))


def test_unknown_arch_rejected():
    with pytest.raises(ValueError):
        build_model("lstm", MODEL_CFGS["cnn"])


# --------------------------------------------------------------- derive_magnitude_channels (cnn_mag)

MAGNITUDE_MODEL_CFG = {**MODEL_CFGS["cnn"], "derive_magnitude_channels": True}


def test_magnitude_model_public_contract_still_six_channels():
    """derive_magnitude_channels is an internal-only detail: the public forward()/features() input
    is still exactly [B, T, 6], never 8 -- external callers (windowing, ONNX, member2_interface)
    never need to know about it."""
    model = build_model("cnn", MAGNITUDE_MODEL_CFG).eval()
    out = model(torch.randn(4, 20, 6))
    assert out.shape == (4,) and torch.isfinite(out).all()
    for bad in (torch.randn(2, 20, 7), torch.randn(2, 20, 8), torch.randn(2, 20, 5)):
        with pytest.raises(ValueError):
            model(bad)


def test_cnn_mag_alias_builds_cnn_arch_with_magnitude_channels():
    """build_model("cnn_mag", ...) is a config-selection alias: VelocityNet.arch stays "cnn"
    (mean-pool readout), only derive_magnitude_channels differs."""
    model = build_model("cnn_mag", MAGNITUDE_MODEL_CFG).eval()
    assert model.arch == "cnn" and model.derive_magnitude_channels is True
    out = model(torch.randn(3, 20, 6))
    assert out.shape == (3,) and torch.isfinite(out).all()


def test_magnitude_channels_only_add_a_few_parameters():
    plain = count_parameters(build_model("cnn", MODEL_CFGS["cnn"]))
    with_mag = count_parameters(build_model("cnn", MAGNITUDE_MODEL_CFG))
    # only the first conv layer's input width changes (6 -> 8 channels); a handful of extra weights.
    assert 0 < with_mag - plain < 200


def test_magnitude_channels_are_rotation_invariant():
    """|acc| and |gyr| are the L2 norm of a rotated vector, which rotation preserves exactly -- the
    derived magnitude channels see the SAME values whether the raw 6-channel window was rotated by
    yaw/SO(3) augmentation or not (unlike the raw per-axis channels, which do change). This is the
    property that motivated adding them: an orientation-invariant cue for a dataset with unknown,
    inconsistent phone mounting per trip (docs/data_protocol.md)."""
    from src.data.augmentation import random_rotation_matrices, rotate_windows

    x = torch.randn(6, 20, 6)
    rng = np.random.default_rng(0)
    r = random_rotation_matrices(6, rng)
    x_rot = torch.as_tensor(rotate_windows(x.numpy(), r))
    torch.testing.assert_close(x[..., 0:3].norm(dim=-1), x_rot[..., 0:3].norm(dim=-1), atol=1e-4, rtol=1e-4)
    torch.testing.assert_close(x[..., 3:6].norm(dim=-1), x_rot[..., 3:6].norm(dim=-1), atol=1e-4, rtol=1e-4)
    assert not torch.allclose(x[..., 0], x_rot[..., 0])  # the raw per-axis channels DO change


def test_per_step_features_are_causal_with_magnitude_channels():
    model = build_model("cnn", MAGNITUDE_MODEL_CFG).eval()
    x = torch.randn(3, 40, 6)
    t = 17
    x2 = x.clone()
    x2[:, t + 1:] = torch.randn_like(x2[:, t + 1:]) * 50
    torch.testing.assert_close(model.features(x)[:, :, :t + 1], model.features(x2)[:, :, :t + 1])
    assert not torch.allclose(model.features(x)[:, :, t + 1:], model.features(x2)[:, :, t + 1:])


def test_fit_normalization_with_magnitude_channels_appends_two_scale_entries(windows):
    scale6, _, _ = fit_normalization(windows["train_imu"], windows["train_y"])
    scale8, mean, std = fit_normalization(windows["train_imu"], windows["train_y"], derive_magnitude_channels=True)
    assert scale8.shape == (8,)
    np.testing.assert_allclose(scale8[:6], scale6)
    assert scale8[6] == pytest.approx(scale6[0]) and scale8[7] == pytest.approx(scale6[3])  # reuse acc/gyr RMS
    model = build_model("cnn", MAGNITUDE_MODEL_CFG).eval()
    model.set_normalization(scale8, mean, std)  # must not raise (buffer shape matches)
    assert model.input_scale.shape == (8,)


# ----------------------------------------------------------------------------- loss

def test_losses():
    pred, target = torch.tensor([0.0, 2.0, 5.0]), torch.tensor([0.0, 1.0, 1.0])
    assert make_loss("mse")(pred, target).item() == pytest.approx((0 + 1 + 16) / 3)
    assert make_loss("l1")(pred, target).item() == pytest.approx((0 + 1 + 4) / 3)
    # huber delta=1: 0, 0.5*1^2, 1*(4-0.5)
    assert make_loss("huber", 1.0)(pred, target).item() == pytest.approx((0 + 0.5 + 3.5) / 3)
    assert make_loss("huber")(target, target).item() == 0.0
    p = pred.clone().requires_grad_(True)
    make_loss("huber")(p, target).backward()
    assert torch.isfinite(p.grad).all()
    with pytest.raises(ValueError):
        make_loss("nll")
    with pytest.raises(ValueError):
        make_loss("huber", 0.0)


# ----------------------------------------------------------------------------- training / checkpoint / determinism

def _train(windows, arch, tmp_path, seed=0, augment_fn=AUGMENT_FN, model_cfg=None, tcfg=TRAIN_CFG):
    seed_everything(seed)
    model_cfg = model_cfg or MODEL_CFGS[arch]
    model = build_model(arch, model_cfg)
    model.set_normalization(*fit_normalization(windows["train_imu"], windows["train_y"]))
    history = train_model(model, arch, model_cfg, windows["train_x"], windows["train_y"], windows["val_x"],
                          windows["val_y"], tcfg, augment_fn, seed, CPU, tmp_path / "best.pt", log=lambda _: None)
    return model, history


@pytest.mark.parametrize("arch", ["cnn", "tcn"])
def test_training_runs_and_checkpoint_roundtrip(windows, arch, tmp_path):
    model, history = _train(windows, arch, tmp_path)
    assert len(history) == TRAIN_CFG["max_epochs"]
    assert all(np.isfinite(h["train_loss"]) and np.isfinite(h["val_mae_mps"]) for h in history)
    assert (tmp_path / "best.pt").is_file()
    loaded, payload = load_checkpoint(tmp_path / "best.pt")
    best_epoch = min(history, key=lambda h: h["val_mae_mps"])["epoch"]
    assert payload["epoch"] == best_epoch and payload["arch"] == arch
    # reloaded best checkpoint reproduces its recorded validation MAE exactly
    p = predict_windows(loaded, windows["val_x"], CPU)
    assert np.mean(np.abs(p - windows["val_y"])) == pytest.approx(payload["val_metrics"]["mae_mps"], rel=1e-6)
    assert (p >= 0).all() and np.isfinite(p).all()
    # normalisation buffers are restored
    torch.testing.assert_close(loaded.input_scale, model.input_scale)
    # chunked indexed prediction equals materialised prediction
    ds, e = windows["val_ds"], windows["val_ends"]
    np.testing.assert_allclose(predict_indexed(loaded, ds.imu, e, 20, CPU, batch_size=7, chunk_size=13), p, rtol=1e-5, atol=1e-5)


def test_save_load_preserves_outputs(tmp_path):
    model = _model("tcn")
    model.set_normalization(np.full(6, 2.0, dtype=np.float32), 12.0, 4.0)
    save_checkpoint(tmp_path / "m.pt", model, "tcn", MODEL_CFGS["tcn"], {"epoch": 1})
    loaded, _ = load_checkpoint(tmp_path / "m.pt")
    x = torch.randn(4, 40, 6)
    torch.testing.assert_close(loaded(x), model(x))


def test_training_is_deterministic(windows, tmp_path):
    _, h1 = _train(windows, "tcn", tmp_path / "a", seed=3)
    _, h2 = _train(windows, "tcn", tmp_path / "b", seed=3)
    assert [h["train_loss"] for h in h1] == [h["train_loss"] for h in h2]
    assert [h["val_mae_mps"] for h in h1] == [h["val_mae_mps"] for h in h2]
    _, h3 = _train(windows, "tcn", tmp_path / "c", seed=4)
    assert [h["train_loss"] for h in h1] != [h["train_loss"] for h in h3]


def test_training_rejects_non_imu_features(windows, tmp_path):
    """Anything but [N, T, 6] IMU windows is refused, e.g. IMU + an appended speed/GPS column."""
    leaky = np.concatenate([windows["train_x"], windows["train_y"][:, None, None].repeat(20, 1).astype(np.float32)], -1)
    model = build_model("cnn", MODEL_CFGS["cnn"])
    with pytest.raises(ValueError):
        train_model(model, "cnn", MODEL_CFGS["cnn"], leaky, windows["train_y"], windows["val_x"], windows["val_y"],
                    TRAIN_CFG, None, 0, CPU, tmp_path / "x.pt", log=lambda _: None)
    with pytest.raises(ValueError):
        model(torch.as_tensor(leaky))
    with pytest.raises(LeakageError):  # the only constructor of IMU input refuses non-IMU keys
        from src.data.dataset import build_model_input
        build_model_input({"acc": np.zeros((3, 3)), "gyr": np.zeros((3, 3)), "gps_speed": np.zeros((3, 3))},
                          keys=("acc", "gyr", "gps_speed"))


# ----------------------------------------------------------------------------- uncertainty (Milestone 3)


@pytest.mark.parametrize("arch", ["cnn", "tcn"])
def test_uncertainty_forward_shape_positive_finite(arch):
    model = build_model(arch, UNCERTAINTY_MODEL_CFGS[arch]).eval()
    mean, log_var = model.forward_full(torch.randn(6, 40, 6))
    assert mean.shape == (6,) and log_var.shape == (6,)
    assert torch.isfinite(mean).all() and torch.isfinite(log_var).all()
    sigma = log_var_to_sigma(log_var)
    assert torch.isfinite(sigma).all() and (sigma > 0).all()


def test_uncertainty_head_clamped_and_stable_on_extreme_input():
    """However extreme the input, the clamped log-variance keeps sigma finite and positive."""
    model = build_model("tcn", UNCERTAINTY_MODEL_CFGS["tcn"]).eval()
    x = torch.randn(4, 40, 6) * 1e4
    mean, log_var = model.forward_full(x)
    assert torch.isfinite(mean).all()
    assert (log_var >= model.log_var_min - 1e-4).all() and (log_var <= 2 * torch.log(model.target_std) + model.log_var_max + 1e-4).all()
    sigma = log_var_to_sigma(log_var)
    assert torch.isfinite(sigma).all() and (sigma > 0).all()


def test_uncertainty_head_clamp_bounds_arbitrary_head_weights():
    """The clamp must bound the output even when the log-variance head itself produces extreme
    raw values (a freshly built model's head is zero-init, which alone would mask a missing
    clamp -- so this test drives the head directly instead of relying on random weights)."""
    model = build_model("cnn", {**UNCERTAINTY_MODEL_CFGS["cnn"], "log_var_min": -3.0, "log_var_max": 3.0}).eval()
    with torch.no_grad():
        model.log_var_head.weight.fill_(1e6)
        model.log_var_head.bias.fill_(1e6)
    mean, log_var = model.forward_full(torch.randn(5, 20, 6))
    lo = model.log_var_min + 2.0 * torch.log(model.target_std)
    hi = model.log_var_max + 2.0 * torch.log(model.target_std)
    assert torch.isfinite(log_var).all()
    assert (log_var >= lo - 1e-4).all() and (log_var <= hi + 1e-4).all()
    sigma = log_var_to_sigma(log_var)
    assert torch.isfinite(sigma).all() and (sigma > 0).all()
    with torch.no_grad():
        model.log_var_head.weight.fill_(-1e6)
        model.log_var_head.bias.fill_(-1e6)
    _, log_var_neg = model.forward_full(torch.randn(5, 20, 6))
    assert (log_var_neg >= lo - 1e-4).all() and torch.isfinite(log_var_to_sigma(log_var_neg)).all()


def test_point_model_has_no_uncertainty_output():
    model = build_model("cnn", MODEL_CFGS["cnn"]).eval()
    assert model.uncertainty is False
    mean, log_var = model.forward_full(torch.randn(3, 20, 6))
    assert log_var is None
    with pytest.raises(ValueError):
        predict_windows_uncertainty(model, np.zeros((2, 20, 6), dtype=np.float32), CPU)


def test_log_var_min_max_validated():
    with pytest.raises(ValueError):
        build_model("cnn", {**UNCERTAINTY_MODEL_CFGS["cnn"], "log_var_min": 1.0, "log_var_max": -1.0})


def test_confidence_from_sigma_monotonic_and_bounded():
    model = build_model("cnn", UNCERTAINTY_MODEL_CFGS["cnn"])
    model.set_confidence_reference(2.0)
    sigma = torch.tensor([0.0, 0.5, 2.0, 10.0, 1000.0])
    conf = model.confidence_from_sigma(sigma)
    assert torch.isfinite(conf).all()
    assert conf[0].item() == pytest.approx(1.0)
    assert conf[2].item() == pytest.approx(0.5)
    assert (conf[:-1] > conf[1:]).all()  # strictly decreasing as sigma grows
    assert ((conf > 0) & (conf <= 1)).all()
    with pytest.raises(ValueError):
        model.set_confidence_reference(0.0)
    with pytest.raises(ValueError):
        model.set_confidence_reference(-1.0)


def test_heteroscedastic_nll_loss_gradients_finite():
    mean = torch.tensor([1.0, 2.0, 3.0], requires_grad=True)
    log_var = torch.tensor([-1.0, 0.0, 1.0], requires_grad=True)
    target = torch.tensor([1.5, 1.0, 5.0])
    loss = heteroscedastic_gaussian_nll(mean, log_var, target)
    assert torch.isfinite(loss)
    loss.backward()
    assert torch.isfinite(mean.grad).all() and torch.isfinite(log_var.grad).all()
    assert heteroscedastic_gaussian_nll(target, torch.zeros(3), target) < loss  # perfect mean -> lower NLL
    with pytest.raises(ValueError):
        make_uncertainty_loss("huber")


@pytest.mark.parametrize("arch", ["cnn", "tcn"])
def test_uncertainty_training_runs_and_checkpoint_roundtrip(windows, arch, tmp_path):
    model, history = _train(windows, arch, tmp_path, model_cfg=UNCERTAINTY_MODEL_CFGS[arch], tcfg=NLL_TRAIN_CFG)
    assert len(history) == NLL_TRAIN_CFG["max_epochs"]
    assert [h["in_warmup"] for h in history] == [True] + [False] * (NLL_TRAIN_CFG["max_epochs"] - 1)
    assert all(np.isfinite(h["val_nll"]) and h["val_mean_sigma_mps"] > 0 for h in history)
    loaded, payload = load_checkpoint(tmp_path / "best.pt")
    assert loaded.uncertainty is True
    assert "val_nll" in payload and np.isfinite(payload["val_nll"])
    mean, sigma = predict_windows_uncertainty(loaded, windows["val_x"], CPU)
    assert (sigma > 0).all() and np.isfinite(sigma).all() and (mean >= 0).all()
    assert np.mean(np.abs(mean - windows["val_y"])) == pytest.approx(payload["val_metrics"]["mae_mps"], rel=1e-6)
    # chunked indexed uncertainty prediction matches materialised prediction
    ds, e = windows["val_ds"], windows["val_ends"]
    m2, s2 = predict_indexed_uncertainty(loaded, ds.imu, e, 20, CPU, batch_size=7, chunk_size=13)
    np.testing.assert_allclose(m2, mean, rtol=1e-5, atol=1e-5)
    np.testing.assert_allclose(s2, sigma, rtol=1e-5, atol=1e-5)


def test_nll_requires_uncertainty_model(windows, tmp_path):
    model = build_model("cnn", MODEL_CFGS["cnn"])  # no uncertainty head
    with pytest.raises(ValueError):
        train_model(model, "cnn", MODEL_CFGS["cnn"], windows["train_x"], windows["train_y"], windows["val_x"],
                    windows["val_y"], NLL_TRAIN_CFG, None, 0, CPU, tmp_path / "x.pt", log=lambda _: None)


def test_uncertainty_inference_deterministic(windows, tmp_path):
    _, h1 = _train(windows, "tcn", tmp_path / "a", seed=7, model_cfg=UNCERTAINTY_MODEL_CFGS["tcn"], tcfg=NLL_TRAIN_CFG)
    _, h2 = _train(windows, "tcn", tmp_path / "b", seed=7, model_cfg=UNCERTAINTY_MODEL_CFGS["tcn"], tcfg=NLL_TRAIN_CFG)
    assert [h["val_nll"] for h in h1] == [h["val_nll"] for h in h2]
    loaded1, _ = load_checkpoint(tmp_path / "a" / "best.pt")
    loaded2, _ = load_checkpoint(tmp_path / "b" / "best.pt")
    m1, s1 = predict_windows_uncertainty(loaded1, windows["val_x"], CPU)
    m2, s2 = predict_windows_uncertainty(loaded2, windows["val_x"], CPU)
    np.testing.assert_array_equal(m1, m2)
    np.testing.assert_array_equal(s1, s2)


def test_augmentation_policy_alternatives_produce_different_but_valid_training(windows, tmp_path):
    """Sanity check that every augmentation policy trains a model to finite, valid outputs."""
    from src.data.augmentation import build_augmentation
    so3_cfg = {"probability": 1.0, "max_angle_deg": 180.0}
    yaw_cfg = {"probability": 1.0, "max_angle_deg": 180.0}
    for policy in ("none", "so3", "yaw", "gravity_yaw"):
        fn = build_augmentation(policy, so3_cfg, yaw_cfg)
        _, history = _train(windows, "cnn", tmp_path / policy, augment_fn=fn)
        assert all(np.isfinite(h["train_loss"]) and np.isfinite(h["val_mae_mps"]) for h in history)
