// EngineController — a single global instance owning:
//   • MemberFiveEngine (the JS Member 5 simulator)
//   • SensorPipeline    (timestamp-aware IMU pairing)
//   • SyntheticDrive    (dev-only synthetic scenarios)
//   • Location watcher  (expo-location, real GNSS on device)
//
// The Navigation and Diagnostics screens subscribe via useEngine().

import React, {
  createContext,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { AppState, Platform } from "react-native";
import * as Location from "expo-location";
import { Accelerometer, Gyroscope } from "expo-sensors";
import { Asset } from "expo-asset";

import { MemberFiveEngine } from "./MemberFiveEngine";
import { OnnxSpeedEstimator } from "./OnnxSpeedEstimator";
import { SensorPipeline, SensorStats } from "../sensors/SensorPipeline";
import { SyntheticDrive, Scenario } from "../simulation/SyntheticDrive";
import {
  emptyNavigationState,
  NavigationState,
} from "../navigation/types";
import { evaluateSpeed } from "../safety/SpeedGuard";
import { RejectionReason } from "../navigation/types";

export interface EngineStatus {
  engineInitialized: boolean;
  locationPermission: "unknown" | "granted" | "denied";
  gnssAvailable: boolean;
  gnssAccuracyM: number | null;
  gnssAgeMs: number;
  lastNativeError: string | null;
  lastMapError: string | null;
  syntheticEnabled: boolean;
  scenario: Scenario;
  simulationInjectedSpeedMps: number | null;
  lastUiSpeedRejection: RejectionReason;
  // Member 1 ONNX model status
  mlModelLoaded: boolean;
  mlModelError: string | null;
}

interface EngineCtx {
  navState: NavigationState;
  sensorStats: SensorStats;
  status: EngineStatus;
  requestLocation: () => Promise<void>;
  enableSyntheticMode: (v: boolean) => void;
  setScenario: (s: Scenario) => void;
  triggerRegression700: () => void;
  clearInjection: () => void;
  simulateEngineFault: (on: boolean) => void;
}

const Ctx = createContext<EngineCtx | null>(null);

export function EngineProvider({ children }: { children: React.ReactNode }) {
  const engineRef = useRef<MemberFiveEngine | null>(null);
  const pipelineRef = useRef<SensorPipeline | null>(null);
  const syntheticRef = useRef<SyntheticDrive | null>(null);
  const accelSubRef = useRef<any>(null);
  const gyroSubRef = useRef<any>(null);
  const locSubRef = useRef<Location.LocationSubscription | null>(null);

  const [navState, setNavState] = useState<NavigationState>(
    emptyNavigationState(),
  );
  const [sensorStats, setSensorStats] = useState<SensorStats>({
    accelHz: 0,
    gyroHz: 0,
    emittedHz: 0,
    lastPairingDeltaMs: 0,
    droppedRegression: 0,
    droppedStale: 0,
    droppedNoPair: 0,
    duplicatesSkipped: 0,
    lastAccelTsNs: 0,
    lastGyroTsNs: 0,
    lastEmitTsNs: 0,
  });
  const [status, setStatus] = useState<EngineStatus>({
    engineInitialized: false,
    locationPermission: "unknown",
    gnssAvailable: false,
    gnssAccuracyM: null,
    gnssAgeMs: -1,
    lastNativeError: null,
    lastMapError: null,
    syntheticEnabled: false,
    scenario: "STATIONARY",
    simulationInjectedSpeedMps: null,
    lastUiSpeedRejection: RejectionReason.NONE,
    mlModelLoaded: false,
    mlModelError: null,
  });

  // One-time engine boot.
  useEffect(() => {
    // Create ONNX speed estimator (loads model asynchronously after engine starts).
    const estimator = new OnnxSpeedEstimator();

    try {
      const engine = new MemberFiveEngine({ onnxEstimator: estimator });
      engine.init();
      engineRef.current = engine;
      const pipeline = new SensorPipeline();
      pipeline.onSample((s) => engineRef.current?.feedImu(s));
      pipelineRef.current = pipeline;
      const synth = new SyntheticDrive();
      synth.onImu((s) => {
        pipeline.pushAccel(s.timestampNs, s.ax, s.ay, s.az);
        pipeline.pushGyro(s.timestampNs, s.gx, s.gy, s.gz);
      });
      synth.onGnss((g) => engineRef.current?.feedGnss(g));
      syntheticRef.current = synth;
      setStatus((s) => ({ ...s, engineInitialized: true }));
    } catch (e: any) {
      setStatus((s) => ({
        ...s,
        engineInitialized: false,
        lastNativeError: String(e?.message ?? e),
      }));
    }

    // Load ONNX model from bundled asset in background.
    // Engine runs normally (GPS mode) while model loads; ML kicks in once ready.
    (async () => {
      try {
        // Resolve the bundled asset URI at runtime.
        const [asset] = await Asset.loadAsync(
          require("../../assets/models/final.production.onnx"),
        );
        const uri = asset.localUri ?? asset.uri;
        if (!uri) throw new Error("Asset URI is null after loadAsync");
        await estimator.load(uri);
        setStatus((s) => ({ ...s, mlModelLoaded: true, mlModelError: null }));
      } catch (e: any) {
        const msg = String(e?.message ?? e);
        console.warn("[EngineController] ONNX load failed:", msg);
        setStatus((s) => ({ ...s, mlModelLoaded: false, mlModelError: msg }));
      }
    })();


    // Poll navigation state + stats at 8 Hz. UI updates decoupled from
    // 100 Hz IMU cadence to keep the JS thread responsive.
    const pollId = setInterval(() => {
      const eng = engineRef.current;
      const pipe = pipelineRef.current;
      if (!eng || !pipe) return;
      const state = eng.getState();
      const stats = pipe.getStats();
      setNavState(state);
      setSensorStats(stats);
      const speedEval = evaluateSpeed(state.speedMps);
      setStatus((s) => ({
        ...s,
        gnssAgeMs: eng.getGnssAgeMs(),
        lastUiSpeedRejection: speedEval.valid
          ? RejectionReason.NONE
          : speedEval.reason,
      }));
    }, 125);

    // Real sensor subscriptions (accel/gyro) — best effort on web, native
    // on iOS/Android. Web values are not physically calibrated, so their
    // absolute magnitude is NOT VALIDATED for navigation math.
    (async () => {
      // Robust sensor setup: retry intervals (10ms -> 20ms -> 50ms) to prevent SecurityException on Android 12+
      const intervals = [10, 20, 50];
      for (const intervalMs of intervals) {
        try {
          Accelerometer.setUpdateInterval(intervalMs);
          Gyroscope.setUpdateInterval(intervalMs);
          break;
        } catch (e) {
          // Continue to next interval if high sampling rate is blocked
        }
      }

      try {
        // expo-sensors delivers { x, y, z } in "g" for accelerometer. Convert to m/s^2.
        accelSubRef.current = Accelerometer.addListener(({ x, y, z }) => {
          const tsNs = nowNs();
          pipelineRef.current?.pushAccel(tsNs, x * 9.80665, y * 9.80665, z * 9.80665);
        });
        // Gyroscope in rad/s already.
        gyroSubRef.current = Gyroscope.addListener(({ x, y, z }) => {
          const tsNs = nowNs();
          pipelineRef.current?.pushGyro(tsNs, x, y, z);
        });
      } catch (e: any) {
        setStatus((s) => ({
          ...s,
          lastNativeError: `Sensor setup: ${String(e?.message ?? e)}`,
        }));
      }
    })();


    // Lifecycle: stop synthetic drive in background to avoid duplicate engines.
    const appSub = AppState.addEventListener("change", (next) => {
      if (next !== "active" && syntheticRef.current?.getState().running) {
        syntheticRef.current.stop();
        setStatus((s) => ({ ...s, syntheticEnabled: false }));
      }
    });

    return () => {
      clearInterval(pollId);
      accelSubRef.current?.remove?.();
      gyroSubRef.current?.remove?.();
      locSubRef.current?.remove?.();
      syntheticRef.current?.stop();
      engineRef.current?.shutdown();
      appSub.remove();
    };
  }, []);

  const requestLocation = async () => {
    try {
      const { status: perm } = await Location.requestForegroundPermissionsAsync();
      if (perm !== "granted") {
        setStatus((s) => ({ ...s, locationPermission: "denied" }));
        return;
      }
      setStatus((s) => ({ ...s, locationPermission: "granted" }));
      locSubRef.current?.remove?.();
      locSubRef.current = await Location.watchPositionAsync(
        {
          accuracy: Location.Accuracy.BestForNavigation,
          timeInterval: 1000,
          distanceInterval: 0,
        },
        (loc) => {
          const c = loc.coords;
          engineRef.current?.feedGnss({
            timestampNs: nowNs(),
            latitudeDeg: c.latitude,
            longitudeDeg: c.longitude,
            altitudeM: c.altitude ?? 0,
            speedMps: c.speed ?? 0,
            bearingRad:
              c.heading != null && c.heading >= 0
                ? (c.heading * Math.PI) / 180
                : null,
            horizontalAccuracyM: c.accuracy ?? 20,
            available: true,
          });
          setStatus((s) => ({
            ...s,
            gnssAvailable: true,
            gnssAccuracyM: c.accuracy ?? null,
          }));
        },
      );
    } catch (e: any) {
      setStatus((s) => ({
        ...s,
        lastNativeError: `Location: ${String(e?.message ?? e)}`,
      }));
    }
  };

  const enableSyntheticMode = (v: boolean) => {
    const synth = syntheticRef.current;
    if (!synth) return;
    if (v) synth.start();
    else synth.stop();
    setStatus((s) => ({ ...s, syntheticEnabled: v }));
  };

  const setScenario = (s: Scenario) => {
    syntheticRef.current?.setScenario(s);
    setStatus((prev) => ({ ...prev, scenario: s }));
  };

  const triggerRegression700 = () => {
    // 194.4 m/s * 3.6 == 699.84 km/h. Injected at the state boundary so
    // the safety layer must catch it before it reaches the HUD.
    engineRef.current?.injectSpeedMps(194.4);
    setStatus((s) => ({ ...s, simulationInjectedSpeedMps: 194.4 }));
  };

  const clearInjection = () => {
    engineRef.current?.injectSpeedMps(null);
    setStatus((s) => ({ ...s, simulationInjectedSpeedMps: null }));
  };

  const simulateEngineFault = (on: boolean) => {
    engineRef.current?.simulateFault(on);
  };

  const value = useMemo(
    () => ({
      navState,
      sensorStats,
      status,
      requestLocation,
      enableSyntheticMode,
      setScenario,
      triggerRegression700,
      clearInjection,
      simulateEngineFault,
    }),
    [navState, sensorStats, status],
  );

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useEngine(): EngineCtx {
  const v = useContext(Ctx);
  if (!v) throw new Error("useEngine must be used inside <EngineProvider>");
  return v;
}

function nowNs(): number {
  const t = typeof performance !== "undefined" ? performance.now() : Date.now();
  return Math.floor(t * 1_000_000);
}

export const __PLATFORM_TAG = Platform.OS;
