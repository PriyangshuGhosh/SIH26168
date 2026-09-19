import React, { useEffect, useRef, useMemo } from "react";
import { StyleSheet, View } from "react-native";
import { WebView } from "react-native-webview";
import { NavigationMode, NavigationState } from "../navigation/types";

interface InteractiveMapProps {
  navState: NavigationState;
  gnssAvailable: boolean;
}

// Vizag centre coordinates (member4 region)
const VIZAG_LAT = 17.6868;
const VIZAG_LON = 83.2185;

// Build the full self-contained Leaflet map page.
// Leaflet JS/CSS are loaded from CDN; if offline the WebView
// serves them from its HTTP cache (populated on first run).
// Tile images are additionally cached in IndexedDB so the map
// continues to work without internet once tiles have been loaded.
const MAP_HTML = `<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1,user-scalable=no"/>
  <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
  <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
  <style>
    *{margin:0;padding:0;box-sizing:border-box}
    html,body,#map{width:100%;height:100%;background:#0b1218}
    /* Dark map tile tint */
    .leaflet-tile{filter:brightness(.65) contrast(1.15) invert(1) hue-rotate(180deg) saturate(.9)}
    /* Vehicle arrow */
    #vehicle-svg{transform-origin:center center;transition:transform .25s linear}
    .leaflet-control{display:none}
    /* Mode badge */
    #mode-badge{
      position:absolute;top:10px;left:10px;z-index:1000;
      padding:5px 14px;border-radius:20px;
      font-family:monospace;font-size:12px;font-weight:bold;
      letter-spacing:1px;border:1px solid;pointer-events:none;
      transition:background .4s,color .4s,border-color .4s;
    }
    #mode-badge.gps{background:rgba(0,200,100,.18);color:#00e696;border-color:#00e696}
    #mode-badge.dr {background:rgba(255,160,0,.18);color:#ffaa00;border-color:#ffaa00}
    /* Speed overlay */
    #speed-badge{
      position:absolute;top:10px;right:10px;z-index:1000;
      background:rgba(11,18,24,.85);border:1px solid #1f2a33;
      color:#00e5ff;padding:5px 12px;border-radius:12px;
      font-family:monospace;font-size:13px;font-weight:bold;
      pointer-events:none;
    }
    /* Accuracy ring shown in GPS mode */
    .acc-circle{pointer-events:none}
  </style>
</head>
<body>
  <div id="map"></div>
  <div id="mode-badge" class="gps">⬤ GPS</div>
  <div id="speed-badge">-- km/h</div>
<script>
// ─── Constants ───────────────────────────────────────────────────
const VIZAG_LAT = ${VIZAG_LAT};
const VIZAG_LON = ${VIZAG_LON};
const TILE_URL  = 'https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png';
const DB_NAME   = 'IDR_VizagTiles_v2';
const DB_STORE  = 'tiles';
// Vizag bounding box ≈ 5×5 km
const CACHE_BOUNDS = { minLat:17.63, maxLat:17.74, minLon:83.18, maxLon:83.27 };
const CACHE_ZOOMS  = [13, 14, 15, 16];

// ─── IndexedDB tile cache ─────────────────────────────────────────
let db = null;
(function openDB(){
  const req = indexedDB.open(DB_NAME, 1);
  req.onupgradeneeded = e => {
    const d = e.target.result;
    if(!d.objectStoreNames.contains(DB_STORE)) d.createObjectStore(DB_STORE);
  };
  req.onsuccess = e => {
    db = e.target.result;
    // Pre-cache Vizag tiles on first load (background, won't block UI)
    precacheVizagTiles();
  };
  req.onerror = () => console.warn('IDR: IndexedDB open failed');
})();

function tileKey(z,x,y){ return z+'/'+x+'/'+y; }

function saveTile(key, blob){
  if(!db) return;
  try{
    const tx = db.transaction(DB_STORE,'readwrite');
    tx.objectStore(DB_STORE).put(blob, key);
  }catch(e){}
}

function loadTile(key){
  return new Promise((res,rej) => {
    if(!db){ rej(); return; }
    try{
      const tx = db.transaction(DB_STORE,'readonly');
      const req = tx.objectStore(DB_STORE).get(key);
      req.onsuccess = e => e.target.result ? res(e.target.result) : rej();
      req.onerror   = () => rej();
    }catch(e){ rej(); }
  });
}

// Degree → tile number
function lon2tile(lon,z){ return Math.floor((lon+180)/360 * Math.pow(2,z)); }
function lat2tile(lat,z){
  const r = lat*Math.PI/180;
  return Math.floor((1-Math.log(Math.tan(r)+1/Math.cos(r))/Math.PI)/2*Math.pow(2,z));
}

async function precacheVizagTiles(){
  for(const z of CACHE_ZOOMS){
    const x0=lon2tile(CACHE_BOUNDS.minLon,z), x1=lon2tile(CACHE_BOUNDS.maxLon,z);
    const y0=lat2tile(CACHE_BOUNDS.maxLat,z), y1=lat2tile(CACHE_BOUNDS.minLat,z);
    for(let x=x0;x<=x1;x++){
      for(let y=y0;y<=y1;y++){
        const key=tileKey(z,x,y);
        // Skip if already cached
        try{ await loadTile(key); continue; }catch(e){}
        // Fetch and store
        try{
          const sub=['a','b','c'][Math.abs(x+y)%3];
          const url=TILE_URL.replace('{s}',sub).replace('{z}',z).replace('{x}',x).replace('{y}',y);
          const resp = await fetch(url);
          if(resp.ok){ const blob=await resp.blob(); saveTile(key,blob); }
        }catch(e){}
        // Small delay to avoid hammering tile server
        await new Promise(r=>setTimeout(r,40));
      }
    }
  }
}

// ─── Custom tile layer that serves from IndexedDB when offline ───
const OfflineTileLayer = L.TileLayer.extend({
  createTile(coords, done){
    const img = document.createElement('img');
    img.setAttribute('role','presentation');
    img.crossOrigin='';
    const key = tileKey(coords.z, coords.x, coords.y);
    loadTile(key).then(blob => {
      img.src = URL.createObjectURL(blob);
      done(null, img);
    }).catch(() => {
      // Not cached → fall through to network
      const sub=['a','b','c'][Math.abs(coords.x+coords.y)%3];
      img.src = TILE_URL.replace('{s}',sub).replace('{z}',coords.z).replace('{x}',coords.x).replace('{y}',coords.y);
      img.onload  = () => { done(null,img); /* save for next time */ fetch(img.src).then(r=>r.blob()).then(b=>saveTile(key,b)).catch(()=>{}); };
      img.onerror = () => done(new Error('tile load error'), img);
    });
    return img;
  }
});

// ─── Leaflet map init ─────────────────────────────────────────────
const map = L.map('map', {
  zoomControl: false,
  attributionControl: false,
  fadeAnimation: false,
  inertia: false,
}).setView([VIZAG_LAT, VIZAG_LON], 15);

new OfflineTileLayer(TILE_URL, { maxZoom:19, subdomains:'abc' }).addTo(map);

// ─── Vehicle marker (SVG arrow) ───────────────────────────────────
const vehicleIcon = L.divIcon({
  className: '',
  html: \`<svg id="vehicle-svg" width="40" height="40" viewBox="0 0 40 40">
    <circle cx="20" cy="20" r="18" fill="rgba(0,229,255,.12)" stroke="#00e5ff" stroke-width="2"/>
    <path d="M20 4 L30 30 L20 23 L10 30 Z" fill="#00e5ff"/>
  </svg>\`,
  iconSize: [40,40],
  iconAnchor: [20,20],
});

const marker    = L.marker([VIZAG_LAT, VIZAG_LON], { icon: vehicleIcon }).addTo(map);
const polyline  = L.polyline([], { color:'#00e5ff', weight:3, opacity:.7 }).addTo(map);
const accCircle = L.circle([VIZAG_LAT, VIZAG_LON], { radius:20, color:'#00e5ff', fillColor:'#00e5ff', fillOpacity:.06, weight:1 }).addTo(map);

let pathCoords  = [];
let isFirstFix  = true;
let lastMode    = 'GPS';

// ─── Mode badge helpers ───────────────────────────────────────────
const modeBadge  = document.getElementById('mode-badge');
const speedBadge = document.getElementById('speed-badge');

function setModeBadge(mode, speedKmh){
  const isGps = (mode === 'GNSS' || mode === 'GNSS_DEGRADED');
  modeBadge.className  = 'mode-badge ' + (isGps ? 'gps' : 'dr');
  modeBadge.textContent = isGps
    ? '⬤ GPS'
    : '⬤ DEAD RECKONING';
  speedBadge.textContent = (typeof speedKmh === 'number' && speedKmh >= 0)
    ? speedKmh.toFixed(0) + ' km/h'
    : '-- km/h';
}

// ─── State update from React Native ──────────────────────────────
function updateMap(data){
  const lat      = data.lat;
  const lon      = data.lon;
  const yawDeg   = data.headingDeg || 0;
  const mode     = data.mode || 'GNSS';
  const speedKmh = data.speedKmh;
  const accM     = data.accuracyM || 20;

  // Move marker
  const pos = [lat, lon];
  marker.setLatLng(pos);

  // Rotate arrow
  const svg = document.getElementById('vehicle-svg');
  if(svg) svg.style.transform = 'rotate('+yawDeg+'deg)';

  // Accuracy circle (GPS mode only)
  const isGps = (mode === 'GNSS' || mode === 'GNSS_DEGRADED');
  if(isGps){
    accCircle.setLatLng(pos);
    accCircle.setRadius(accM);
    accCircle.setStyle({ opacity:.5, fillOpacity:.06 });
  } else {
    accCircle.setStyle({ opacity:0, fillOpacity:0 });
  }

  // Trail
  if(pathCoords.length === 0 ||
     L.latLng(pathCoords[pathCoords.length-1]).distanceTo(pos) > 1.5){
    pathCoords.push(pos);
    if(pathCoords.length > 300) pathCoords.shift();
    polyline.setLatLngs(pathCoords);
  }

  // Pan map
  if(isFirstFix){
    map.setView(pos, 16);
    isFirstFix = false;
  } else {
    // Smooth follow pan in GPS, instant in DR (avoids stuttering)
    if(isGps){
      map.panTo(pos, { animate:true, duration:.3 });
    } else {
      map.setView(pos, map.getZoom(), { animate:false });
    }
  }

  setModeBadge(mode, speedKmh);
}

// ─── Listen to React Native postMessage ──────────────────────────
document.addEventListener('message', function(e){ try{ updateMap(JSON.parse(e.data)); }catch(_){} });
window.addEventListener('message',   function(e){ try{ updateMap(JSON.parse(e.data)); }catch(_){} });
</script>
</body>
</html>`;

