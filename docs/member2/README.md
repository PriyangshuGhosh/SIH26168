# Member 2 — Sensor Calibration & Frame Alignment

## Current completion status

**Status: IMPLEMENTED + HOST VALIDATED.**

### Confirmed in the repository

- Real-time phone-to-vehicle frame alignment is implemented in `member2_alignment/`.
- C++ implementation, Python reference/tests, calibration status handling, confidence handling, rotation conventions, and downstream integration documentation are present.
- The latest repository-wide host CTest run passed both Member 2 C++ and Python test suites.
- A benchmark executable is present for the module.

### Validation boundary

- Host/reference validation is complete for the committed test suite.
- Android/arm64-v8a target performance is **NOT VALIDATED** by this module.
- Real-world mounting/hardware validation beyond the committed test data is not represented as a measured result here.

## Documentation index

1. [Deliverable map](FRAME_ALIGNMENT.md)
2. [Algorithm and alternatives](ALGORITHM.md)
3. [Rotation conventions](ROTATION_CONVENTIONS.md)
4. [Status and confidence](STATUS_AND_CONFIDENCE.md)
5. [Downstream integration](INTEGRATION.md)

Module source: `member2_alignment/`.

```text
Phone IMU/GNSS → FrameAligner → vehicle-frame IMU → Members 1, 3, 5
```
