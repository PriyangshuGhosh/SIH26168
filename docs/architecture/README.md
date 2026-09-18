# SIH26168 architecture

```text
Phone IMU (m/s², rad/s, timestamps in seconds)
      |
      v
Member 2 FrameAligner  → vehicle frame +X forward, +Y left, +Z up, quaternion [w,x,y,z]
      |
      +------> Member 1 AI speed  (100 Hz windows of 200 samples, output m/s + variance)
      |                 |
      v                 v
Member 3 EKF  [x,y,vx,vy,yaw,bax,bay,bgz]  GNSS gated, AI gated, NIS
      |
      v
Member 4 offline HMM map match  (.roadpack only at runtime; no OSM download)
      |
      v
Member 5 libidr_engine  C ABI  (speed m/s, validity flags, map catalog)
      |
      v
Member 6 Android JNI / UI
```

Rendering tiles (MBTiles) and road-network `.roadpack` files are separate. A roadpack is not a visual map.

Mock ONNX / integrator backends are labelled **SIMULATION**. They are not trained-model accuracy.

See [INTERFACES.md](INTERFACES.md) and [SAFETY.md](SAFETY.md).
