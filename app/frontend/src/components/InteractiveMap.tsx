import React, { useEffect, useRef } from "react";
import { StyleSheet, View } from "react-native";
import { WebView } from "react-native-webview";
import { NavigationMode, NavigationState } from "../navigation/types";

interface InteractiveMapProps {
  navState: NavigationState;
  gnssAvailable: boolean;
}

// Leaflet offline HTML template with IndexedDB tile caching
const generateMapHtml = () => `
<!DOCTYPE html>
<html>
<head>
  <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no" />
  <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
  <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
  <style>
    body, html, #map { margin: 0; padding: 0; width: 100%; height: 100%; background: #0b1218; }
    .vehicle-marker {
      transition: transform 0.2s linear;
      filter: drop-shadow(0px 0px 6px #00e5ff);
    }
    .leaflet-tile { filter: brightness(0.7) contrast(1.2) invert(1) hue-rotate(180deg); }
    .mode-badge {
      position: absolute; top: 12px; left: 12px; z-index: 1000;
      background: rgba(11, 18, 24, 0.85); border: 1px solid #1f2a33;
      color: #00e5ff; padding: 6px 12px; border-radius: 20px;
      font-family: monospace; font-size: 11px; font-weight: bold;
    }
  </style>
</head>
<body>
  <div id="map"></div>
  <script>
    let map = L.map('map', { zoomControl: false, attributionControl: false }).setView([17.6868, 83.2185], 16);
    
    // OpenStreetMap dark-style tiles
    let tileLayer = L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      maxZoom: 19,
      crossOrigin: true
    }).addTo(map);

    // Simple Tile Caching using CacheStorage / LocalStorage
    const DB_NAME = 'IDR_Offline_Tiles';
    let db;
    const request = indexedDB.open(DB_NAME, 1);
    request.onupgradeneeded = (e) => {
      db = e.target.result;
      if (!db.objectStoreNames.contains('tiles')) db.createObjectStore('tiles');
    };
    request.onsuccess = (e) => { db = e.target.result; };

    // Vehicle Icon SVG (Navigation Arrow)
    const arrowIcon = L.divIcon({
      className: 'custom-vehicle-marker',
      html: \`<svg id="vehicle-arrow" width="36" height="36" viewBox="0 0 36 36" style="transform-origin: center;">
        <circle cx="18" cy="18" r="16" fill="rgba(0, 229, 255, 0.15)" stroke="#00e5ff" stroke-width="2"/>
        <path d="M18 6 L26 26 L18 21 L10 26 Z" fill="#00e5ff"/>
      </svg>\`,
      iconSize: [36, 36],
      iconAnchor: [18, 18]
    });

    let marker = L.marker([17.6868, 83.2185], { icon: arrowIcon }).addTo(map);
    let polyline = L.polyline([], { color: '#00e5ff', weight: 3, opacity: 0.8 }).addTo(map);
    let pathCoords = [];
    let isInitialFix = true;

    // Listen to React Native state updates
    window.addEventListener('message', function(event) {
      try {
        const data = JSON.parse(event.data);
        if (!data || typeof data.lat !== 'number' || typeof data.lon !== 'number') return;

        const lat = data.lat;
        const lon = data.lon;
        const yawDeg = data.headingDeg || 0;
        const mode = data.mode || 'GNSS';

        const newLatLng = [lat, lon];
        marker.setLatLng(newLatLng);

        // Rotate vehicle arrow SVG
        const arrowEl = document.getElementById('vehicle-arrow');
        if (arrowEl) {
          arrowEl.style.transform = \`rotate(\${yawDeg}deg)\`;
        }

        // Update trail path
        if (pathCoords.length === 0 || L.latLng(pathCoords[pathCoords.length - 1]).distanceTo(newLatLng) > 2) {
          pathCoords.push(newLatLng);
          if (pathCoords.length > 200) pathCoords.shift();
          polyline.setLatLngs(pathCoords);
        }

        // Center map on vehicle
        if (isInitialFix) {
          map.setView(newLatLng, 16);
          isInitialFix = false;
        } else {
          map.panTo(newLatLng, { animate: true, duration: 0.3 });
        }
      } catch(e) {}
    });
  </script>
</body>
</html>
`;

export function InteractiveMap({ navState, gnssAvailable }: InteractiveMapProps) {
  const webViewRef = useRef<WebView>(null);

  // Convert yawRad (ENU radians, CCW from East) to compass bearing (Degrees, CW from North)
  const headingDeg = useMemo(() => {
    // yawRad: 0 = East, PI/2 = North, PI = West, -PI/2 = South
    // Compass: 0 = North, 90 = East, 180 = South, 270 = West
    let deg = 90 - (navState.yawRad * 180) / Math.PI;
    while (deg < 0) deg += 360;
    while (deg >= 360) deg -= 360;
    return Math.round(deg);
  }, [navState.yawRad]);

  useEffect(() => {
    if (!webViewRef.current) return;
    const payload = JSON.stringify({
      lat: navState.latitudeDeg,
      lon: navState.longitudeDeg,
      headingDeg,
      mode: navState.mode,
      speedKmh: Math.round(navState.speedMps * 3.6),
      gnssAvailable,
    });
    webViewRef.current.postMessage(payload);
  }, [navState.latitudeDeg, navState.longitudeDeg, headingDeg, navState.mode, gnssAvailable]);

  return (
    <View style={styles.container}>
      <WebView
        ref={webViewRef}
        originWhitelist={["*"]}
        source={{ html: generateMapHtml() }}
        style={styles.webview}
        javaScriptEnabled={true}
        domStorageEnabled={true}
        allowFileAccess={true}
        mixedContentMode="always"
        scrollEnabled={false}
      />
    </View>
  );
}

import { useMemo } from "react";

const styles = StyleSheet.create({
  container: {
    ...StyleSheet.absoluteFillObject,
    backgroundColor: "#0b1218",
  },
  webview: {
    flex: 1,
    backgroundColor: "transparent",
  },
});
