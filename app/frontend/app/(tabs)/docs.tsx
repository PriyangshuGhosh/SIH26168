import React from "react";
import { ScrollView, StyleSheet, Text, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { MONO_FAMILY, SectionHeader, StatusPill } from "@/src/components/ui";
import { colors, spacing } from "@/src/theme";

interface DocRow {
  feature: string;
  status: "VALIDATED" | "NOT_VALIDATED" | "PARTIAL";
  note: string;
}

// Truthful validation matrix — what actually works inside this Expo
// prototype vs what needs the native Android + JNI + libmember5 stack.
const MATRIX: DocRow[] = [
  {
    feature: "NavigationState contract (types.ts)",
    status: "VALIDATED",
    note: "TS mirrors Member 5 C ABI: fields, units, validity bitfield, mode/status enums.",
  },
  {
    feature: "Timestamp-aware IMU pairing",
    status: "VALIDATED",
    note: "SensorPipeline: monotonic guard, stale/regression drops, ring buffer nearest-ts pairing, Hz metering.",
  },
  {
    feature: "SpeedGuard: NaN/Inf/negative/absurd → 'unavailable'",
    status: "VALIDATED",
    note: "Centralized m/s → km/h. Never clamps; surfaces reason.",
  },
  {
    feature: "700 km/h regression trigger + UI guard",
    status: "VALIDATED",
    note: "Simulation screen injects 194.4 m/s; HUD renders 'SPEED UNAVAILABLE' + reason banner.",
  },
  {
    feature: "Offline map region selection (bounding box)",
    status: "VALIDATED",
    note: "RegionSelector caches active region, chooses by lat/lon, reports out-of-coverage.",
  },
  {
    feature: "GNSS outage → dead-reckoning mode transition",
    status: "PARTIAL",
    note: "JS engine transitions to DEAD_RECKONING when GNSS stale. Position propagates from last v_ENU. NOT a validated EKF — Member 3 replacement pending.",
  },
  {
    feature: "GNSS recovery reconciliation",
    status: "PARTIAL",
    note: "Engine snaps to fresh GNSS when it returns; no covariance handoff.",
  },
  {
    feature: "expo-sensors real IMU ingestion (Android/iOS)",
    status: "PARTIAL",
    note: "Accel converted g → m/s². Web preview values are DOM DeviceMotion — not physically calibrated.",
  },
  {
    feature: "expo-location real GNSS ingestion",
    status: "PARTIAL",
    note: "Uses BestForNavigation. Web fallback is browser Geolocation — not the same as Android FLP.",
  },
  {
    feature: "Member 5 C ABI (idr_init / idr_feed_imu / idr_feed_gnss / idr_get_state)",
    status: "NOT_VALIDATED",
    note: "This app uses a TS SIMULATOR of Member 5. Real JNI bridge + libmember5.so remain in the native Android project.",
  },
  {
    feature: "Member 1 speed ML model",
    status: "NOT_VALIDATED",
    note: "Not runnable in Expo prototype. ONNX inference stays native.",
  },
  {
    feature: "Member 2 phone→vehicle IMU alignment quaternion",
    status: "NOT_VALIDATED",
    note: "Not executed here. Contract preserved so a real alignment quaternion can drive engine yaw upstream.",
  },
  {
    feature: "Member 3 EKF sensor fusion",
    status: "NOT_VALIDATED",
    note: "Only a first-order dead-reckoning stub is present. Not the production EKF.",
  },
  {
    feature: "Member 4 .roadpack loading & map matching",
    status: "NOT_VALIDATED",
    note: "Region selection logic is present; actual road-network snap-to-road is stubbed.",
  },
  {
    feature: "arm64-v8a native library build + APK packaging",
    status: "NOT_VALIDATED",
    note: "This is an Expo/React Native prototype — Android Gradle/NDK is out of scope here.",
  },
  {
    feature: "Physical Android hardware validation",
    status: "NOT_VALIDATED",
    note: "No physical device available in this environment.",
  },
];

export default function DocsScreen() {
  const insets = useSafeAreaInsets();

  const grouped = {
    VALIDATED: MATRIX.filter((r) => r.status === "VALIDATED"),
    PARTIAL: MATRIX.filter((r) => r.status === "PARTIAL"),
    NOT_VALIDATED: MATRIX.filter((r) => r.status === "NOT_VALIDATED"),
  };

  return (
    <View style={styles.root} testID="docs-screen">
      <ScrollView
        contentContainerStyle={{
          paddingTop: insets.top + spacing.md,
          paddingBottom: spacing.xxxl,
        }}
      >
        <Text style={styles.title}>VALIDATION MATRIX</Text>
        <Text style={styles.subtitle}>
          Truthful status of every Member 6 behavior in this Expo prototype.
        </Text>

        <SectionHeader
          title={`VALIDATED  (${grouped.VALIDATED.length})`}
          right={<StatusPill tone="ok" label="OK" testID="validated-count" />}
        />
        <View style={styles.card}>
          {grouped.VALIDATED.map((r) => (
            <MatrixRow key={r.feature} row={r} />
          ))}
        </View>

        <SectionHeader
          title={`PARTIAL  (${grouped.PARTIAL.length})`}
          right={<StatusPill tone="warn" label="LIMITED" testID="partial-count" />}
        />
        <View style={styles.card}>
          {grouped.PARTIAL.map((r) => (
            <MatrixRow key={r.feature} row={r} />
          ))}
        </View>

        <SectionHeader
          title={`NOT VALIDATED  (${grouped.NOT_VALIDATED.length})`}
          right={<StatusPill tone="bad" label="NATIVE ONLY" testID="not-validated-count" />}
        />
        <View style={styles.card}>
          {grouped.NOT_VALIDATED.map((r) => (
            <MatrixRow key={r.feature} row={r} />
          ))}
        </View>

        <SectionHeader title="INTENDED PIPELINE" />
        <View style={styles.pipelineCard}>
          <Text style={styles.pipelineText}>
            Android sensors → M2 alignment → M1 speed → M3 EKF → M4 map match → M5 native
            engine → JNI → Member 6 Android UI
          </Text>
          <Text style={styles.pipelineNote}>
            Member 6 must consume Member 5 via C ABI. This prototype swaps that C
            ABI for a TS simulator so the contract stays testable.
          </Text>
        </View>
      </ScrollView>
    </View>
  );
}

function MatrixRow({ row }: { row: DocRow }) {
  const tone =
    row.status === "VALIDATED" ? "ok" : row.status === "PARTIAL" ? "warn" : "bad";
  return (
    <View
      style={styles.matrixRow}
      testID={`matrix-row-${row.status.toLowerCase()}`}
    >
      <View style={{ flex: 1, paddingRight: spacing.md }}>
        <Text style={styles.feature}>{row.feature}</Text>
        <Text style={styles.note}>{row.note}</Text>
      </View>
      <StatusPill
        tone={tone as any}
        label={row.status.replace("_", " ")}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: colors.surface },
  title: {
    color: colors.onSurface,
    fontSize: 22,
    fontWeight: "800",
    paddingHorizontal: spacing.lg,
    letterSpacing: 2,
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
    overflow: "hidden",
  },
  matrixRow: {
    flexDirection: "row",
    alignItems: "center",
    padding: spacing.md,
    paddingHorizontal: spacing.lg,
    borderBottomColor: colors.divider,
    borderBottomWidth: 1,
  },
  feature: {
    color: colors.onSurface,
    fontSize: 13,
    fontWeight: "700",
    fontFamily: MONO_FAMILY,
  },
  note: {
    color: colors.onSurfaceTertiary,
    fontSize: 12,
    marginTop: 4,
    lineHeight: 17,
  },
  pipelineCard: {
    backgroundColor: colors.surfaceSecondary,
    marginHorizontal: spacing.lg,
    padding: spacing.lg,
    borderRadius: 12,
    borderWidth: 1,
    borderColor: colors.border,
    marginTop: spacing.sm,
  },
  pipelineText: {
    color: colors.brandPrimary,
    fontFamily: MONO_FAMILY,
    fontSize: 13,
    lineHeight: 20,
    fontWeight: "700",
  },
  pipelineNote: {
    color: colors.onSurfaceTertiary,
    fontSize: 12,
    marginTop: spacing.sm,
    lineHeight: 18,
  },
});
