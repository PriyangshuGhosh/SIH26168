import React from "react";
import { Download, Smartphone, CheckCircle, Navigation, Radio } from "lucide-react";
import { RealSensorState } from "../sensors/PhoneSensorService";

interface SensorConnectModalProps {
  isOpen: boolean;
  onClose: () => void;
  onConnectRealSensors: () => void;
  onDisconnectRealSensors: () => void;
  sensorState: RealSensorState;
  appUrl: string;
}

export const SensorConnectModal: React.FC<SensorConnectModalProps> = ({
  isOpen,
  onClose,
  onConnectRealSensors,
  onDisconnectRealSensors,
  sensorState,
  appUrl,
}) => {
  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-sm animate-in fade-in duration-200">
      <div className="bg-[#0e141a] border border-[#1f2a33] rounded-2xl w-full max-w-lg shadow-2xl p-6 flex flex-col gap-5 text-[#e1e7ec]">
        <div className="flex items-center justify-between border-b border-[#1f2a33] pb-4">
          <div className="flex items-center gap-3">
            <div className="p-2.5 rounded-xl bg-[#00e5ff]/10 text-[#00e5ff] border border-[#00e5ff]/20">
              <Smartphone className="w-5 h-5" />
            </div>
            <div>
              <h3 className="text-base font-bold font-mono text-white">
                LIVE HARDWARE SENSORS & INSTALL
              </h3>
              <p className="text-xs text-[#9aa0a6] font-mono mt-0.5">
                Test with real mobile IMU (Accel/Gyro) & GPS
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="text-[#9aa0a6] hover:text-white text-lg font-mono px-2 py-1 rounded"
          >
            ✕
          </button>
        </div>

        {/* Live Sensor Switch */}
        <div className="bg-[#141d24] border border-[#1f2a33] rounded-xl p-4 flex flex-col gap-3 font-mono">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Radio className={`w-4 h-4 ${sensorState.isStreaming ? "text-[#00e676] animate-pulse" : "text-[#9aa0a6]"}`} />
              <span className="text-sm font-bold text-white">Device Sensor Stream</span>
            </div>
            {sensorState.isStreaming ? (
              <button
                onClick={onDisconnectRealSensors}
                className="px-3 py-1 text-xs rounded-lg bg-[#ff1744]/20 text-[#ff1744] hover:bg-[#ff1744]/30 border border-[#ff1744]/30"
              >
                DISCONNECT
              </button>
            ) : (
              <button
                onClick={onConnectRealSensors}
                className="px-3.5 py-1.5 text-xs font-bold rounded-lg bg-[#00e5ff] text-[#070b0e] hover:bg-[#00e5ff]/90"
              >
                ENABLE HARDWARE SENSORS
              </button>
            )}
          </div>

          <div className="grid grid-cols-2 gap-2 text-xs pt-2 border-t border-[#1f2a33]">
            <div className="flex justify-between items-center bg-[#0e141a] p-2 rounded border border-[#1f2a33]/60">
              <span className="text-[#9aa0a6]">3-Axis IMU:</span>
              <span className={sensorState.motionActive ? "text-[#00e676] font-bold" : "text-[#9aa0a6]"}>
                {sensorState.motionActive ? "STREAMING" : "WAITING"}
              </span>
            </div>
            <div className="flex justify-between items-center bg-[#0e141a] p-2 rounded border border-[#1f2a33]/60">
              <span className="text-[#9aa0a6]">GPS Satellite:</span>
              <span className={sensorState.gpsActive ? "text-[#00e676] font-bold" : "text-[#9aa0a6]"}>
                {sensorState.gpsActive ? "LOCKED" : "WAITING"}
              </span>
            </div>
          </div>

          {sensorState.error && (
            <div className="text-xs text-[#ff1744] bg-[#ff1744]/10 p-2 rounded border border-[#ff1744]/20">
              {sensorState.error}
            </div>
          )}
        </div>

        {/* How to download / open on mobile */}
        <div className="flex flex-col gap-3 font-mono text-xs">
          <div className="text-[#00e5ff] font-bold flex items-center gap-1.5">
            <Download className="w-4 h-4" />
            <span>HOW TO TEST ON YOUR PHONE:</span>
          </div>

          <ol className="list-decimal list-inside space-y-2 text-[#9aa0a6] leading-relaxed">
            <li>
              <strong className="text-white">Open on Phone:</strong> Scan or visit this link in Chrome or Safari:
              <div className="mt-1 p-2 rounded bg-[#070b0e] border border-[#1f2a33] text-[11px] text-[#00e5ff] break-all select-all font-mono">
                {appUrl}
              </div>
            </li>
            <li>
              <strong className="text-white">Install as App (PWA):</strong> Tap <span className="text-white">"Add to Home screen"</span> or <span className="text-white">"Install App"</span> in your browser menu. It will install with standalone cockpit view.
            </li>
            <li>
              <strong className="text-white">Allow Permissions:</strong> When prompted, tap <em>Allow</em> for Location (GNSS) and Motion Sensors (IMU).
            </li>
            <li>
              <strong className="text-white">Drive / Walk:</strong> Put the phone on your car dashboard or hold it forward. Member 2 will align orientation, Member 3 EKF will track speed, and Member 1 will predict speed during tunnel outages.
            </li>
          </ol>
        </div>

        <div className="flex justify-end pt-2">
          <button
            onClick={onClose}
            className="px-5 py-2 text-xs font-mono font-bold bg-[#141d24] text-white hover:bg-[#1f2a33] rounded-lg border border-[#1f2a33]"
          >
            DONE
          </button>
        </div>
      </div>
    </div>
  );
};
