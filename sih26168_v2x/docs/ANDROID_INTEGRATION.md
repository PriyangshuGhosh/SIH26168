# Android integration

**DESIGNED, NOT IMPLEMENTED, NOT VALIDATED.**

```text
Android app  →  (future adapter: permissions, lifecycle, socket)
                     ↓
                 NormalizedV2XMessage
                     ↓
                 V2XCore (this C++ library)
                     ↓
                 optional EKF measurement
```

The core stays platform-independent. Do not put radio code in fusion.

`kAndroidV2XStatus = DESIGNED_NOT_IMPLEMENTED_MODE_A_SIMULATION_ONLY`
