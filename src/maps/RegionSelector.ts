// Offline .roadpack region selection for Member 4 / Member 6
import { RegionSelectionResult, RoadPackRegion } from "../types";

export function pointInRegion(
  latDeg: number,
  lonDeg: number,
  region: RoadPackRegion
): boolean {
  return (
    latDeg >= region.minLatDeg &&
    latDeg <= region.maxLatDeg &&
    lonDeg >= region.minLonDeg &&
    lonDeg <= region.maxLonDeg
  );
}

export function selectRegion(
  latDeg: number,
  lonDeg: number,
  regions: RoadPackRegion[],
  currentActive: RoadPackRegion | null
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

  return { active: null, outOfCoverage: true };
}

export const BUILTIN_REGIONS: RoadPackRegion[] = [
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