export function InteractiveMap({ navState, gnssAvailable }: InteractiveMapProps) {
  const webViewRef = useRef<WebView>(null);

  // Convert yawRad (ENU: 0=East, CCW) → compass bearing (CW from North)
  // ENU yaw → compass: bearing = 90 - (yawRad * 180/PI)
  const headingDeg = useMemo(() => {
    let deg = 90 - (navState.yawRad * 180) / Math.PI;
    deg = ((deg % 360) + 360) % 360;
    return Math.round(deg);
  }, [navState.yawRad]);

  const speedKmh = useMemo(
    () => Math.max(0, Math.round(navState.speedMps * 3.6)),
    [navState.speedMps],
  );

  // Default to Vizag if position not yet available
  const lat = Number.isFinite(navState.latitudeDeg) && navState.latitudeDeg !== 0
    ? navState.latitudeDeg
    : VIZAG_LAT;
  const lon = Number.isFinite(navState.longitudeDeg) && navState.longitudeDeg !== 0
    ? navState.longitudeDeg
    : VIZAG_LON;

  useEffect(() => {
    if (!webViewRef.current) return;
    const payload = JSON.stringify({
      lat,
      lon,
      headingDeg,
      mode: navState.mode,
      speedKmh,
      gnssAvailable,
      accuracyM: navState.confidence > 0 ? Math.round((1 - navState.confidence) * 50) : 20,
    });
    webViewRef.current.postMessage(payload);
  }, [lat, lon, headingDeg, navState.mode, speedKmh, gnssAvailable]);

  return (
    <View style={styles.container}>
      <WebView
        ref={webViewRef}
        originWhitelist={["*"]}
        source={{ html: MAP_HTML }}
        style={styles.webview}
        javaScriptEnabled={true}
        domStorageEnabled={true}
        allowFileAccess={true}
        allowUniversalAccessFromFileURLs={true}
        mixedContentMode="always"
        cacheEnabled={true}
        cacheMode="LOAD_CACHE_ELSE_NETWORK"
        scrollEnabled={false}
        onMessage={() => {}}
      />
    </View>
  );
}

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
