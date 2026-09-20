// Member 6 Navigation Cockpit HUD
// Integrates Member 1 ML Speed Estimator, SpeedGuard, Tunnel Outage Controller, and Leaflet Map

import React from "react";
import {
  MapMatchStatus,
  NavigationMode,
  NavigationState,
  RejectionReason,
} from "../types";
import { evaluateSpeed, rejectionLabel } from "../safety/SpeedGuard";
import { InteractiveMap } from "./InteractiveMap";
import {
  Compass,
  Radio,
  Gauge,
  MapPin,
  AlertTriangle,
  ShieldAlert,
  Zap,
  Activity,
  CheckCircle2,
  BrainCircuit,
  Timer,
  Layers,
  Sparkles,
  TrendingDown,
  Navigation,
} from "lucide-react";

interface NavigationHUDProps {
  navState: NavigationState;
  gnssAvailable: boolean;
  onToggleGnssBlackout: () => void;
  onTrigger700Regression: () => void;
  onClearInjection: () => void;
  gnssBlackout: boolean;
}

export const NavigationHUD: React.FC<NavigationHUDProps> = ({
  navState,
  gnssAvailable,
  onToggleGnssBlackout,
  onTrigger700Regression,
  onClearInjection,
  gnssBlackout,
}) => {
  const speedEval = evaluateSpeed(navState.speedMps);
  const isSpeedValid = speedEval.valid && speedEval.kmh !== null;
  const kmhFormatted = speedEval.kmh !== null ? speedEval.kmh.toFixed(1) : "--";

  const isDeadReckoning = navState.mode === NavigationMode.DEAD_RECKONING;
  const isFault = navState.mode === NavigationMode.FAULT;
  const isGnssDegraded = navState.mode === NavigationMode.GNSS_DEGRADED;

  // Heading calculation (0 deg = North, clockwise)
  const headingDeg = Math.round(((-navState.yawRad * 180) / Math.PI + 90 + 360) % 360);

  return (
    <div className="flex flex-col gap-5">
      {/* Top Warning Alert Banner if SpeedGuard rejected value */}
      {!speedEval.valid && speedEval.reason !== RejectionReason.NONE && (
        <div className="bg-[#ff1744]/15 border border-[#ff1744]/50 rounded-xl p-4 text-[#ff1744] flex items-center justify-between shadow-lg backdrop-blur-md animate-pulse">
          <div className="flex items-center gap-3">
            <ShieldAlert className="w-6 h-6 shrink-0 text-[#ff1744]" />
            <div>
              <div className="font-bold font-mono tracking-wide text-sm">
                SPEEDGUARD REFUSAL: {rejectionLabel(speedEval.reason)}
              </div>
              <div className="text-xs text-[#ff1744]/80 mt-0.5">
                Upstream speed value ({navState.speedMps} m/s) rejected by safety ceiling (&gt;55 m/s or invalid).
              </div>
            </div>
          </div>
          <button
            type="button"
            onClick={onClearInjection}
            className="px-3 py-1.5 bg-[#ff1744] hover:bg-[#ff1744]/90 text-white font-mono text-xs font-semibold rounded-lg transition-colors shrink-0 ml-3"
          >
            Reset Fault
          </button>
        </div>
      )}

      {/* Outage Active Notification Bar */}
      {isDeadReckoning && (
        <div className="bg-[#00e5ff]/10 border border-[#00e5ff]/40 rounded-xl p-4 text-[#00e5ff] flex flex-wrap items-center justify-between shadow-lg backdrop-blur-md">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-lg bg-[#00e5ff]/20 flex items-center justify-center shrink-0">
              <BrainCircuit className="w-5 h-5 text-[#00e5ff] animate-pulse" />
            </div>
            <div>
              <div className="font-bold font-mono text-sm flex items-center gap-2">
                <span>GNSS OUTAGE DETECTED — INTELLIGENT DEAD RECKONING ACTIVE</span>
                <span className="px-2 py-0.5 rounded bg-[#00e5ff]/20 text-[10px] font-semibold uppercase">
                  final.production.onnx
                </span>
              </div>
              <div className="text-xs text-[#9aa0a6] mt-0.5">
                Member 1 ML model is estimating vehicle forward speed from 100 Hz IMU vibration patterns. Fusing into Member 3 8-State EKF.
              </div>
            </div>
          </div>

          <div className="flex items-center gap-6 mt-3 sm:mt-0 font-mono text-xs">
            <div>
              <span className="text-[#9aa0a6] block text-[10px]">OUTAGE TIME</span>
              <span className="text-white font-bold text-sm">
                {navState.outageDurationSec.toFixed(1)}s
              </span>
            </div>
            <div>
              <span className="text-[#9aa0a6] block text-[10px]">DRIFT SAVED</span>
              <span className="text-[#00e676] font-bold text-sm">
                {navState.driftErrorMeters.toFixed(1)}m
              </span>
            </div>
          </div>
        </div>
      )}

      {/* Main Grid: Left interactive Map, Right Cockpit Controls & ML Telemetry */}
      <div className="grid grid-cols-1 xl:grid-cols-12 gap-5">
        {/* Left Column: Interactive Map & Live Navigation Overview (7 cols) */}
        <div className="xl:col-span-7 flex flex-col gap-4">
          <InteractiveMap navState={navState} gnssAvailable={gnssAvailable} />

          {/* Outage & Safety Test Strip */}
          <div className="bg-[#0e1318] border border-[#1f2a33] rounded-xl p-4 flex flex-wrap items-center justify-between gap-3 shadow-lg">
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={onToggleGnssBlackout}
                className={`px-4 py-2.5 rounded-xl font-mono text-xs font-bold transition-all shadow-md flex items-center gap-2 ${
                  gnssBlackout
                    ? "bg-[#00e676] text-[#070b0e] hover:bg-[#00e676]/90"
                    : "bg-[#ff1744] text-white hover:bg-[#ff1744]/90"
                }`}
              >
                <Radio className="w-4 h-4" />
                {gnssBlackout ? "RESTORE GNSS (EXIT OUTAGE)" : "CUT GNSS (TEST OUTAGE)"}
              </button>

              <button
                type="button"
                onClick={onTrigger700Regression}
                className="px-3.5 py-2.5 rounded-xl bg-[#141b22] hover:bg-[#1f2a33] text-[#ff8a80] border border-[#ff1744]/30 font-mono text-xs font-semibold transition-all flex items-center gap-1.5"
                title="Inject 700 km/h (194.4 m/s) speed anomaly to verify SpeedGuard safety refusal"
              >
                <AlertTriangle className="w-3.5 h-3.5 text-[#ff1744]" />
                Test SpeedGuard (700 km/h)
              </button>
            </div>

            <div className="text-[11px] font-mono text-[#9aa0a6]">
              Corridor: <span className="text-white font-bold">NH16 Simhachalam Tunnel</span>
            </div>
          </div>
        </div>

        {/* Right Column: Speedometer, ML Speed Estimator, EKF & Map-Match (5 cols) */}
        <div className="xl:col-span-5 flex flex-col gap-4">
          {/* Speedometer & Navigation Mode Card */}
          <div className="bg-[#0e1318] border border-[#1f2a33] rounded-xl p-5 shadow-lg relative overflow-hidden">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2 text-[#9aa0a6] text-xs font-mono tracking-wider">
                <Gauge className="w-4 h-4 text-[#00e5ff]" />
                <span>VEHICLE COCKPIT SPEED</span>
              </div>
              <span
                className={`text-[11px] font-mono font-bold px-2 py-0.5 rounded ${
                  isSpeedValid
                    ? "bg-[#00e676]/15 text-[#00e676] border border-[#00e676]/30"
                    : "bg-[#ff1744]/15 text-[#ff1744] border border-[#ff1744]/30"
                }`}
              >
                {isSpeedValid ? "SPEEDGUARD: PASS" : "SPEEDGUARD: REFUSED"}
              </span>
            </div>

            <div className="my-5 text-center">
              <div className="flex items-baseline justify-center gap-2 font-mono">
                <span
                  className={`text-6xl font-black tracking-tight ${
                    isSpeedValid ? "text-white" : "text-[#ff1744]"
                  }`}
                >
                  {kmhFormatted}
                </span>
                <span className="text-xl font-bold text-[#9aa0a6]">KM/H</span>
              </div>
              <div className="text-xs font-mono text-[#9aa0a6] mt-1">
                {isSpeedValid && navState.speedMps !== null
                  ? `${navState.speedMps.toFixed(2)} m/s forward velocity`
                  : "Velocity reading withheld by safety guard"}
              </div>
            </div>

            {/* Navigation Mode Bar */}
            <div className="grid grid-cols-3 gap-2 pt-3 border-t border-[#1f2a33] text-center font-mono text-xs">
              <div className="bg-[#141b22] p-2 rounded-lg border border-[#1f2a33]">
                <span className="text-[10px] text-[#9aa0a6] block">NAV MODE</span>
                <span
                  className={`font-bold ${
                    isDeadReckoning
                      ? "text-[#00e5ff]"
                      : isFault
                      ? "text-[#ff1744]"
                      : isGnssDegraded
                      ? "text-[#ff9100]"
                      : "text-[#00e676]"
                  }`}
                >
                  {navState.mode}
                </span>
              </div>
              <div className="bg-[#141b22] p-2 rounded-lg border border-[#1f2a33]">
                <span className="text-[10px] text-[#9aa0a6] block">HEADING</span>
                <span className="text-white font-bold">{headingDeg}°</span>
              </div>
              <div className="bg-[#141b22] p-2 rounded-lg border border-[#1f2a33]">
                <span className="text-[10px] text-[#9aa0a6] block">CONFIDENCE</span>
                <span className="text-[#00e676] font-bold">
                  {(navState.confidence * 100).toFixed(0)}%
                </span>
              </div>
            </div>
          </div>

          {/* Member 1: Deep Learning Speed Estimator Card */}
          <div className="bg-[#0e1318] border border-[#1f2a33] rounded-xl p-5 shadow-lg flex flex-col gap-3">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2 text-white font-mono text-xs font-bold">
                <BrainCircuit className="w-4 h-4 text-[#00e5ff]" />
                <span>MEMBER 1: ML VELOCITY ESTIMATOR</span>
              </div>
              <span
                className={`text-[10px] font-mono px-2 py-0.5 rounded font-semibold ${
                  isDeadReckoning
                    ? "bg-[#00e5ff]/20 text-[#00e5ff] border border-[#00e5ff]/40 animate-pulse"
                    : "bg-[#1f2a33] text-[#9aa0a6]"
                }`}
              >
                {isDeadReckoning ? "ACTIVE INFERENCE" : "STANDBY (GNSS AVAIL)"}
              </span>
            </div>

            <div className="bg-[#141b22] rounded-lg p-3 border border-[#1f2a33] flex flex-col gap-2 font-mono text-xs">
              <div className="flex justify-between items-center">
                <span className="text-[#9aa0a6]">ONNX Model:</span>
                <span className="text-[#00e5ff] font-semibold">final.production.onnx</span>
              </div>
              <div className="flex justify-between items-center">
                <span className="text-[#9aa0a6]">Architecture:</span>
                <span className="text-white">Causal CNN (27,266 params)</span>
              </div>
              <div className="flex justify-between items-center">
                <span className="text-[#9aa0a6]">IMU Input Window:</span>
                <span className="text-white">200 samples @ 100 Hz (2.0s)</span>
              </div>
              <div className="flex justify-between items-center">
                <span className="text-[#9aa0a6]">Predicted Speed (v_x):</span>
                <span className="text-[#00e676] font-bold">
                  {navState.mlSpeedMps !== null
                    ? `${(navState.mlSpeedMps * 3.6).toFixed(1)} km/h (${navState.mlSpeedMps.toFixed(2)} m/s)`
                    : "--"}
                </span>
              </div>
              <div className="flex justify-between items-center">
                <span className="text-[#9aa0a6]">Predictive Variance (σ²):</span>
                <span className="text-white">
                  {navState.mlVarianceM2s2 !== null
                    ? `${navState.mlVarianceM2s2.toFixed(3)} m²/s²`
                    : "--"}
                </span>
              </div>
              <div className="flex justify-between items-center">
                <span className="text-[#9aa0a6]">Model Confidence:</span>
                <span className="text-[#00e5ff] font-bold">
                  {navState.mlConfidence !== null
                    ? `${(navState.mlConfidence * 100).toFixed(1)}%`
                    : "--"}
                </span>
              </div>
              <div className="flex justify-between items-center">
                <span className="text-[#9aa0a6]">Inference Latency:</span>
                <span className="text-[#9aa0a6]">
                  {navState.mlInferenceTimeMs !== null
                    ? `${navState.mlInferenceTimeMs.toFixed(2)} ms`
                    : "< 2.5 ms"}
                </span>
              </div>
            </div>

            <div className="text-[11px] text-[#9aa0a6] leading-relaxed">
              <strong>Dead Reckoning Role:</strong> During GNSS blackout, double-integrating noisy accelerometer biases causes rapid cubic position divergence. The ML model infers metric forward speed from chassis vibration harmonics, feeding the Member 3 EKF to bound velocity drift.
            </div>
          </div>

          {/* Member 2, Member 3 & Member 4 Fusion & Map Match Card */}
          <div className="bg-[#0e1318] border border-[#1f2a33] rounded-xl p-4 shadow-lg grid grid-cols-3 gap-2.5 text-xs font-mono">
            {/* Member 2 Frame Aligner */}
            <div className="bg-[#141b22] p-2.5 rounded-lg border border-[#1f2a33] flex flex-col gap-1">
              <div className="flex items-center gap-1.5 text-white font-bold text-[10px]">
                <Compass className="w-3.5 h-3.5 text-[#00e5ff]" />
                <span>M2: ALIGNER</span>
              </div>
              <div className="text-[#9aa0a6] text-[10px]">Phone → Vehicle</div>
              <div className="flex justify-between mt-0.5 text-[10px]">
                <span className="text-[#9aa0a6]">Status:</span>
                <span className="text-[#00e676] font-bold">ALIGNED</span>
              </div>
              <div className="flex justify-between text-[10px]">
                <span className="text-[#9aa0a6]">Conf:</span>
                <span className="text-white font-bold">
                  {((navState.alignmentConfidence ?? 0.92) * 100).toFixed(0)}%
                </span>
              </div>
            </div>

            {/* Member 3 Sensor Fusion */}
            <div className="bg-[#141b22] p-2.5 rounded-lg border border-[#1f2a33] flex flex-col gap-1">
              <div className="flex items-center gap-1.5 text-white font-bold text-[10px]">
                <Activity className="w-3.5 h-3.5 text-[#00e5ff]" />
                <span>M3: EKF</span>
              </div>
              <div className="text-[#9aa0a6] text-[10px]">8-State [N,E,V,Ψ,B]</div>
              <div className="flex justify-between mt-0.5 text-[10px]">
                <span className="text-[#9aa0a6]">NHC:</span>
                <span className="text-[#00e676]">Vy≈0</span>
              </div>
              <div className="flex justify-between text-[10px]">
                <span className="text-[#9aa0a6]">Speed:</span>
                <span className={isDeadReckoning ? "text-[#00e5ff]" : "text-[#9aa0a6]"}>
                  {isDeadReckoning ? "ML ONNX" : "GNSS Dop"}
                </span>
              </div>
            </div>

            {/* Member 4 Map Matching */}
            <div className="bg-[#141b22] p-2.5 rounded-lg border border-[#1f2a33] flex flex-col gap-1">
              <div className="flex items-center gap-1.5 text-white font-bold text-[10px]">
                <MapPin className="w-3.5 h-3.5 text-[#00e5ff]" />
                <span>M4: HMM</span>
              </div>
              <div className="text-[#9aa0a6] text-[10px] truncate" title={navState.matchedRoadName || "NH16"}>
                {navState.matchedRoadName || "NH16"}
              </div>
              <div className="flex justify-between mt-0.5 text-[10px]">
                <span className="text-[#9aa0a6]">Snap:</span>
                <span
                  className={
                    navState.mapMatchStatus === MapMatchStatus.MATCHED
                      ? "text-[#00e676]"
                      : "text-[#ff9100]"
                  }
                >
                  {navState.mapMatchStatus}
                </span>
              </div>
              <div className="flex justify-between text-[10px]">
                <span className="text-[#9aa0a6]">Offset:</span>
                <span className="text-white">
                  {navState.distanceToRoadMeters !== null
                    ? `${navState.distanceToRoadMeters.toFixed(1)}m`
                    : "0.8m"}
                </span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
