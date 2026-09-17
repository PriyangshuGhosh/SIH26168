#!/usr/bin/env python3
"""Write a tiny ONNX graph matching Member 1 I/O names for C++ loader tests.

This is NOT speed_estimator.onnx and must not be used as a production model.
Requires the `onnx` Python package.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
from onnx import TensorProto, helper, numpy_helper, save


def main() -> None:
    out = Path(__file__).resolve().parents[1] / "tests" / "data" / "dummy_speed_estimator.onnx"
    x = helper.make_tensor_value_info("imu_window", TensorProto.FLOAT, [1, 200, 6])
    y_v = helper.make_tensor_value_info("velocity_mps", TensorProto.FLOAT, [1])
    y_u = helper.make_tensor_value_info("uncertainty", TensorProto.FLOAT, [1])
    y_c = helper.make_tensor_value_info("confidence", TensorProto.FLOAT, [1])

    reduce = helper.make_node(
        "ReduceMean",
        inputs=["imu_window"],
        outputs=["mean"],
        axes=[1, 2],
        keepdims=0,
    )
    relu = helper.make_node("Relu", inputs=["mean"], outputs=["velocity_mps"])
    unc = numpy_helper.from_array(np.array([0.5], dtype=np.float32), name="unc_init")
    conf = numpy_helper.from_array(np.array([0.7], dtype=np.float32), name="conf_init")
    id_u = helper.make_node("Identity", inputs=["unc_init"], outputs=["uncertainty"])
    id_c = helper.make_node("Identity", inputs=["conf_init"], outputs=["confidence"])

    graph = helper.make_graph(
        [reduce, relu, id_u, id_c],
        "dummy_member1_io",
        [x],
        [y_v, y_u, y_c],
        [unc, conf],
    )
    model = helper.make_model(graph, opset_imports=[helper.make_opsetid("", 13)])
    model.ir_version = 8
    out.parent.mkdir(parents=True, exist_ok=True)
    save(model, out)
    print(f"wrote {out} ({out.stat().st_size} bytes) — wiring fixture only")


if __name__ == "__main__":
    main()
