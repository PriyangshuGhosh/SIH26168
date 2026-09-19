import React from "react";
import {
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  Switch,
  Text,
  View,
} from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import * as Haptics from "expo-haptics";
import Icon from "@react-native-vector-icons/material-design-icons";

import { MONO_FAMILY, SectionHeader, StatusPill } from "@/src/components/ui";
import { useEngine } from "@/src/engine/EngineController";
import { colors, radius, spacing } from "@/src/theme";
import { Scenario } from "@/src/simulation/SyntheticDrive";

const SCENARIOS: { key: Scenario; label: string; desc: string }[] = [
  { key: "STATIONARY", label: "STATIONARY", desc: "Vehicle at rest" },
  { key: "CONSTANT_50KMH", label: "CONSTANT 50 KM/H", desc: "Steady cruise" },
  { key: "ACCELERATION", label: "ACCELERATION", desc: "0 → 30 m/s over 20s" },
  { key: "BRAKING", label: "BRAKING", desc: "20 → 0 m/s decel" },
  { key: "TURN", label: "TURN", desc: "Yaw rate 0.5 rad/s at 40 km/h" },
  { key: "NOISY_IMU", label: "NOISY IMU", desc: "High-noise accel/gyro" },
  { key: "GNSS_OUTAGE", label: "GNSS OUTAGE", desc: "Dead-reckoning mode" },
];

