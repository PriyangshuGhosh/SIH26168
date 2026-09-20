// System Diagnostics & Sensor Telemetry View
// Displays live Member 1 ML inference telemetry, 8-state EKF, 6-bit validity mask, and sensor stats

import React, { useState } from "react";
import { NavigationMode, NavigationState, SensorStats, VALIDITY } from "../types";
import {
  Activity,
  Cpu,
  Radio,
  ShieldCheck,
  Zap,
  CheckCircle,
  XCircle,
  Clock,
  Layers,
  Binary,
  BrainCircuit,
  Play,
  RotateCcw,
} from "lucide-react";

interface DiagnosticsViewProps {
  navState: NavigationState;
  sensorStats: SensorStats;
  gnssAvailable: boolean;
}

export const DiagnosticsView: React.FC<DiagnosticsViewProps> = ({
  navState,
  sensorStats,
  gnssAvailable,
}) => {
  const [testResult, setTestResult] = useState<string | null>(null);
  const [testingModel, setTestingModel] = useState(false);

  const isStreaming = sensorStats.accelHz > 15;

  const validityBits = [
    { label: "POSITION (bit 0)", valid: (navState.validity & VALIDITY.POSITION) !== 0 },
    { label: "VELOCITY (bit 1)", valid: (navState.validity & VALIDITY.VELOCITY) !== 0 },
    { label: "YAW (bit 2)", valid: (navState.validity & VALIDITY.YAW) !== 0 },
    { label: "SPEED (bit 3)", valid: (navState.validity & VALIDITY.SPEED) !== 0 },
    { label: "CONFIDENCE (bit 4)", valid: (navState.validity & VALIDITY.CONFIDENCE) !== 0 },
    { label: "MAP_MATCH (bit 5)", valid: (navState.validity & VALIDITY.MAP_MATCH) !== 0 },
  ];

  const pipelineStages = [
    { name: "Phone IMU / GNSS", desc: "100 Hz Accel/Gyro + 1 Hz GNSS Stream", status: isStreaming ? "ACTIVE" : "IDLE" },
    { name: "M2: Frame Aligner", desc: "Phone → Vehicle Gravity Alignment", status: "ACTIVE" },
    { name: "M1: AI Speed Model", desc: "final.production.onnx (Causal CNN)", status: navState.mlModelActive ? "ACTIVE INFERENCE" : "LOADED (READY)" },
    { name: "M3: EKF Sensor Fusion", desc: "8-State Loose-Coupled Filter + NHC", status: "ACTIVE" },
    { name: "M4: HMM Map Matcher", desc: "Offline Viterbi .roadpack Matcher", status: "ACTIVE" },
    { name: "M5: Native Edge Engine", desc: "C ABI idr_feed_imu / idr_feed_gnss", status: "ACTIVE" },
    { name: "M6: Cockpit HUD UI", desc: "SpeedGuard Refusal + Dark Map Display", status: "ACTIVE" },
  ];

  const runManualMlInference = async () => {
    setTestingModel(true);
    setTestResult(null);
    try {
      // Send 200 synthetic samples
      const samples = Array.from({ length: 200 }, (_, i) => ({
        ax: 0.15 + Math.sin(i * 0.1) * 0.2,
        ay: 0.05,
        az: 9.81 + Math.cos(i * 0.2) * 0.1,
        gx: 0.01,
        gy: 0.01,
        gz: 0.02,
      }));

      const res = await fetch("/api/ml/predict", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ samples }),
      });

      if (res.ok) {
        const data = await res.json();
        setTestResult(
          `Prediction Success: ${(data.velocity_mps * 3.6).toFixed(1)} km/h (${data.velocity_mps.toFixed(2)} m/s), σ²=${data.velocity_variance_m2s2.toFixed(3)}, Conf=${(data.confidence * 100).toFixed(1)}%, Latency=${data.inference_time_ms.toFixed(2)} ms`
        );
      } else {
        setTestResult("Inference test returned error: " + res.statusText);
      }
    } catch (err: any) {
      setTestResult("Inference test failed: " + err.message);
    } finally {
      setTestingModel(false);
    }
  };

  return (
    <div className="flex flex-col gap-5">
      <div>
        <h2 className="text-xl font-bold font-mono tracking-tight text-[#e1e7ec]">
          SYSTEM DIAGNOSTICS & TELEMETRY
        </h2>
        <p className="text-xs text-[#9aa0a6] font-mono mt-1">
          Real-time Member 1 ML inference metrics, 8-state EKF fusion, and engine validity bitmask
        </p>
      </div>

      {/* Member 1 ONNX Model Runtime Card */}
      <div className="bg-[#0e1318] border border-[#1f2a33] rounded-xl p-5 shadow-lg flex flex-col gap-4">
        <div className="flex flex-wrap items-center justify-between gap-3 pb-3 border-b border-[#1f2a33]">
          <div className="flex items-center gap-2">
            <BrainCircuit className="w-5 h-5 text-[#00e5ff]" />
            <div>
              <span className="font-mono font-bold text-sm text-[#e1e7ec]">
                MEMBER 1: ONNX RUNTIME ENGINE
              </span>
              <span className="text-xs text-[#00e5ff] font-mono block">
                final.production.onnx (134 KB, 27,266 parameters)
              </span>
            </div>
          </div>

          <div className="flex items-center gap-3">
            <button
              type="button"
              onClick={runManualMlInference}
              disabled={testingModel}
              className="px-3 py-1.5 rounded-lg bg-[#00e5ff]/20 hover:bg-[#00e5ff]/30 text-[#00e5ff] border border-[#00e5ff]/40 font-mono text-xs font-semibold transition-colors flex items-center gap-1.5"
            >
              <Play className="w-3.5 h-3.5" />
              {testingModel ? "Running ONNX..." : "Test Single Inference"}
            </button>
            <span className="px-2.5 py-0.5 rounded-full text-xs font-mono font-bold bg-[#00e676]/15 text-[#00e676] border border-[#00e676]/30">
              OPERATIONAL
            </span>
          </div>
        </div>

        {testResult && (
          <div className="p-3 bg-[#141b22] border border-[#00e5ff]/30 rounded-lg text-xs font-mono text-[#00e5ff]">
            {testResult}
          </div>
        )}

        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 font-mono text-xs">
          <div className="bg-[#141b22] p-3 rounded-lg border border-[#1f2a33]">
            <span className="text-[#9aa0a6] text-[10px] block">TOTAL INFERENCES</span>
            <span className="text-white font-bold text-sm">
              {navState.mlInferenceCount}
            </span>
          </div>
          <div className="bg-[#141b22] p-3 rounded-lg border border-[#1f2a33]">
            <span className="text-[#9aa0a6] text-[10px] block">LAST LATENCY</span>
            <span className="text-[#00e5ff] font-bold text-sm">
              {navState.mlInferenceTimeMs !== null ? `${navState.mlInferenceTimeMs.toFixed(2)} ms` : "--"}
            </span>
          </div>
          <div className="bg-[#141b22] p-3 rounded-lg border border-[#1f2a33]">
            <span className="text-[#9aa0a6] text-[10px] block">PREDICTED SPEED</span>
            <span className="text-[#00e676] font-bold text-sm">
              {navState.mlSpeedMps !== null ? `${(navState.mlSpeedMps * 3.6).toFixed(1)} km/h` : "--"}
            </span>
          </div>
          <div className="bg-[#141b22] p-3 rounded-lg border border-[#1f2a33]">
            <span className="text-[#9aa0a6] text-[10px] block">MODEL CONFIDENCE</span>
            <span className="text-[#00e5ff] font-bold text-sm">
              {navState.mlConfidence !== null ? `${(navState.mlConfidence * 100).toFixed(1)}%` : "--"}
            </span>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {/* Sensor Pipeline Card */}
        <div className="bg-[#0e1318] border border-[#1f2a33] rounded-xl p-5 shadow-lg">
          <div className="flex items-center justify-between pb-3 border-b border-[#1f2a33]">
            <div className="flex items-center gap-2 text-[#9aa0a6] text-xs font-mono font-bold tracking-wider">
              <Activity className="w-4 h-4 text-[#00e5ff]" />
              <span>SENSOR PIPELINE</span>
            </div>
            <span
              className={`px-2.5 py-0.5 rounded-full text-xs font-mono font-bold border ${
                isStreaming
                  ? "bg-[#00e676]/15 text-[#00e676] border-[#00e676]/30"
                  : "bg-[#ffab00]/15 text-[#ffab00] border-[#ffab00]/30"
              }`}
            >
              {isStreaming ? "STREAMING (50/100 Hz)" : "STANDBY"}
            </span>
          </div>

          <div className="divide-y divide-[#1b2631] font-mono text-xs mt-2">
            <div className="py-2.5 flex items-center justify-between">
              <span className="text-[#9aa0a6]">ACCELEROMETER FREQ</span>
              <span className="font-bold text-[#00e5ff]">{sensorStats.accelHz.toFixed(1)} Hz</span>
            </div>
            <div className="py-2.5 flex items-center justify-between">
              <span className="text-[#9aa0a6]">GYROSCOPE FREQ</span>
              <span className="font-bold text-[#00e5ff]">{sensorStats.gyroHz.toFixed(1)} Hz</span>
            </div>
            <div className="py-2.5 flex items-center justify-between">
              <span className="text-[#9aa0a6]">EMITTED PAIRED FREQ</span>
              <span className="font-bold text-[#00e676]">{sensorStats.emittedHz.toFixed(1)} Hz</span>
            </div>
            <div className="py-2.5 flex items-center justify-between">
              <span className="text-[#9aa0a6]">LAST PAIRING Δ</span>
              <span className="font-bold text-[#e1e7ec]">{sensorStats.lastPairingDeltaMs.toFixed(2)} ms</span>
            </div>
            <div className="py-2.5 flex items-center justify-between">
              <span className="text-[#9aa0a6]">TIMESTAMP REGRESSIONS</span>
              <span className={`font-bold ${sensorStats.droppedRegression > 0 ? "text-[#ffab00]" : "text-[#9aa0a6]"}`}>
                {sensorStats.droppedRegression}
              </span>
            </div>
          </div>
        </div>

        {/* 6-Bit Engine Validity Mask Card */}
        <div className="bg-[#0e1318] border border-[#1f2a33] rounded-xl p-5 shadow-lg">
          <div className="flex items-center justify-between pb-3 border-b border-[#1f2a33]">
            <div className="flex items-center gap-2 text-[#9aa0a6] text-xs font-mono font-bold tracking-wider">
              <Binary className="w-4 h-4 text-[#00e5ff]" />
              <span>ENGINE VALIDITY BITMASK</span>
            </div>
            <span className="font-mono text-xs text-[#00e5ff] font-bold">
              0b{navState.validity.toString(2).padStart(6, "0")} (0x{navState.validity.toString(16).toUpperCase()})
            </span>
          </div>

          <div className="grid grid-cols-2 gap-2 mt-3 font-mono text-xs">
            {validityBits.map((b) => (
              <div
                key={b.label}
                className={`p-2.5 rounded-lg border flex items-center justify-between ${
                  b.valid
                    ? "bg-[#00e676]/10 border-[#00e676]/30 text-[#00e676]"
                    : "bg-[#141b22] border-[#1f2a33] text-[#9aa0a6]"
                }`}
              >
                <span className="text-[11px] font-semibold">{b.label}</span>
                {b.valid ? (
                  <CheckCircle className="w-4 h-4 text-[#00e676]" />
                ) : (
                  <XCircle className="w-4 h-4 text-[#9aa0a6]" />
                )}
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* End-to-End Pipeline Stage Status */}
      <div className="bg-[#0e1318] border border-[#1f2a33] rounded-xl p-5 shadow-lg">
        <div className="pb-3 border-b border-[#1f2a33]">
          <span className="font-mono font-bold text-xs text-[#9aa0a6] tracking-wider">
            6-MEMBER NAVIGATION ENGINE ARCHITECTURE
          </span>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3 mt-3 font-mono text-xs">
          {pipelineStages.map((stage) => (
            <div
              key={stage.name}
              className="bg-[#141b22] p-3 rounded-lg border border-[#1f2a33] flex flex-col justify-between"
            >
              <div>
                <div className="font-bold text-white text-xs">{stage.name}</div>
                <div className="text-[11px] text-[#9aa0a6] mt-0.5">{stage.desc}</div>
              </div>
              <div className="mt-2 pt-2 border-t border-[#1f2a33]/60 flex justify-between items-center text-[10px]">
                <span className="text-[#9aa0a6]">STATUS:</span>
                <span className="text-[#00e5ff] font-bold">{stage.status}</span>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};
