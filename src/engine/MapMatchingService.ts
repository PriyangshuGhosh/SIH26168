// Member 4 Offline Map Matcher
// Faithfully matches member4_map_matching/python/sih26168_map_matching/map_matcher.py
// & member4_map_matching/cpp/include/member4/MapMatchingEngine.hpp
//
// Implements road projection, candidate searching, emission probabilities,
// and path snapping for offline .roadpack networks.

export interface RoadPoint {
  lat: number;
  lon: number;
}

export interface MapSegment {
  segmentId: number;
  label: string;
  lengthM: number;
  headingRad: number;
  points: RoadPoint[];
}

export interface MapMatchResult {
  matched: boolean;
  snappedLat: number;
  snappedLon: number;
  matchedSegmentId: number;
  matchedSegmentLabel: string;
  distanceToRoadMeters: number;
  headingRad: number;
  confidence: number;
  // Heading residual between vehicle yaw and road direction, radians.
  headingErrorRad: number;
}

// Built-in Visakhapatnam Simhachalam Tunnel corridor road segments
export const VIZAG_SIMHACHALAM_SEGMENTS: MapSegment[] = [
  {
    segmentId: 101,
    label: "NH16_SIMHACHALAM_APPROACH",
    lengthM: 850,
    headingRad: 0.65,
    points: [
      { lat: 17.7340, lon: 83.2720 },
      { lat: 17.7420, lon: 83.2810 },
    ],
  },
  {
    segmentId: 102,
    label: "SIMHACHALAM_TUNNEL_EASTBOUND",
    lengthM: 450,
    headingRad: 0.72,
    points: [
      { lat: 17.7420, lon: 83.2810 },
      { lat: 17.7485, lon: 83.2885 },
      { lat: 17.7550, lon: 83.2960 },
    ],
  },
  {
    segmentId: 103,
    label: "MADHURAWADA_EXPRESSWAY",
    lengthM: 1200,
    headingRad: 0.70,
    points: [
      { lat: 17.7550, lon: 83.2960 },
      { lat: 17.7680, lon: 83.3100 },
    ],
  },
  {
    segmentId: 104,
    label: "RUSHIKONDA_BYPASS",
    lengthM: 1500,
    headingRad: 0.75,
    points: [
      { lat: 17.7680, lon: 83.3100 },
      { lat: 17.7820, lon: 83.3250 },
    ],
  },
];

export class MapMatcher {
  private segments: MapSegment[];
  private maxSearchRadiusMeters = 50.0;
  private minConfidence = 0.35;

  constructor(segments: MapSegment[] = VIZAG_SIMHACHALAM_SEGMENTS) {
    this.segments = segments;
  }

  loadSegments(segments: MapSegment[]): void {
    this.segments = segments;
  }

  // Snap raw coordinates to nearest valid road segment
  match(lat: number, lon: number, headingRad?: number): MapMatchResult {
    let bestDist = Infinity;
    let bestSnap = { lat, lon };
    let bestSegment: MapSegment | null = null;
    let bestHeading = headingRad ?? 0;

    for (const seg of this.segments) {
      for (let i = 0; i < seg.points.length - 1; i++) {
        const p1 = seg.points[i];
        const p2 = seg.points[i + 1];

        const { snappedLat, snappedLon, distM } = this.projectPointToSegment(
          lat,
          lon,
          p1.lat,
          p1.lon,
          p2.lat,
          p2.lon
        );

        if (distM < bestDist) {
          bestDist = distM;
          bestSnap = { lat: snappedLat, lon: snappedLon };
          bestSegment = seg;
          bestHeading = seg.headingRad;
        }
      }
    }

    if (bestDist <= this.maxSearchRadiusMeters && bestSegment) {
      // Confidence decreases with perpendicular distance from road centerline (Gaussian emission)
      const sigma = 10.0;
      const confidence = Math.max(
        this.minConfidence,
        Math.exp(-(bestDist * bestDist) / (2 * sigma * sigma))
      );

      return {
        matched: true,
        snappedLat: bestSnap.lat,
        snappedLon: bestSnap.lon,
        matchedSegmentId: bestSegment.segmentId,
        matchedSegmentLabel: bestSegment.label,
        distanceToRoadMeters: bestDist,
        headingRad: bestHeading,
        confidence,
        headingErrorRad: this.angularDifference(headingRad ?? bestHeading, bestHeading),
      };
    }

    return {
      matched: false,
      snappedLat: lat,
      snappedLon: lon,
      matchedSegmentId: 0,
      matchedSegmentLabel: "OFF_ROAD",
      distanceToRoadMeters: bestDist,
      headingRad: headingRad ?? 0,
      confidence: 0,
      headingErrorRad: 0,
    };
  }

  private angularDifference(a: number, b: number): number {
    const twoPi = 2 * Math.PI;
    let d = (a - b) % twoPi;
    if (d > Math.PI) d -= twoPi;
    if (d < -Math.PI) d += twoPi;
    return d;
  }

  private projectPointToSegment(
    lat: number,
    lon: number,
    lat1: number,
    lon1: number,
    lat2: number,
    lon2: number
  ): { snappedLat: number; snappedLon: number; distM: number } {
    // Project in flat ENU approximation around lat1, lon1
    const cosLat = Math.cos((lat1 * Math.PI) / 180);
    const x0 = (lon - lon1) * 111320 * cosLat;
    const y0 = (lat - lat1) * 111320;
    const x2 = (lon2 - lon1) * 111320 * cosLat;
    const y2 = (lat2 - lat1) * 111320;

    const segLenSq = x2 * x2 + y2 * y2;
    if (segLenSq < 1e-4) {
      const dist = Math.hypot(x0, y0);
      return { snappedLat: lat1, snappedLon: lon1, distM: dist };
    }

    // Projection factor t
    let t = (x0 * x2 + y0 * y2) / segLenSq;
    t = Math.max(0, Math.min(1, t));

    const projX = t * x2;
    const projY = t * y2;

    const distM = Math.hypot(x0 - projX, y0 - projY);
    const snappedLat = lat1 + projY / 111320;
    const snappedLon = lon1 + projX / (111320 * cosLat);

    return { snappedLat, snappedLon, distM };
  }
}

export const offlineMapMatcher = new MapMatcher();
