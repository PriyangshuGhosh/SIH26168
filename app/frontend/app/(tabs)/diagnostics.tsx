import React from "react";
import { ScrollView, StyleSheet, Text, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { DataRow, SectionHeader, StatusPill } from "@/src/components/ui";
import { useEngine } from "@/src/engine/EngineController";
import { colors, spacing } from "@/src/theme";
import { NavigationMode, MapMatchStatus } from "@/src/navigation/types";

export default function DiagnosticsScreen() {
  const insets = useSafeAreaInsets();
  const { navState, sensorStats, status } = useEngine();

  return (
    <View style={styles.root} testID="diagnostics-screen">
      <ScrollView
        contentContainerStyle={{
          paddingTop: insets.top + spacing.md,
          paddingBottom: spacing.xxxl,
        }}
      >
        <Text style={styles.title}>DIAGNOSTICS</Text>
        <Text style={styles.subtitle}>Live telemetry — 8 Hz UI poll</Text>

        <SectionHeader
          title="SENSOR PIPELINE"
          right={
            <StatusPill
              tone={sensorStats.accelHz > 30 ? "ok" : "warn"}
              label={sensorStats.accelHz > 30 ? "STREAMING" : "IDLE"}
              testID="sensor-status-pill"
            />
          }
        />
        <View style={styles.card}>
          <DataRow
            label="ACCELEROMETER Hz"
            value={sensorStats.accelHz.toFixed(1)}
            tone={sensorStats.accelHz > 30 ? "ok" : "warn"}
            testID="accel-hz-row"
          />
          <DataRow
            label="GYROSCOPE Hz"
            value={sensorStats.gyroHz.toFixed(1)}
            tone={sensorStats.gyroHz > 30 ? "ok" : "warn"}
            testID="gyro-hz-row"
          />
          <DataRow
            label="EMITTED PAIRED Hz"
            value={sensorStats.emittedHz.toFixed(1)}
            testID="emitted-hz-row"
          />
          <DataRow
            label="LAST PAIRING Δ (ms)"
            value={sensorStats.lastPairingDeltaMs.toFixed(2)}
            testID="pairing-delta-row"
          />
          <DataRow
            label="DROPPED (REGRESSION)"
            value={String(sensorStats.droppedRegression)}
            tone={sensorStats.droppedRegression > 0 ? "warn" : undefined}
            testID="drop-regression-row"
          />
          <DataRow
            label="DROPPED (STALE)"
            value={String(sensorStats.droppedStale)}
            tone={sensorStats.droppedStale > 0 ? "warn" : undefined}
            testID="drop-stale-row"
          />
          <DataRow
            label="DROPPED (NO PAIR)"
            value={String(sensorStats.droppedNoPair)}
            testID="drop-nopair-row"
          />
          <DataRow
            label="DUPLICATES SKIPPED"
            value={String(sensorStats.duplicatesSkipped)}
            testID="duplicates-row"
          />
        </View>

        <SectionHeader
          title="GNSS"
          right={
            <StatusPill
              tone={status.gnssAvailable ? "ok" : "bad"}
              label={status.gnssAvailable ? "OK" : "UNAVAILABLE"}
              testID="gnss-status-pill"
            />
          }
        />
        <View style={styles.card}>
          <DataRow
            label="PERMISSION"
            value={status.locationPermission.toUpperCase()}
            tone={status.locationPermission === "granted" ? "ok" : "warn"}
            testID="perm-row"
          />
          <DataRow
            label="ACCURACY (m)"
            value={
              status.gnssAccuracyM !== null
                ? status.gnssAccuracyM.toFixed(1)
                : "--"
            }
            testID="accuracy-row"
          />
          <DataRow
            label="LAST FIX AGE (ms)"
            value={status.gnssAgeMs >= 0 ? String(status.gnssAgeMs) : "--"}
            tone={status.gnssAgeMs > 3000 ? "bad" : "ok"}
            testID="fix-age-row"
          />
        </View>

        <SectionHeader
          title="MEMBER 5 ENGINE"
          right={
            <StatusPill
              tone={
                navState.mode === NavigationMode.FAULT
                  ? "bad"
                  : navState.mode === NavigationMode.UNINITIALIZED
                    ? "neutral"
                    : "ok"
              }
              label={navState.mode}
              testID="engine-mode-pill"
            />
          }
        />
        <View style={styles.card}>
          <DataRow
            label="INITIALIZED"
            value={status.engineInitialized ? "TRUE" : "FALSE"}
            tone={status.engineInitialized ? "ok" : "bad"}
            testID="engine-init-row"
          />
          <DataRow
            label="ML MODEL (ONNX)"
            value={status.mlModelLoaded ? "LOADED" : (status.mlModelError ? "ERROR" : "LOADING...")}
            tone={status.mlModelLoaded ? "ok" : (status.mlModelError ? "bad" : "warn")}
            testID="ml-model-row"
          />
          <DataRow
            label="SPEED (m/s)"
            value={
              Number.isFinite(navState.speedMps)
                ? navState.speedMps.toFixed(3)
                : String(navState.speedMps)
            }
            testID="speed-mps-row"
          />

          <DataRow
            label="POSITION"
            value={`${navState.latitudeDeg.toFixed(5)}, ${navState.longitudeDeg.toFixed(5)}`}
            testID="pos-row"
          />
          <DataRow
            label="YAW (rad)"
            value={navState.yawRad.toFixed(3)}
            testID="yaw-row"
          />
          <DataRow
            label="CONFIDENCE"
            value={navState.confidence.toFixed(3)}
            testID="conf-row"
          />
          <DataRow
            label="VALIDITY BITS"
            value={`0x${navState.validity.toString(16).padStart(2, "0")}`}
            testID="validity-row"
          />
          <DataRow
            label="LAST REJECTION"
            value={navState.lastRejection}
            tone={
              navState.lastRejection === "NONE" ? undefined : "warn"
            }
            testID="last-rejection-row"
          />
        </View>

        <SectionHeader
          title="MEMBER 4 MAP MATCH"
          right={
            <StatusPill
              tone={
                navState.mapMatchStatus === MapMatchStatus.MATCHED
                  ? "ok"
                  : navState.mapMatchStatus === MapMatchStatus.DEGRADED
                    ? "warn"
                    : "neutral"
              }
              label={navState.mapMatchStatus}
              testID="map-match-pill"
            />
          }
        />
        <View style={styles.card}>
          <DataRow
            label="ACTIVE REGION"
            value={navState.mapRegionId ?? "NONE"}
            testID="active-region-row"
          />
        </View>

        <SectionHeader title="ERRORS" />
        <View style={styles.card}>
          <DataRow
            label="LAST NATIVE ERROR"
            value={status.lastNativeError ?? "NONE"}
            tone={status.lastNativeError ? "bad" : undefined}
            testID="last-native-error-row"
          />
          <DataRow
            label="LAST MAP ERROR"
            value={status.lastMapError ?? "NONE"}
            testID="last-map-error-row"
          />
          <DataRow
            label="LAST UI SPEED REJECTION"
            value={status.lastUiSpeedRejection}
            tone={
              status.lastUiSpeedRejection === "NONE" ? undefined : "bad"
            }
            testID="last-ui-reject-row"
          />
        </View>
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: colors.surface },
  title: {
    color: colors.onSurface,
    fontSize: 24,
    fontWeight: "800",
    paddingHorizontal: spacing.lg,
    letterSpacing: 3,
  },
  subtitle: {
    color: colors.onSurfaceTertiary,
    fontSize: 12,
    paddingHorizontal: spacing.lg,
    letterSpacing: 1,
    marginTop: 2,
  },
  card: {
    backgroundColor: colors.surfaceSecondary,
    marginHorizontal: spacing.lg,
    borderRadius: 12,
    borderWidth: 1,
    borderColor: colors.border,
  },
});
