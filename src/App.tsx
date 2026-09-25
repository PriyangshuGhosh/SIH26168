// Main Application Entry Component
// Connects Member 1 (ML Velocity Estimator), Member 3 (8-State EKF), Member 4 (HMM),
// Member 5 (Integrated Engine), Member 6 (Cockpit HUD), and Sensor Pipeline.

import React, { useEffect, useRef, useState } from "react";
import {
  emptyNavigationState,
  NavigationMode,
  NavigationState,
  SensorStats,
} from "./types";
import { MemberFiveEngine } from "./engine/MemberFiveEngine";
import { SensorPipeline } from "./sensors/SensorPipeline";
import { SyntheticDrive } from "./simulation/SyntheticDrive";
import { NavigationHUD } from "./components/NavigationHUD";
import { DiagnosticsView } from "./components/DiagnosticsView";
import { DocsView } from "./components/DocsView";
import { PhoneSensorService, RealSensorState } from "./sensors/PhoneSensorService";
import { SensorConnectModal } from "./components/SensorConnectModal";
import {
  Compass,
  Activity,
  BookOpen,
  RotateCcw,
  BrainCircuit,
  Smartphone,
} from "lucide-react";

type TabType = "NAV" | "DIAG" | "DOCS";

export default function App() {
  const [activeTab, setActiveTab] = useState<TabType>("NAV");
  const [navState, setNavState] = useState<NavigationState>(emptyNavigationState());
  const [sensorStats, setSensorStats] = useState<SensorStats>({
    accelHz: 50,
    gyroHz: 50,
    emittedHz: 50,
    lastPairingDeltaMs: 0.15,
    droppedRegression: 0,
    droppedStale: 0,
    droppedNoPair: 0,
    duplicatesSkipped: 0,
  });

  const [injectedSpeedMps, setInjectedSpeedMps] = useState<number | null>(null);
  const [gnssBlackout, setGnssBlackout] = useState(false);
  const [roadConstraintEnabled, setRoadConstraintEnabled] = useState(false);
  const [isSensorModalOpen, setIsSensorModalOpen] = useState(false);
  const [realSensorState, setRealSensorState] = useState<RealSensorState>(() => ({
    isSupported: typeof window !== "undefined" && ("DeviceMotionEvent" in window || "ondevicemotion" in window),
    permissionGranted: false,
    isStreaming: false,
    gpsActive: false,
    motionActive: false,
    error: null,
    rawImu: {
      ax: 0, ay: 0, az: 9.81, accelMag: 9.81,
      gx: 0, gy: 0, gz: 0,
      alpha: null, beta: null, gamma: null,
      rateHz: 0, eventCount: 0, lastUpdateMs: 0,
    },
    rawGps: {
      latitudeDeg: null, longitudeDeg: null, altitudeM: null,
      accuracyM: null, speedMps: null, headingDeg: null,
      available: false, lastFixMs: 0, error: null,
    },
  }));

  // Engine instances in refs
  const engineRef = useRef<MemberFiveEngine>(new MemberFiveEngine());
  const pipelineRef = useRef<SensorPipeline>(new SensorPipeline());
  const syntheticRef = useRef<SyntheticDrive>(new SyntheticDrive());
  const phoneSensorRef = useRef<PhoneSensorService | null>(null);

  // Initialize PhoneSensorService ref
  if (!phoneSensorRef.current) {
    phoneSensorRef.current = new PhoneSensorService(pipelineRef.current);
  }

  // Setup sensor loop and engine
  useEffect(() => {
    const engine = engineRef.current;
    const pipeline = pipelineRef.current;
    const synthetic = syntheticRef.current;

    engine.init();

    // Wire pipeline outputs to engine
    pipeline.onImu((imu) => {
      engine.feedImu(imu);
    });

    pipeline.onGnss((gnss) => {
      engine.feedGnss(gnss);
    });

    // Provide default road baseline if phone sensors are not yet streaming
    synthetic.onImu((imu) => {
      pipeline.feedPairedImu(imu);
    });

    synthetic.onGnss((gnss) => {
      pipeline.feedRawGnss(gnss);
    });

    synthetic.start();

    // Fast UI poll loop (10 Hz)
    const pollInterval = setInterval(() => {
      const state = engine.getState();
      setNavState(state);
      setSensorStats(pipeline.getStats());
      setGnssBlackout(synthetic.isInTunnel());
    }, 100);

    return () => {
      clearInterval(pollInterval);
      synthetic.stop();
      engine.shutdown();
    };
  }, []);

  const handleToggleRoadConstraint = () => {
    setRoadConstraintEnabled((enabled) => {
      const next = !enabled;
      engineRef.current.setRoadConstraintEnabled(next);
      return next;
    });
  };

  // 700 km/h regression test trigger
  const handleTrigger700Regression = () => {
    const absurdMps = 194.44; // ~700 km/h
    setInjectedSpeedMps(absurdMps);
    engineRef.current.setInjectedSpeed(absurdMps);
  };

  // Clear all injections
  const handleClearInjection = () => {
    setInjectedSpeedMps(null);
    setGnssBlackout(false);
    engineRef.current.setInjectedSpeed(null);
    engineRef.current.injectFault(false);
    engineRef.current.restoreGnssNow(17.7420, 83.2810, 16.67);
    syntheticRef.current.setGnssEnabled(true);
  };

  // Toggle GNSS blackout
  const handleToggleGnssBlackout = () => {
    const next = !gnssBlackout;
    setGnssBlackout(next);
    syntheticRef.current.setGnssEnabled(!next);
    if (next) {
      engineRef.current.triggerOutageNow();
    } else {
      engineRef.current.restoreGnssNow(navState.latitudeDeg, navState.longitudeDeg, 16.67);
    }
  };

  // Hardware Sensor Integration
  const handleConnectRealSensors = async () => {
    if (!phoneSensorRef.current) return;
    phoneSensorRef.current.onStateChange((st) => setRealSensorState(st));
    const ok = await phoneSensorRef.current.requestPermissionAndStart();
    if (ok) {
      // Stop synthetic drive when real phone hardware sensors take over
      syntheticRef.current.stop();
    }
  };

  const handleDisconnectRealSensors = () => {
    if (phoneSensorRef.current) {
      phoneSensorRef.current.stop();
      setRealSensorState(phoneSensorRef.current.getState());
    }
    // Resume synthetic fallback if user disconnected
    syntheticRef.current.start();
  };

  const isDeadReckoning = navState.mode === NavigationMode.DEAD_RECKONING;
  const isFault = navState.mode === NavigationMode.FAULT;

  return (
    <div className="min-h-screen bg-[#070b0e] text-[#e1e7ec] flex flex-col font-sans">
      {/* Top Application Header */}
      <header className="border-b border-[#1b2631] bg-[#090e13]/95 backdrop-blur-md sticky top-0 z-[2000] px-4 py-3">
        <div className="max-w-7xl mx-auto flex flex-col sm:flex-row sm:items-center justify-between gap-3">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-[#00e5ff] to-[#1e88e5] p-0.5 flex items-center justify-center shadow-lg shadow-[#00e5ff]/20">
              <div className="w-full h-full bg-[#070b0e] rounded-[10px] flex items-center justify-center">
                <Compass className="w-5 h-5 text-[#00e5ff]" />
              </div>
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h1 className="text-sm font-bold font-mono tracking-wider text-[#e1e7ec]">
                  SIH26168 EDGE NAVIGATION SYSTEM
                </h1>
                <span className="text-[10px] font-mono bg-[#1b2631] text-[#00e5ff] px-1.5 py-0.5 rounded font-bold">
                  ML OUTAGE ENGINE
                </span>
              </div>
              <p className="text-[11px] text-[#9aa0a6] font-mono">
                Intelligent GNSS-Denied Navigation · ONNX Speed Estimator (100 Hz) · 8-State EKF
              </p>
            </div>
          </div>

          {/* Status Indicators & Outage Counter */}
          <div className="flex items-center flex-wrap gap-2.5 font-mono text-xs">
            {isDeadReckoning && (
              <div className="flex items-center gap-1.5 px-3 py-1 rounded-full bg-[#00e5ff]/20 text-[#00e5ff] border border-[#00e5ff]/40 animate-pulse font-bold">
                <BrainCircuit className="w-3.5 h-3.5 text-[#00e5ff]" />
                <span>ML DEAD RECKONING ({navState.outageDurationSec.toFixed(0)}s)</span>
              </div>
            )}

            <div
              className={`flex items-center gap-1.5 px-3 py-1 rounded-full font-bold border ${
                isFault
                  ? "bg-[#ff1744]/20 text-[#ff1744] border-[#ff1744]/40"
                  : isDeadReckoning
                  ? "bg-[#00e5ff]/20 text-[#00e5ff] border-[#00e5ff]/40"
                  : "bg-[#00e676]/20 text-[#00e676] border-[#00e676]/40"
              }`}
            >
              <span className="w-2 h-2 rounded-full bg-current" />
              <span>{navState.mode}</span>
            </div>

            <div className="hidden sm:flex items-center gap-1.5 px-3 py-1 rounded-full bg-[#141d24] text-[#81d4fa] border border-[#1f2a33]">
              <span>REGION:</span>
              <span className="text-[#e1e7ec] font-bold">
                {navState.mapRegionId || "in-vizag"}
              </span>
            </div>

            {/* Hardware Sensor & PWA Install Button */}
            <button
              type="button"
              onClick={() => setIsSensorModalOpen(true)}
              className={`flex items-center gap-1.5 px-3 py-1 rounded-full font-mono font-bold transition-all border ${
                realSensorState.isStreaming
                  ? "bg-[#00e676]/20 text-[#00e676] border-[#00e676]/40 animate-pulse"
                  : "bg-[#00e5ff]/15 text-[#00e5ff] hover:bg-[#00e5ff]/25 border-[#00e5ff]/30"
              }`}
            >
              <Smartphone className="w-3.5 h-3.5" />
              <span>{realSensorState.isStreaming ? "PHONE SENSORS: ACTIVE" : "REAL SENSORS / INSTALL"}</span>
            </button>

            {(injectedSpeedMps !== null || gnssBlackout) && (
              <button
                type="button"
                onClick={handleClearInjection}
                className="flex items-center gap-1 px-2.5 py-1 rounded-lg bg-[#ff1744]/20 text-[#ff1744] hover:bg-[#ff1744]/30 border border-[#ff1744]/40 transition-colors"
                title="Reset active blackout or anomaly"
              >
                <RotateCcw className="w-3 h-3" />
                <span>RESET</span>
              </button>
            )}
          </div>
        </div>
      </header>

      {/* Navigation Tab Bar */}
      <nav className="border-b border-[#1b2631] bg-[#0c1217]">
        <div className="max-w-7xl mx-auto flex items-center px-4">
          <button
            type="button"
            onClick={() => setActiveTab("NAV")}
            className={`flex items-center gap-2 py-3 px-4 text-xs font-mono font-bold border-b-2 transition-colors ${
              activeTab === "NAV"
                ? "border-[#00e5ff] text-[#00e5ff] bg-[#00e5ff]/5"
                : "border-transparent text-[#9aa0a6] hover:text-[#e1e7ec]"
            }`}
          >
            <Compass className="w-4 h-4" />
            <span>COCKPIT HUD & MAP</span>
          </button>

          <button
            type="button"
            onClick={() => setActiveTab("DIAG")}
            className={`flex items-center gap-2 py-3 px-4 text-xs font-mono font-bold border-b-2 transition-colors ${
              activeTab === "DIAG"
                ? "border-[#00e5ff] text-[#00e5ff] bg-[#00e5ff]/5"
                : "border-transparent text-[#9aa0a6] hover:text-[#e1e7ec]"
            }`}
          >
            <Activity className="w-4 h-4" />
            <span>DIAGNOSTICS & ONNX RUNTIME</span>
          </button>

          <button
            type="button"
            onClick={() => setActiveTab("DOCS")}
            className={`flex items-center gap-2 py-3 px-4 text-xs font-mono font-bold border-b-2 transition-colors ${
              activeTab === "DOCS"
                ? "border-[#00e5ff] text-[#00e5ff] bg-[#00e5ff]/5"
                : "border-transparent text-[#9aa0a6] hover:text-[#e1e7ec]"
            }`}
          >
            <BookOpen className="w-4 h-4" />
            <span>ARCHITECTURE & MATRIX</span>
          </button>
        </div>
      </nav>

      {/* Main Content Area */}
      <main className="flex-1 max-w-7xl w-full mx-auto p-4 sm:p-6">
        {activeTab === "NAV" && (
          <NavigationHUD
            navState={navState}
            gnssAvailable={!gnssBlackout}
            onToggleGnssBlackout={handleToggleGnssBlackout}
            onToggleRoadConstraint={handleToggleRoadConstraint}
            onTrigger700Regression={handleTrigger700Regression}
            onClearInjection={handleClearInjection}
            gnssBlackout={gnssBlackout}
          />
        )}

        {activeTab === "DIAG" && (
          <DiagnosticsView
            navState={navState}
            sensorStats={sensorStats}
            gnssAvailable={!gnssBlackout}
          />
        )}

        {activeTab === "DOCS" && <DocsView />}
      </main>

      {/* Bottom Technical Status Bar */}
      <footer className="border-t border-[#1b2631] bg-[#070b0e] py-2 px-4 text-[11px] font-mono text-[#6b7280]">
        <div className="max-w-7xl mx-auto flex flex-col sm:flex-row items-center justify-between gap-2">
          <div>
            Contract: <span className="text-[#9aa0a6]">Member 1 ONNX (Causal CNN)</span> · Fusion: <span className="text-[#9aa0a6]">Member 3 8-State EKF</span> · Safety: <span className="text-[#9aa0a6]">Member 6 SpeedGuard</span>
          </div>
          <div>
            Built with React 18, Vite, Express, and ONNX Runtime Node
          </div>
        </div>
      </footer>

      {/* Sensor Connect & PWA Download Modal */}
      <SensorConnectModal
        isOpen={isSensorModalOpen}
        onClose={() => setIsSensorModalOpen(false)}
        onConnectRealSensors={handleConnectRealSensors}
        onDisconnectRealSensors={handleDisconnectRealSensors}
        sensorState={realSensorState}
        appUrl={typeof window !== "undefined" ? window.location.href : "https://ais-pre-eku4kxyh6skzrsucg4poi5-556565534077.asia-southeast1.run.app"}
      />
    </div>
  );
}
