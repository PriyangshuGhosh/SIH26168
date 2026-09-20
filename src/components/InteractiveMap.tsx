// Interactive Map with Dual-Track Dead Reckoning & Tunnel Zone Visualization
import React, { useEffect, useRef, useState } from "react";
import L from "leaflet";
import { NavigationMode, NavigationState } from "../types";
import { formatKmh } from "../safety/SpeedGuard";
import { Crosshair, Plus, Minus, RotateCcw, BrainCircuit, ShieldAlert } from "lucide-react";

interface InteractiveMapProps {
  navState: NavigationState;
  gnssAvailable: boolean;
  onCenter?: () => void;
}

// Simhachalam Tunnel geographic bounds
const TUNNEL_POLYGON: [number, number][] = [
  [17.7410, 83.2795],
  [17.7435, 83.2825],
  [17.7560, 83.2975],
  [17.7540, 83.2995],
  [17.7395, 83.2810],
];

export const InteractiveMap: React.FC<InteractiveMapProps> = ({
  navState,
  gnssAvailable,
}) => {
  const mapContainerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<L.Map | null>(null);
  const markerRef = useRef<L.Marker | null>(null);
  const accuracyCircleRef = useRef<L.Circle | null>(null);
  const mlTrailPolylineRef = useRef<L.Polyline | null>(null);
  const unconstrainedTrailPolylineRef = useRef<L.Polyline | null>(null);
  const mlTrailCoordsRef = useRef<[number, number][]>([]);
  const unconstrainedTrailCoordsRef = useRef<[number, number][]>([]);
  const tunnelPolygonRef = useRef<L.Polygon | null>(null);
  const [followVehicle, setFollowVehicle] = useState(true);

  // Initialize map once
  useEffect(() => {
    if (!mapContainerRef.current || mapRef.current) return;

    const initialLat = navState.latitudeDeg || 17.7420;
    const initialLon = navState.longitudeDeg || 83.2810;

    const map = L.map(mapContainerRef.current, {
      center: [initialLat, initialLon],
      zoom: 16,
      zoomControl: false,
      attributionControl: false,
    });

    // Dark-styled OpenStreetMap tile layer with inverted high-contrast tone
    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
      maxZoom: 19,
      subdomains: ["a", "b", "c"],
    }).addTo(map);

    // Render Tunnel Zone Polygon
    const tunnelPoly = L.polygon(TUNNEL_POLYGON, {
      color: "#FF9100",
      fillColor: "#FF9100",
      fillOpacity: 0.18,
      weight: 2,
      dashArray: "4, 4",
    }).addTo(map);
    tunnelPoly.bindTooltip("Simhachalam Tunnel [450m GNSS Denial]", {
      permanent: true,
      direction: "center",
      className: "tunnel-tooltip",
    });
    tunnelPolygonRef.current = tunnelPoly;

    // Unconstrained Drift Polyline (Red Dashed)
    const unconstrainedTrail = L.polyline([], {
      color: "#FF1744",
      weight: 2.5,
      opacity: 0.8,
      dashArray: "5, 5",
    }).addTo(map);
    unconstrainedTrailPolylineRef.current = unconstrainedTrail;

    // ML Intelligent Dead Reckoning Trail (Cyan Solid)
    const mlTrail = L.polyline([], {
      color: "#00E5FF",
      weight: 3.5,
      opacity: 0.9,
    }).addTo(map);
    mlTrailPolylineRef.current = mlTrail;

    // Vehicle custom SVG icon
    const vehicleIcon = L.divIcon({
      className: "vehicle-marker-wrapper",
      html: `
        <div id="vehicle-icon-inner" style="width: 38px; height: 38px; display: flex; align-items: center; justify-content: center; transform: rotate(0deg); transition: transform 0.15s ease-out;">
          <svg viewBox="0 0 38 38" width="38" height="38">
            <defs>
              <filter id="glow" x="-20%" y="-20%" width="140%" height="140%">
                <feDropShadow dx="0" dy="0" stdDeviation="3" flood-color="#00E5FF" flood-opacity="0.9"/>
              </filter>
            </defs>
            <circle cx="19" cy="19" r="16" fill="rgba(0, 229, 255, 0.2)" stroke="#00E5FF" stroke-width="2" />
            <polygon points="19,7 27,29 19,23 11,29" fill="#00E5FF" filter="url(#glow)"/>
          </svg>
        </div>
      `,
      iconSize: [38, 38],
      iconAnchor: [19, 19],
    });

    const marker = L.marker([initialLat, initialLon], { icon: vehicleIcon }).addTo(map);
    markerRef.current = marker;

    // Accuracy circle
    const circle = L.circle([initialLat, initialLon], {
      radius: 15,
      color: "#00E676",
      fillColor: "#00E676",
      fillOpacity: 0.12,
      weight: 1.5,
    }).addTo(map);
    accuracyCircleRef.current = circle;

    mapRef.current = map;

    map.on("dragstart", () => setFollowVehicle(false));

    return () => {
      map.remove();
      mapRef.current = null;
    };
  }, []);

  // Update position, trail, and orientation
  useEffect(() => {
    if (!mapRef.current || !markerRef.current) return;

    const lat = navState.latitudeDeg;
    const lon = navState.longitudeDeg;
    if (!Number.isFinite(lat) || !Number.isFinite(lon)) return;

    // Move marker
    markerRef.current.setLatLng([lat, lon]);

    // Update orientation angle in DOM SVG icon
    const iconElement = document.getElementById("vehicle-icon-inner");
    if (iconElement) {
      const headingDeg = ((-navState.yawRad * 180) / Math.PI + 90 + 360) % 360;
      iconElement.style.transform = `rotate(${headingDeg}deg)`;
    }

    // Update accuracy radius and color based on mode
    if (accuracyCircleRef.current) {
      accuracyCircleRef.current.setLatLng([lat, lon]);
      if (navState.mode === NavigationMode.DEAD_RECKONING) {
        // DR uncertainty expands slowly
        const radius = Math.min(60, 15 + (navState.outageDurationSec || 0) * 1.5);
        accuracyCircleRef.current.setRadius(radius);
        accuracyCircleRef.current.setStyle({
          color: "#00E5FF",
          fillColor: "#00E5FF",
          fillOpacity: 0.15,
        });
      } else if (navState.mode === NavigationMode.GNSS_DEGRADED) {
        accuracyCircleRef.current.setRadius(35);
        accuracyCircleRef.current.setStyle({
          color: "#FF9100",
          fillColor: "#FF9100",
          fillOpacity: 0.15,
        });
      } else {
        accuracyCircleRef.current.setRadius(10);
        accuracyCircleRef.current.setStyle({
          color: "#00E676",
          fillColor: "#00E676",
          fillOpacity: 0.12,
        });
      }
    }

    // Append to ML breadcrumb trail
    const lastMl = mlTrailCoordsRef.current[mlTrailCoordsRef.current.length - 1];
    if (!lastMl || Math.hypot(lastMl[0] - lat, lastMl[1] - lon) > 0.00005) {
      mlTrailCoordsRef.current.push([lat, lon]);
      if (mlTrailCoordsRef.current.length > 250) {
        mlTrailCoordsRef.current.shift();
      }
      if (mlTrailPolylineRef.current) {
        mlTrailPolylineRef.current.setLatLngs(mlTrailCoordsRef.current);
      }
    }

    // Append to Unconstrained Drift trail during Dead Reckoning
    if (navState.mode === NavigationMode.DEAD_RECKONING && navState.unconstrainedDrLatDeg) {
      const uLat = navState.unconstrainedDrLatDeg;
      const uLon = navState.unconstrainedDrLonDeg;
      unconstrainedTrailCoordsRef.current.push([uLat, uLon]);
      if (unconstrainedTrailCoordsRef.current.length > 250) {
        unconstrainedTrailCoordsRef.current.shift();
      }
      if (unconstrainedTrailPolylineRef.current) {
        unconstrainedTrailPolylineRef.current.setLatLngs(unconstrainedTrailCoordsRef.current);
      }
    } else {
      unconstrainedTrailCoordsRef.current = [];
      if (unconstrainedTrailPolylineRef.current) {
        unconstrainedTrailPolylineRef.current.setLatLngs([]);
      }
    }

    // Smooth pan if following vehicle
    if (followVehicle) {
      mapRef.current.panTo([lat, lon], { animate: true, duration: 0.2 });
    }
  }, [navState, followVehicle]);

  const handleRecenter = () => {
    if (!mapRef.current) return;
    setFollowVehicle(true);
    mapRef.current.setView([navState.latitudeDeg, navState.longitudeDeg], 16, { animate: true });
  };

  const handleZoomIn = () => mapRef.current?.zoomIn();
  const handleZoomOut = () => mapRef.current?.zoomOut();

  const handleClearTrails = () => {
    mlTrailCoordsRef.current = [];
    unconstrainedTrailCoordsRef.current = [];
    mlTrailPolylineRef.current?.setLatLngs([]);
    unconstrainedTrailPolylineRef.current?.setLatLngs([]);
  };

  const isDr = navState.mode === NavigationMode.DEAD_RECKONING;

  return (
    <div className="relative w-full h-[520px] rounded-2xl overflow-hidden border border-[#1f2a33] bg-[#070b0e] shadow-2xl">
      {/* Leaflet Canvas Container */}
      <div ref={mapContainerRef} className="w-full h-full z-0" />

      {/* Top Map HUD Status Overlay */}
      <div className="absolute top-4 left-4 z-[400] flex flex-wrap items-center gap-2 pointer-events-none">
        <div className="px-3 py-1.5 rounded-xl bg-[#0e1318]/90 backdrop-blur-md border border-[#1f2a33] flex items-center gap-2 shadow-lg">
          <span className="relative flex h-2.5 w-2.5">
            <span
              className={`animate-ping absolute inline-flex h-full w-full rounded-full opacity-75 ${
                isDr ? "bg-[#00e5ff]" : gnssAvailable ? "bg-[#00e676]" : "bg-[#ff1744]"
              }`}
            />
            <span
              className={`relative inline-flex rounded-full h-2.5 w-2.5 ${
                isDr ? "bg-[#00e5ff]" : gnssAvailable ? "bg-[#00e676]" : "bg-[#ff1744]"
              }`}
            />
          </span>
          <span className="font-mono text-xs font-bold tracking-wide">
            {isDr
              ? "IDR ACTIVE: ML SPEED ESTIMATION (100Hz)"
              : gnssAvailable
              ? "GNSS LOCK: SATELLITE FIX"
              : "GNSS DENIED: DEAD RECKONING"}
          </span>
        </div>

        {isDr && (
          <div className="px-3 py-1.5 rounded-xl bg-[#00e5ff]/15 border border-[#00e5ff]/40 text-[#00e5ff] backdrop-blur-md flex items-center gap-2 shadow-lg animate-pulse">
            <BrainCircuit className="w-3.5 h-3.5 text-[#00e5ff]" />
            <span className="font-mono text-xs font-bold">
              final.production.onnx Active
            </span>
          </div>
        )}
      </div>

      {/* Trajectory Legend Card */}
      <div className="absolute top-4 right-4 z-[400] bg-[#0e1318]/90 backdrop-blur-md border border-[#1f2a33] rounded-xl p-3 text-xs font-mono shadow-lg flex flex-col gap-1.5">
        <div className="text-[10px] text-[#9aa0a6] uppercase tracking-wider font-semibold border-b border-[#1f2a33] pb-1">
          Trajectory Comparison
        </div>
        <div className="flex items-center gap-2">
          <div className="w-3.5 h-1 bg-[#00e5ff] rounded" />
          <span className="text-white text-[11px]">Intelligent DR (ML+EKF)</span>
        </div>
        <div className="flex items-center gap-2">
          <div className="w-3.5 h-1 border-b border-dashed border-[#ff1744]" />
          <span className="text-[#ff8a80] text-[11px]">Unconstrained Drift</span>
        </div>
        <div className="flex items-center gap-2">
          <div className="w-3 h-3 bg-[#ff9100]/25 border border-[#ff9100] rounded-xs" />
          <span className="text-[#ffb74d] text-[11px]">Tunnel Zone</span>
        </div>
        {isDr && navState.driftErrorMeters > 0 && (
          <div className="mt-1 pt-1 border-t border-[#1f2a33] text-[11px] text-[#00e5ff] font-bold">
            Drift Saved: {navState.driftErrorMeters.toFixed(1)}m
          </div>
        )}
      </div>

      {/* Floating Map Action Controls */}
      <div className="absolute bottom-4 right-4 z-[400] flex flex-col gap-2">
        <button
          type="button"
          onClick={handleRecenter}
          className={`p-2.5 rounded-xl backdrop-blur-md border transition-all shadow-xl ${
            followVehicle
              ? "bg-[#00e5ff] text-[#070b0e] border-[#00e5ff]"
              : "bg-[#0e1318]/90 text-white border-[#1f2a33] hover:border-[#00e5ff]"
          }`}
          title="Center on Vehicle"
        >
          <Crosshair className="w-5 h-5" />
        </button>

        <div className="flex flex-col rounded-xl overflow-hidden border border-[#1f2a33] bg-[#0e1318]/90 backdrop-blur-md shadow-xl">
          <button
            type="button"
            onClick={handleZoomIn}
            className="p-2.5 text-white hover:bg-[#1a232b] hover:text-[#00e5ff] transition-colors border-b border-[#1f2a33]"
            title="Zoom In"
          >
            <Plus className="w-4 h-4" />
          </button>
          <button
            type="button"
            onClick={handleZoomOut}
            className="p-2.5 text-white hover:bg-[#1a232b] hover:text-[#00e5ff] transition-colors"
            title="Zoom Out"
          >
            <Minus className="w-4 h-4" />
          </button>
        </div>

        <button
          type="button"
          onClick={handleClearTrails}
          className="p-2.5 rounded-xl bg-[#0e1318]/90 text-[#9aa0a6] hover:text-white border border-[#1f2a33] hover:border-[#00e5ff] transition-all shadow-xl backdrop-blur-md"
          title="Clear Breadcrumb Trails"
        >
          <RotateCcw className="w-4 h-4" />
        </button>
      </div>

      {/* Bottom Coordinates & Heading Ribbon */}
      <div className="absolute bottom-4 left-4 z-[400] bg-[#0e1318]/90 backdrop-blur-md border border-[#1f2a33] rounded-xl px-3.5 py-2 text-xs font-mono text-[#c3c8cf] shadow-xl flex items-center gap-4">
        <div>
          <span className="text-[#9aa0a6] text-[10px] block">COORDINATES</span>
          <span className="text-white">
            {navState.latitudeDeg.toFixed(5)}°N, {navState.longitudeDeg.toFixed(5)}°E
          </span>
        </div>
        <div className="h-6 w-[1px] bg-[#1f2a33]" />
        <div>
          <span className="text-[#9aa0a6] text-[10px] block">CONFIDENCE</span>
          <span
            className={
              navState.confidence > 0.75
                ? "text-[#00e676]"
                : navState.confidence > 0.4
                ? "text-[#ff9100]"
                : "text-[#ff1744]"
            }
          >
            {(navState.confidence * 100).toFixed(0)}%
          </span>
        </div>
        <div className="h-6 w-[1px] bg-[#1f2a33]" />
        <div>
          <span className="text-[#9aa0a6] text-[10px] block">SPEED</span>
          <span className="text-[#00e5ff] font-bold">
            {formatKmh(navState.speedMps)} km/h
          </span>
        </div>
      </div>
    </div>
  );
};
