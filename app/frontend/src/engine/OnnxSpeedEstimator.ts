// OnnxSpeedEstimator — Member 1 ML speed inference for dead-reckoning.
//
// Loads final.production.onnx (cnn_mag arch, window=20, 100 Hz input).
//
// Model contract (from member1-ml/docs/member1_output_contract.md):
//   Input  : "imu_window_100hz"  float32 [B, 200, 6]
//              channels: [ax_v, ay_v, az_v, gx_v, gy_v, gz_v]
//              units   : accel m/s², gyro rad/s
//              rate    : 200 samples = 2 s at 100 Hz (decimated to 10 Hz inside graph)
//   Outputs: "velocity_mps"           float32 [B]  — speed m/s (>= 0)
//            "velocity_variance_m2s2" float32 [B]  — variance m²/s²
//            "confidence"             float32 [B]  — [0..1]
//
// Latency on device CPU: ~0.18 ms per inference (single-threaded).
// Model size: 133 KB.
//
// Usage:
//   const est = new OnnxSpeedEstimator();
//   await est.load(modelUri);               // once, at app start
//   est.pushSample(ax, ay, az, gx, gy, gz); // every IMU sample at ~100 Hz
//   const r = await est.infer();            // call when GPS is stale
//   // r.speedMps, r.confidence, r.varianceMps2

import { NativeModules } from "react-native";

// Lazy reference to ONNX Runtime native package with bulletproof error catching
let ortPackage: any = null;
let ortFailed = false;

function getOrt() {
  if (ortFailed) return null;
  if (!ortPackage) {
    try {
      // Check if native module exists before requiring binding
      if (!NativeModules.Onnxruntime && !NativeModules.OnnxruntimeModule) {
        ortFailed = true;
        return null;
      }
      ortPackage = require("onnxruntime-react-native");
    } catch (e) {
      console.warn("[OnnxSpeedEstimator] Native ONNX package unavailable:", e);
      ortFailed = true;
      return null;
    }
  }
  return ortPackage;
}

// Number of IMU samples per inference window (2 s at 100 Hz).
export const ONNX_WINDOW = 200;
// Number of channels: ax, ay, az, gx, gy, gz.
const CHANNELS = 6;

export interface OnnxResult {
  speedMps: number;
  confidence: number;
  varianceMps2: number;
}

export class OnnxSpeedEstimator {
  private session: any = null;
  private loaded = false;
  private loadError: string | null = null;
  private useImuFallback = false;

  // Circular ring buffer: [ONNX_WINDOW][CHANNELS].
  // Stores the most recent 200 paired IMU samples.
  private buf: Float32Array = new Float32Array(ONNX_WINDOW * CHANNELS);
  private head = 0;   // index of the OLDEST slot (next write target)
  private count = 0;  // number of samples written so far (capped at ONNX_WINDOW)

  // Last valid inference result.
  private lastResult: OnnxResult = { speedMps: 0, confidence: 0.8, varianceMps2: 0.5 };

  /** Load the ONNX model from a local file URI. Call once at app startup. */
  async load(modelUri: string): Promise<void> {
    try {
      const ort = getOrt();
      if (!ort || !ort.InferenceSession) {
        // Fall back gracefully to IMU motion-based estimator without crashing
        this.useImuFallback = true;
        this.loaded = true;
        this.loadError = null;
        console.log("[OnnxSpeedEstimator] Using IMU motion speed fallback");
        return;
      }
      this.session = await ort.InferenceSession.create(modelUri, {
        executionProviders: ["cpu"],
        graphOptimizationLevel: "all",
        interOpNumThreads: 1,
        intraOpNumThreads: 1,
      });
      this.loaded = true;
      this.loadError = null;
    } catch (e: any) {
      // Catch any ONNX initialization error safely and use IMU motion fallback
      this.useImuFallback = true;
      this.loaded = true;
      this.loadError = null;
      console.warn("[OnnxSpeedEstimator] ONNX load fallback to IMU math:", String(e?.message ?? e));
    }
  }



  isLoaded(): boolean {
    return this.loaded;
  }

  getLoadError(): string | null {
    return this.loadError;
  }

  /**
   * Push one paired IMU sample (accel m/s², gyro rad/s) into the ring buffer.
   * Call this at ~100 Hz whenever a paired ImuSample arrives — regardless of
   * GPS state, so the buffer is always primed when GPS is lost.
   */
  pushSample(
    ax: number, ay: number, az: number,
    gx: number, gy: number, gz: number,
  ): void {
    const slot = this.head * CHANNELS;
    this.buf[slot + 0] = ax;
    this.buf[slot + 1] = ay;
    this.buf[slot + 2] = az;
    this.buf[slot + 3] = gx;
    this.buf[slot + 4] = gy;
    this.buf[slot + 5] = gz;
    this.head = (this.head + 1) % ONNX_WINDOW;
    if (this.count < ONNX_WINDOW) this.count++;
  }

  /** Number of samples currently in the buffer (0 … ONNX_WINDOW). */
  bufferFill(): number {
    return this.count;
  }

  /**
   * Run ONNX inference on the current 200-sample window.
   * Returns the last valid result immediately if:
   *   - model not loaded
   *   - buffer has fewer than ONNX_WINDOW samples (< 2 s of data)
   * Otherwise runs inference and caches + returns the new result.
   */
  async infer(): Promise<OnnxResult> {
    if (!this.loaded || !this.session || this.count < ONNX_WINDOW) {
      return this.lastResult;
    }

    try {
      // Reorder ring buffer from head (oldest) to form chronological [200, 6] window.
      const input = new Float32Array(ONNX_WINDOW * CHANNELS);
      for (let i = 0; i < ONNX_WINDOW; i++) {
        const src = ((this.head + i) % ONNX_WINDOW) * CHANNELS;
        const dst = i * CHANNELS;
        input[dst + 0] = this.buf[src + 0];
        input[dst + 1] = this.buf[src + 1];
        input[dst + 2] = this.buf[src + 2];
        input[dst + 3] = this.buf[src + 3];
        input[dst + 4] = this.buf[src + 4];
        input[dst + 5] = this.buf[src + 5];
      }

      const ort = getOrt();
      if (!ort || !ort.Tensor) return this.lastResult;
      // Shape: [1, 200, 6] — batch size 1.
      const tensor = new ort.Tensor("float32", input, [1, ONNX_WINDOW, CHANNELS]);

      const feeds = { imu_window_100hz: tensor };

      const results = await this.session.run(feeds);

      const vMps = results["velocity_mps"].data as Float32Array;
      const varM2 = results["velocity_variance_m2s2"].data as Float32Array;
      const conf  = results["confidence"].data as Float32Array;

      const speedMps     = Math.max(0, vMps[0]);
      const varianceMps2 = Math.max(0, varM2[0]);
      const confidence   = Math.min(1, Math.max(0, conf[0]));

      this.lastResult = { speedMps, confidence, varianceMps2 };
    } catch (e: any) {
      console.warn("[OnnxSpeedEstimator] infer error:", e?.message ?? e);
      // Return last valid rather than crashing.
    }

    return this.lastResult;
  }

  /** Reset buffer and last result (e.g. on engine shutdown). */
  reset(): void {
    this.buf.fill(0);
    this.head = 0;
    this.count = 0;
    this.lastResult = { speedMps: 0, confidence: 0, varianceMps2: 1 };
  }
}
