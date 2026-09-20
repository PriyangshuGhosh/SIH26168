import express from "express";
import cors from "cors";
import path from "path";
import fs from "fs";
import { fileURLToPath } from "url";
import { createServer as createViteServer } from "vite";
import * as ort from "onnxruntime-node";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

let onnxSession: ort.InferenceSession | null = null;
let onnxLoadError: string | null = null;
let onnxModelMetadata = {
  modelName: "final.production.onnx",
  inputName: "imu_window_100hz",
  inputShape: [1, 200, 6],
  outputNames: ["velocity_mps", "velocity_variance_m2s2", "confidence"],
  parameterCount: 27266,
  fileSizeBytes: 137216,
  architecture: "1D Causal CNN (VelocityNet) + Decimation (100Hz->10Hz) + Heteroscedastic Uncertainty Head",
  member: "Member 1 (ML Kinematics) -> Member 3 (EKF Fusion)",
  loaded: false,
};

async function initOnnxEngine() {
  try {
    const modelPath = path.join(process.cwd(), "final.production.onnx");
    if (fs.existsSync(modelPath)) {
      const stats = fs.statSync(modelPath);
      onnxModelMetadata.fileSizeBytes = stats.size;
      onnxSession = await ort.InferenceSession.create(modelPath);
      onnxModelMetadata.loaded = true;
      console.log(`[SIH26168-ML] Member 1 ONNX model loaded successfully (${(stats.size / 1024).toFixed(1)} KB)`);
    } else {
      onnxLoadError = `Model file not found at ${modelPath}`;
      console.warn(`[SIH26168-ML] ${onnxLoadError}`);
    }
  } catch (err: any) {
    onnxLoadError = err?.message || String(err);
    console.error("[SIH26168-ML] Failed to load ONNX model:", err);
  }
}

interface RoadPackRegion {
  regionId: string;
  name: string;
  minLatDeg: number;
  maxLatDeg: number;
  minLonDeg: number;
  maxLonDeg: number;
  version: string;
  source: "demo" | "provisioned";
}

interface StatusCheck {
  id: string;
  client_name: string;
  timestamp: string;
}

const CATALOG: RoadPackRegion[] = [
  {
    regionId: "in-vizag",
    name: "Visakhapatnam (Vizag)",
    minLatDeg: 17.60,
    maxLatDeg: 17.78,
    minLonDeg: 83.15,
    maxLonDeg: 83.30,
    version: "1.0.0",
    source: "provisioned",
  },
  {
    regionId: "demo-sandbox",
    name: "Demo Sandbox (0,0)",
    minLatDeg: -0.5,
    maxLatDeg: 0.5,
    minLonDeg: -0.5,
    maxLonDeg: 0.5,
    version: "0.1.0",
    source: "demo",
  },
  {
    regionId: "in-bengaluru",
    name: "Bengaluru",
    minLatDeg: 12.80,
    maxLatDeg: 13.15,
    minLonDeg: 77.45,
    maxLonDeg: 77.80,
    version: "1.0.0",
    source: "provisioned",
  },
  {
    regionId: "in-delhi",
    name: "Delhi NCR",
    minLatDeg: 28.40,
    maxLatDeg: 28.90,
    minLonDeg: 76.90,
    maxLonDeg: 77.50,
    version: "1.0.0",
    source: "provisioned",
  },
];

// In-memory status checks store (replacing MongoDB from python backend)
const statusChecksStore: StatusCheck[] = [
  {
    id: "init-status-1",
    client_name: "Member 6 Navigation Client",
    timestamp: new Date().toISOString(),
  },
];

