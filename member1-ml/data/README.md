# Data

Place the dataset at `data/member1_imu_speed.npz`. It is **not** tracked by git (see `.gitignore`)
and is never modified by any code in this repository (it is only opened read-only with `np.load`).

Inspect and validate it with:

```bash
python -m src.data.inspect_dataset --npz data/member1_imu_speed.npz
```

The structure, allowed inputs and split protocol are documented in [`docs/data_protocol.md`](../docs/data_protocol.md).
