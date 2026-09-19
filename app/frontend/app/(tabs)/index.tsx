import React, { useEffect, useMemo } from "react";
import {
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { LinearGradient } from "expo-linear-gradient";
import Icon from "@react-native-vector-icons/material-design-icons";

import {
  DataRow,
  MONO_FAMILY,
  MonoValue,
  SectionHeader,
  StatusPill,
} from "@/src/components/ui";
import { useEngine } from "@/src/engine/EngineController";
import { colors, radius, spacing } from "@/src/theme";
import {
  MapMatchStatus,
  NavigationMode,
  RejectionReason,
} from "@/src/navigation/types";
import { evaluateSpeed } from "@/src/safety/SpeedGuard";
import { InteractiveMap } from "@/src/components/InteractiveMap";

// Procedural grid fallback map
function MapGrid() {

  const cells = 12;
  const rows = [] as React.ReactNode[];
  for (let i = 0; i < cells; i++) {
    rows.push(
      <View
        key={`h${i}`}
        style={[
          styles.gridLine,
          { top: `${(i / cells) * 100}%`, left: 0, right: 0, height: 1 },
        ]}
      />,
    );
    rows.push(
      <View
        key={`v${i}`}
        style={[
          styles.gridLine,
          { left: `${(i / cells) * 100}%`, top: 0, bottom: 0, width: 1 },
        ]}
      />,
    );
  }
  return (
    <View style={styles.mapWrap} pointerEvents="none">
      <LinearGradient
        colors={["#0B1218", "#050708"]}
        style={StyleSheet.absoluteFillObject}
      />
      {rows}
      {/* Fake road strokes */}
      <View style={[styles.road, { top: "48%", left: 0, right: 0, height: 3 }]} />
      <View style={[styles.road, { left: "36%", top: 0, bottom: 0, width: 3 }]} />
    </View>
  );
}

export default function NavigationScreen() {
  const insets = useSafeAreaInsets();
  const {
    navState,
    status,
    requestLocation,
  } = useEngine();

  useEffect(() => {
    if (status.locationPermission === "unknown") {
      requestLocation();
    }
  }, [status.locationPermission]);

  const speedEval = useMemo(() => evaluateSpeed(navState.speedMps), [navState.speedMps]);
  const kmhText = speedEval.valid && speedEval.kmh !== null ? speedEval.kmh.toFixed(0) : "--";
  const kmhSubText = speedEval.valid ? "km/h" : rejectionLabel(speedEval.reason);

  const modeTone =
    navState.mode === NavigationMode.GNSS
      ? "ok"
      : navState.mode === NavigationMode.GNSS_DEGRADED
        ? "warn"
        : navState.mode === NavigationMode.DEAD_RECKONING
          ? "warn"
          : navState.mode === NavigationMode.FAULT
            ? "bad"
            : "neutral";
  const gnssTone = status.gnssAvailable && status.locationPermission === "granted" ? "ok" : "bad";
  const mapTone =
    navState.mapMatchStatus === MapMatchStatus.MATCHED
      ? "ok"
      : navState.mapMatchStatus === MapMatchStatus.DEGRADED
        ? "warn"
        : "neutral";

  const headingDeg = ((navState.yawRad * 180) / Math.PI + 360) % 360;

  // Position marker converted from active-region bounds to on-screen %.
  const marker = markerPosition(navState);

  return (
    <View style={[styles.root, { paddingTop: insets.top }]} testID="nav-screen">
      <InteractiveMap navState={navState} gnssAvailable={status.gnssAvailable} />


      {/* Vehicle marker */}
      <View
        pointerEvents="none"
        style={[
          styles.markerWrap,
          { left: `${marker.xPct}%`, top: `${marker.yPct}%` },
        ]}
      >
        <View
          style={[
            styles.markerHalo,
            { borderColor: modeTone === "warn" ? colors.warning : colors.brandPrimary },
          ]}
        />
        <View
          style={[
            styles.marker,
            { transform: [{ rotate: `${headingDeg}deg` }] },
          ]}
          testID="vehicle-marker"
        >
          <Icon name="navigation" size={22} color={colors.onBrandPrimary} />
        </View>
      </View>

      {/* Top status row */}
      <View style={[styles.topBar, { top: insets.top + spacing.sm }]}>
        <StatusPill
          tone={modeTone as any}
          label={`MODE • ${navState.mode}`}
          testID="mode-pill"
        />
        <StatusPill
          tone={gnssTone}
          label={`GNSS • ${status.gnssAvailable ? "OK" : status.locationPermission === "denied" ? "DENIED" : "SEARCHING"}`}
          testID="gnss-pill"
        />
      </View>

      {/* Bottom HUD */}
      <View style={[styles.hud, { paddingBottom: insets.bottom + spacing.lg }]}
        testID="hud-panel"
      >
        <View style={styles.hudTopRow}>
          <View style={styles.speedBlock}>
            <MonoValue
              value={kmhText}
              size={72}
              color={speedEval.valid ? colors.brandPrimary : colors.error}
              testID="speed-value"
            />
            <Text
              style={[styles.speedUnit, { color: speedEval.valid ? colors.onSurfaceTertiary : colors.error }]}
              testID="speed-unit"
            >
              {kmhSubText.toUpperCase()}
            </Text>
          </View>
          <View style={styles.hudRight}>
            <MiniStat label="HEADING" value={`${headingDeg.toFixed(0)}°`} testID="heading-stat" />
            <MiniStat
              label="CONF"
              value={navState.confidence.toFixed(2)}
              testID="conf-stat"
            />
            <MiniStat
              label="ACC"
              value={
                status.gnssAccuracyM !== null
                  ? `${status.gnssAccuracyM.toFixed(0)}m`
                  : "--"
              }
              testID="acc-stat"
            />
          </View>
        </View>

        <View style={styles.divider} />

        <View style={styles.pillRow}>
          <StatusPill
            tone={mapTone as any}
            label={`MAP • ${navState.mapMatchStatus}`}
            testID="map-pill"
          />
          <StatusPill
            tone={navState.mapRegionId ? "info" : "neutral"}
            label={`REGION • ${navState.mapRegionId ?? "NONE"}`}
            testID="region-pill"
          />
        </View>

        <View style={styles.metaRow}>
          <Text style={styles.metaText}>
            LAT{" "}
            <Text style={styles.metaMono}>{navState.latitudeDeg.toFixed(5)}</Text>
          </Text>
          <Text style={styles.metaText}>
            LON{" "}
            <Text style={styles.metaMono}>{navState.longitudeDeg.toFixed(5)}</Text>
          </Text>
        </View>

        {speedEval.reason !== RejectionReason.NONE ? (
          <View style={styles.rejectBanner} testID="reject-banner">
            <Icon name="alert-octagon" size={16} color={colors.error} />
            <Text style={styles.rejectText}>
              SAFETY GUARD: {speedEval.reason}
            </Text>
          </View>
        ) : null}
      </View>

      {status.locationPermission === "denied" ? (
        <Pressable
          style={[styles.permBtn, { bottom: insets.bottom + 220 }]}
          onPress={requestLocation}
          testID="grant-location-btn"
        >
          <Text style={styles.permText}>Grant Location Permission</Text>
        </Pressable>
      ) : null}
    </View>
  );
}

function MiniStat({
  label,
  value,
  testID,
}: {
  label: string;
  value: string;
  testID?: string;
}) {
  return (
    <View style={styles.miniStat} testID={testID}>
      <Text style={styles.miniLabel}>{label}</Text>
      <MonoValue value={value} size={16} color={colors.onSurface} />
    </View>
  );
}

function rejectionLabel(r: RejectionReason): string {
  switch (r) {
    case RejectionReason.NAN_SPEED:
      return "NaN";
    case RejectionReason.INF_SPEED:
      return "INFINITY";
    case RejectionReason.NEGATIVE_SPEED:
      return "NEGATIVE";
    case RejectionReason.ABSURD_SPEED:
      return "SPEED UNAVAILABLE";
    default:
      return "UNAVAILABLE";
  }
}

// Marker position: if no valid nav position, center. Otherwise use a
// simple sinusoidal mapping around center so the marker moves visibly.
function markerPosition(state: {
  latitudeDeg: number;
  longitudeDeg: number;
}): { xPct: number; yPct: number } {
  if (!Number.isFinite(state.latitudeDeg) || !Number.isFinite(state.longitudeDeg)) {
    return { xPct: 50, yPct: 40 };
  }
  const lat = state.latitudeDeg;
  const lon = state.longitudeDeg;
  const x = 50 + 30 * Math.sin(lon * 5);
  const y = 40 + 20 * Math.cos(lat * 5);
  return { xPct: Math.max(5, Math.min(95, x)), yPct: Math.max(5, Math.min(75, y)) };
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: colors.surface },
  mapWrap: { ...StyleSheet.absoluteFillObject },
  gridLine: {
    position: "absolute",
    backgroundColor: "#12181E",
  },
  road: {
    position: "absolute",
    backgroundColor: "#1F2A33",
  },
  markerWrap: {
    position: "absolute",
    marginLeft: -18,
    marginTop: -18,
    width: 36,
    height: 36,
    alignItems: "center",
    justifyContent: "center",
  },
  markerHalo: {
    position: "absolute",
    width: 36,
    height: 36,
    borderRadius: 999,
    borderWidth: 2,
    opacity: 0.7,
  },
  marker: {
    width: 28,
    height: 28,
    borderRadius: 999,
    backgroundColor: colors.brandPrimary,
    alignItems: "center",
    justifyContent: "center",
  },
  topBar: {
    position: "absolute",
    left: spacing.lg,
    right: spacing.lg,
    flexDirection: "row",
    justifyContent: "space-between",
    gap: spacing.sm,
  },
  hud: {
    position: "absolute",
    left: 0,
    right: 0,
    bottom: 0,
    paddingHorizontal: spacing.lg,
    paddingTop: spacing.lg,
    backgroundColor: "rgba(21,23,28,0.94)",
    borderTopWidth: 1,
    borderColor: colors.border,
    borderTopLeftRadius: radius.lg,
    borderTopRightRadius: radius.lg,
    gap: spacing.md,
  },
  hudTopRow: { flexDirection: "row", alignItems: "flex-end", gap: spacing.lg },
  speedBlock: { flex: 1 },
  speedUnit: {
    fontFamily: MONO_FAMILY,
    fontSize: 12,
    letterSpacing: 2,
    marginTop: -8,
  },
  hudRight: {
    gap: 6,
    alignItems: "flex-end",
    minWidth: 90,
  },
  miniStat: { alignItems: "flex-end" },
  miniLabel: {
    fontFamily: MONO_FAMILY,
    color: colors.onSurfaceTertiary,
    fontSize: 10,
    letterSpacing: 1.5,
  },
  divider: {
    height: 1,
    backgroundColor: colors.divider,
  },
  pillRow: { flexDirection: "row", gap: spacing.sm, flexWrap: "wrap" },
  metaRow: {
    flexDirection: "row",
    justifyContent: "space-between",
    paddingVertical: 4,
  },
  metaText: {
    color: colors.onSurfaceTertiary,
    fontSize: 12,
    letterSpacing: 1,
  },
  metaMono: {
    color: colors.onSurface,
    fontFamily: MONO_FAMILY,
  },
  rejectBanner: {
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.sm,
    padding: spacing.md,
    borderRadius: radius.md,
    backgroundColor: "#2A060C",
    borderWidth: 1,
    borderColor: "#5A0F1B",
  },
  rejectText: {
    color: colors.error,
    fontFamily: MONO_FAMILY,
    fontSize: 12,
    letterSpacing: 1,
    fontWeight: "700",
  },
  permBtn: {
    position: "absolute",
    alignSelf: "center",
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.md,
    backgroundColor: colors.brandPrimary,
    borderRadius: radius.pill,
  },
  permText: {
    color: colors.onBrandPrimary,
    fontFamily: MONO_FAMILY,
    fontWeight: "800",
    letterSpacing: 1,
  },
});