async function startServer() {
  const app = express();
  const PORT = 3000;

  app.use(cors());
  app.use(express.json());

  await initOnnxEngine();

  // API Routes
  app.get("/api/health", (_req, res) => {
    res.json({
      status: "ok",
      timestamp: new Date().toISOString(),
      onnx_loaded: onnxModelMetadata.loaded,
    });
  });

  // Member 1 ML Model Metadata & Status
  app.get("/api/ml/status", (_req, res) => {
    res.json({
      ...onnxModelMetadata,
      error: onnxLoadError,
      timestamp: new Date().toISOString(),
    });
  });

  // Serve ONNX model binary if client runtime desires local inference
  app.get("/final.production.onnx", (_req, res) => {
    const modelPath = path.join(process.cwd(), "final.production.onnx");
    if (fs.existsSync(modelPath)) {
      res.setHeader("Content-Type", "application/octet-stream");
      res.sendFile(modelPath);
    } else {
      res.status(404).send("Model file not found");
    }
  });

  // Member 1 Machine Learning Prediction Inference
  // Transforms 2-second 100 Hz IMU buffer [200, 6] -> velocity_mps, velocity_variance_m2s2, confidence
  app.post("/api/ml/predict", async (req, res) => {
    const tStart = performance.now();
    try {
      if (!onnxSession) {
        return res.status(503).json({
          error: "ONNX inference engine not initialized",
          details: onnxLoadError,
        });
      }

      let flatBuffer: Float32Array;
      const body = req.body;

      if (Array.isArray(body.imu_window_100hz)) {
        if (Array.isArray(body.imu_window_100hz[0])) {
          // 2D array [N, 6]
          const rows = Math.min(200, body.imu_window_100hz.length);
          flatBuffer = new Float32Array(200 * 6);
          const startRow = 200 - rows;
          for (let r = 0; r < rows; r++) {
            const row = body.imu_window_100hz[r];
            const base = (startRow + r) * 6;
            for (let c = 0; c < 6; c++) {
              flatBuffer[base + c] = Number(row[c]) || 0;
            }
          }
        } else {
          // 1D flat array
          const raw = body.imu_window_100hz;
          flatBuffer = new Float32Array(200 * 6);
          const len = Math.min(1200, raw.length);
          const offset = 1200 - len;
          for (let i = 0; i < len; i++) {
            flatBuffer[offset + i] = Number(raw[i]) || 0;
          }
        }
      } else if (Array.isArray(body.samples)) {
        // [{ ax, ay, az, gx, gy, gz }, ...]
        const samples = body.samples;
        const count = Math.min(200, samples.length);
        flatBuffer = new Float32Array(200 * 6);
        const startRow = 200 - count;
        for (let i = 0; i < count; i++) {
          const s = samples[i];
          const base = (startRow + i) * 6;
          flatBuffer[base + 0] = Number(s.ax) || 0;
          flatBuffer[base + 1] = Number(s.ay) || 0;
          flatBuffer[base + 2] = Number(s.az) || 0;
          flatBuffer[base + 3] = Number(s.gx) || 0;
          flatBuffer[base + 4] = Number(s.gy) || 0;
          flatBuffer[base + 5] = Number(s.gz) || 0;
        }
      } else {
        return res.status(400).json({
          error: "Missing required 'imu_window_100hz' or 'samples' payload",
        });
      }

      // Run ONNX forward pass
      const inputTensor = new ort.Tensor("float32", flatBuffer, [1, 200, 6]);
      const results = await onnxSession.run({ imu_window_100hz: inputTensor });

      const velocity_mps = Number(results.velocity_mps.data[0]);
      const velocity_variance_m2s2 = Number(results.velocity_variance_m2s2.data[0]);
      const confidence = Number(results.confidence.data[0]);
      const inference_time_ms = performance.now() - tStart;

      return res.json({
        status: "ok",
        velocity_mps: Math.max(0, velocity_mps),
        velocity_variance_m2s2: Math.max(1e-4, velocity_variance_m2s2),
        confidence: Math.min(1, Math.max(0, confidence)),
        inference_time_ms,
        model: onnxModelMetadata.modelName,
        timestamp: Date.now(),
      });
    } catch (err: any) {
      return res.status(500).json({
        error: "Model inference execution failed",
        details: err?.message || String(err),
      });
    }
  });

  app.get("/api", (_req, res) => {
    res.json({
      service: "sih26168-navigation-system",
      pipeline: "Phone IMU/GNSS → M2 (Frame Alignment) → M1 (AI Speed) → M3 (EKF Fusion) → M4 (HMM Map Matching) → M5 (Native Engine) → M6 (UI)",
      version: "1.0.0",
    });
  });

  app.get("/api/roadpacks", (_req, res) => {
    res.json(CATALOG);
  });

  app.get("/api/roadpacks/resolve", (req, res) => {
    const lat = parseFloat(req.query.lat as string);
    const lon = parseFloat(req.query.lon as string);

    if (isNaN(lat) || isNaN(lon)) {
      return res.status(400).json({ error: "Invalid lat or lon query parameter" });
    }

    for (const r of CATALOG) {
      if (lat >= r.minLatDeg && lat <= r.maxLatDeg && lon >= r.minLonDeg && lon <= r.maxLonDeg) {
        return res.json({ active: r, outOfCoverage: false, count: CATALOG.length });
      }
    }

    res.json({ active: null, outOfCoverage: true, count: CATALOG.length });
  });

  app.get("/api/status", (_req, res) => {
    res.json(statusChecksStore);
  });

  app.post("/api/status", (req, res) => {
    const { client_name } = req.body;
    const item: StatusCheck = {
      id: "status-" + Math.random().toString(36).substring(2, 9),
      client_name: client_name || "Unknown Client",
      timestamp: new Date().toISOString(),
    };
    statusChecksStore.unshift(item);
    if (statusChecksStore.length > 50) statusChecksStore.pop();
    res.status(201).json(item);
  });

  // Vite middleware in dev / Static files in production
  if (process.env.NODE_ENV !== "production") {
    const vite = await createViteServer({
      server: { middlewareMode: true },
      appType: "spa",
    });
    app.use(vite.middlewares);
  } else {
    const distPath = path.join(process.cwd(), "dist");
    app.use(express.static(distPath));
    app.get("*", (_req, res) => {
      res.sendFile(path.join(distPath, "index.html"));
    });
  }

  app.listen(PORT, "0.0.0.0", () => {
    console.log(`[SIH26168] Server running at http://0.0.0.0:${PORT}`);
  });
}

startServer();