export default function SimulationScreen() {
  const insets = useSafeAreaInsets();
  const {
    status,
    enableSyntheticMode,
    setScenario,
    triggerRegression700,
    clearInjection,
    simulateEngineFault,
  } = useEngine();

  return (
    <View style={styles.root} testID="simulation-screen">
      <ScrollView
        contentContainerStyle={{
          paddingTop: insets.top + spacing.md,
          paddingBottom: spacing.xxxl,
        }}
      >
        <Text style={styles.title}>SIMULATION</Text>
        <Text style={styles.subtitle}>
          Developer-only synthetic scenarios. Never enabled in production.
        </Text>

        <SectionHeader
          title="SYNTHETIC DRIVE"
          right={
            <StatusPill
              tone={status.syntheticEnabled ? "warn" : "neutral"}
              label={status.syntheticEnabled ? "ACTIVE" : "IDLE"}
              testID="synth-status-pill"
            />
          }
        />
        <View style={styles.card}>
          <View style={styles.row}>
            <View style={{ flex: 1 }}>
              <Text style={styles.rowLabel}>Enable synthetic mode</Text>
              <Text style={styles.rowHelp}>
                Feeds fabricated IMU + GNSS into the engine.
              </Text>
            </View>
            <Switch
              value={status.syntheticEnabled}
              onValueChange={(v) => {
                Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium);
                enableSyntheticMode(v);
              }}
              trackColor={{ true: colors.brandPrimary, false: colors.surfaceTertiary }}
              thumbColor={colors.onBrand}
              testID="synth-enable-switch"
            />
          </View>
        </View>

        <SectionHeader title="SCENARIO" />
        <View style={styles.card}>
          {SCENARIOS.map((s) => {
            const active = status.scenario === s.key;
            return (
              <Pressable
                key={s.key}
                onPress={() => {
                  Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
                  setScenario(s.key);
                }}
                style={[
                  styles.scenarioRow,
                  active && { backgroundColor: colors.brandTertiary },
                ]}
                testID={`scenario-${s.key}`}
              >
                <Icon
                  name={active ? "radiobox-marked" : "radiobox-blank"}
                  size={20}
                  color={active ? colors.brandPrimary : colors.onSurfaceTertiary}
                />
                <View style={{ flex: 1, marginLeft: spacing.md }}>
                  <Text
                    style={[
                      styles.scenarioLabel,
                      active && { color: colors.brandPrimary },
                    ]}
                  >
                    {s.label}
                  </Text>
                  <Text style={styles.rowHelp}>{s.desc}</Text>
                </View>
              </Pressable>
            );
          })}
        </View>

        <SectionHeader title="ENGINE FAULT INJECTION" />
        <View style={styles.card}>
          <View style={styles.row}>
            <View style={{ flex: 1 }}>
              <Text style={styles.rowLabel}>Simulate engine fault</Text>
              <Text style={styles.rowHelp}>
                Forces NavigationMode.FAULT. UI must degrade gracefully.
              </Text>
            </View>
            <Switch
              onValueChange={(v) => {
                Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium);
                simulateEngineFault(v);
              }}
              trackColor={{ true: colors.error, false: colors.surfaceTertiary }}
              testID="engine-fault-switch"
            />
          </View>
        </View>

        <SectionHeader title="REGRESSION TRIGGERS" />
        <View style={{ paddingHorizontal: spacing.lg }}>
          <Pressable
            style={styles.regressionBtn}
            onPress={() => {
              Haptics.notificationAsync(Haptics.NotificationFeedbackType.Warning);
              triggerRegression700();
            }}
            testID="regression-700-btn"
          >
            <Icon name="alert-octagon" size={22} color={colors.onError} />
            <Text style={styles.regressionText}>INJECT 194.4 m/s (≈700 km/h)</Text>
          </Pressable>
          <Text style={styles.regressionHelp}>
            Publishes an impossible NavigationState.speedMps to verify
            Member 6's SpeedGuard never surfaces it on the HUD.
          </Text>

          <View style={{ height: spacing.sm }} />

          <Pressable
            style={styles.clearBtn}
            onPress={() => {
              Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
              clearInjection();
            }}
            testID="clear-injection-btn"
          >
            <Text style={styles.clearText}>CLEAR INJECTION</Text>
          </Pressable>

          {status.simulationInjectedSpeedMps !== null ? (
            <View style={styles.injectedBanner} testID="injected-banner">
              <Text style={styles.injectedText}>
                INJECTED speedMps = {status.simulationInjectedSpeedMps}
              </Text>
            </View>
          ) : null}
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
    overflow: "hidden",
  },
  row: {
    flexDirection: "row",
    alignItems: "center",
    padding: spacing.lg,
    gap: spacing.md,
  },
  rowLabel: {
    color: colors.onSurface,
    fontSize: 14,
    fontWeight: "600",
  },
  rowHelp: {
    color: colors.onSurfaceTertiary,
    fontSize: 12,
    marginTop: 2,
  },
  scenarioRow: {
    flexDirection: "row",
    alignItems: "center",
    padding: spacing.md,
    paddingHorizontal: spacing.lg,
    borderBottomColor: colors.divider,
    borderBottomWidth: 1,
  },
  scenarioLabel: {
    color: colors.onSurface,
    fontFamily: MONO_FAMILY,
    fontSize: 13,
    letterSpacing: 1.5,
    fontWeight: "700",
  },
  regressionBtn: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: colors.error,
    paddingVertical: spacing.lg,
    borderRadius: radius.md,
    gap: spacing.sm,
  },
  regressionText: {
    color: colors.onError,
    fontFamily: MONO_FAMILY,
    fontWeight: "800",
    letterSpacing: 1.5,
    fontSize: 14,
  },
  regressionHelp: {
    color: colors.onSurfaceTertiary,
    fontSize: 12,
    marginTop: spacing.sm,
    lineHeight: 18,
  },
  clearBtn: {
    borderWidth: 1,
    borderColor: colors.borderStrong,
    borderRadius: radius.md,
    paddingVertical: spacing.md,
    alignItems: "center",
  },
  clearText: {
    color: colors.onSurface,
    fontFamily: MONO_FAMILY,
    fontWeight: "700",
    letterSpacing: 1.5,
    fontSize: 12,
  },
  injectedBanner: {
    marginTop: spacing.md,
    padding: spacing.md,
    backgroundColor: "#2A060C",
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: "#5A0F1B",
  },
  injectedText: {
    color: colors.error,
    fontFamily: MONO_FAMILY,
    fontWeight: "700",
    fontSize: 12,
    letterSpacing: 1,
  },
});
