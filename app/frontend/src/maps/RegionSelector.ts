// Offline .roadpack region selection.
// Member 4 uses local road-network packages; Member 6 must choose the
// region containing the current GNSS/DR fix without reloading on every
// GPS update. This mimics that logic.

export interface RoadPackRegion {
  regionId: string;
  name: string;
  minLatDeg: number;
  maxLatDeg: number;
  minLonDeg: number;
  maxLonDeg: number;
  version: string;
  source: "demo" | "provisioned";
}

export interface RegionSelectionResult {
  active: RoadPackRegion | null;
  outOfCoverage: boolean;
}

export function pointInRegion(
  latDeg: number,
  lonDeg: number,
  region: RoadPackRegion,
): boolean {
  return (
    latDeg >= region.minLatDeg &&
    latDeg <= region.maxLatDeg &&
    lonDeg >= region.minLonDeg &&
    lonDeg <= region.maxLonDeg
  );
}

// Chooses a new active region only when the current one no longer covers
// the point; otherwise returns the incoming active region unchanged.
export function selectRegion(
  latDeg: number,
  lonDeg: number,
  regions: RoadPackRegion[],
  currentActive: RoadPackRegion | null,
): RegionSelectionResult {
  if (
    !Number.isFinite(latDeg) ||
    !Number.isFinite(lonDeg) ||
    regions.length === 0
  ) {
    return { active: currentActive, outOfCoverage: true };
  }

  if (currentActive && pointInRegion(latDeg, lonDeg, currentActive)) {
    return { active: currentActive, outOfCoverage: false };
  }

  for (const r of regions) {
    if (pointInRegion(latDeg, lonDeg, r)) {
      return { active: r, outOfCoverage: false };
    }
  }

  // Outside every provisioned region: do NOT snap to a demo city.
  return { active: null, outOfCoverage: true };
}

// Built-in demo pack + provisioned regions.
// Vizag is the PRIMARY region (first entry) — it is selected automatically
// whenever the GNSS or dead-reckoning position falls within its bounds.
// The offline map tile cache also covers exactly this region.
export const BUILTIN_REGIONS: RoadPackRegion[] = [
  {
    regionId: "in-vizag",
    name: "Visakhapatnam (Vizag)",
    // Covers the offline tile pre-cache area: ~10 km × 10 km
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

