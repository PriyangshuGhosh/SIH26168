# SIH26168 — Vision + Depth Differentiator

## Motivation

The baseline SIH26168 system uses phone IMU, AI speed estimation, EKF/UKF fusion, offline HMM map matching, and a native mobile engine. To stand out, we will investigate an additional camera-based sensing channel for GNSS-denied navigation.

The proposed differentiator is **confidence-aware visual-inertial-depth navigation**: camera-derived scene geometry and visual motion become an auxiliary measurement source rather than replacing the inertial navigation stack.

## Critical technical point

A monocular depth model does **not** directly solve metric localization. Monocular depth has scale ambiguity. The useful contribution is to combine scene geometry and visual motion with IMU/vehicle constraints, which provide metric information and temporal stability.

Therefore, the first implementation should focus on:

1. Lightweight monocular depth inference on selected frames.
2. Optical-flow / visual-odometry features for relative camera motion.
3. Visual measurement confidence from image quality and motion consistency.
4. Confidence-gated fusion with the existing EKF.
5. Automatic fallback to IMU + AI speed when vision is unreliable.

## Proposed architecture

```text
Camera -> depth + visual motion -> confidence -> EKF

Phone IMU -> FrameAligner -> AI Speed -> EKF -> HMM Map Matching
                                      ^
                                      |
                               GNSS when available

EKF -> Native C++ Engine -> Mobile UI
```

## Sensor roles

| Source | Main role | Failure handled by |
|---|---|---|
| IMU | High-rate dynamics | AI speed, EKF constraints |
| AI speed | Longitudinal speed prior | IMU + visual/map evidence |
| Camera/depth | Scene geometry + visual motion | IMU + AI speed |
| GNSS | Absolute correction when available | Dead reckoning |
| Offline map | Road topology / geometric prior | EKF trajectory |

## Confidence gating

Vision must not be trusted equally in every scene. Potential quality indicators include feature count/distribution, optical-flow consistency, image blur, brightness/exposure, frame-to-frame motion consistency, dynamic-object contamination, and depth uncertainty.

```text
if visual_quality_good:
    use visual measurement with estimated covariance
elif visual_quality_degraded:
    down-weight visual measurement
else:
    reject visual measurement
    continue IMU + AI speed + EKF + map matching
```

## Experimental protocol

Run an A/B comparison using identical recorded trajectories and GNSS-outage intervals.

**Baseline:** `IMU + AI Speed + EKF + NHC + HMM Map Matching`

**Enhanced:** `Baseline + Camera Visual/Depth Measurement`

Report position error, drift rate (m/min), heading error, speed MAE/RMSE, 50th/95th percentile position error, outage duration tolerated, inference latency, CPU/RAM usage, battery impact, and robustness under turns, stops, blur, low texture and low light.

## Success criterion

Retain the differentiator only if the enhanced system produces a measurable improvement over the baseline without unacceptable mobile compute, latency, memory, or battery cost. Do not claim accuracy improvement before the A/B experiment is complete.

## Demo narrative

> **SIH26168 is not dependent on a single sensor. During GNSS loss, it dynamically combines inertial dynamics, learned kinematics, visual scene geometry, and road-network constraints, while confidence-gating unreliable measurements and degrading gracefully when a modality fails.**

This is stronger than presenting depth as a standalone model feature.

## Initial implementation priority

1. Camera capture + synchronized timestamps.
2. Lightweight depth feasibility benchmark.
3. Visual-motion baseline.
4. Confidence estimation.
5. EKF visual measurement integration.
6. Baseline vs enhanced benchmark.
7. Native C++ integration.
8. Mobile demo instrumentation.

Do not begin with a large depth model or full end-to-end visual localization. Establish whether the visual signal actually reduces drift first.
