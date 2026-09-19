// Shared UI primitives: status pill, mono readout, data row, section header.
// All colors from theme; testIDs on every interactive/informational element.

import React from "react";
import { Platform, StyleSheet, Text, View, ViewStyle } from "react-native";
import { colors, radius, spacing } from "../theme";

const MONO = Platform.select({ ios: "Menlo", android: "monospace", default: "Menlo" }) as string;

export type StatusTone = "ok" | "warn" | "bad" | "info" | "neutral";

const TONE: Record<StatusTone, { bg: string; fg: string; border: string }> = {
  ok: { bg: "#0B2A18", fg: colors.success, border: "#125733" },
  warn: { bg: "#2A1F02", fg: colors.warning, border: "#5A4200" },
  bad: { bg: "#2A060C", fg: colors.error, border: "#5A0F1B" },
  info: { bg: colors.brandTertiary, fg: colors.onBrandTertiary, border: colors.borderStrong },
  neutral: { bg: colors.surfaceTertiary, fg: colors.onSurfaceTertiary, border: colors.border },
};

export function StatusPill({
  tone,
  label,
  testID,
}: {
  tone: StatusTone;
  label: string;
  testID?: string;
}) {
  const c = TONE[tone];
  return (
    <View
      testID={testID}
      style={[pillStyles.pill, { backgroundColor: c.bg, borderColor: c.border }]}
    >
      <View style={[pillStyles.dot, { backgroundColor: c.fg }]} />
      <Text style={[pillStyles.text, { color: c.fg, fontFamily: MONO }]}>{label}</Text>
    </View>
  );
}

const pillStyles = StyleSheet.create({
  pill: {
    flexDirection: "row",
    alignItems: "center",
    borderWidth: 1,
    paddingHorizontal: spacing.md,
    paddingVertical: 6,
    borderRadius: radius.pill,
  },
  dot: { width: 8, height: 8, borderRadius: 999, marginRight: spacing.sm },
  text: { fontSize: 12, letterSpacing: 1.2, fontWeight: "700" },
});

export function MonoValue({
  value,
  size = 14,
  color,
  testID,
}: {
  value: string;
  size?: number;
  color?: string;
  testID?: string;
}) {
  return (
    <Text
      testID={testID}
      style={{
        fontFamily: MONO,
        fontVariant: ["tabular-nums"],
        color: color ?? colors.onSurface,
        fontSize: size,
      }}
    >
      {value}
    </Text>
  );
}

export function DataRow({
  label,
  value,
  tone,
  testID,
}: {
  label: string;
  value: string;
  tone?: StatusTone;
  testID?: string;
}) {
  const c = tone ? TONE[tone].fg : colors.onSurface;
  return (
    <View style={rowStyles.row} testID={testID}>
      <Text style={rowStyles.label}>{label}</Text>
      <MonoValue value={value} color={c} size={14} />
    </View>
  );
}

const rowStyles = StyleSheet.create({
  row: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    paddingVertical: 10,
    paddingHorizontal: spacing.lg,
    borderBottomColor: colors.divider,
    borderBottomWidth: StyleSheet.hairlineWidth,
  },
  label: {
    color: colors.onSurfaceTertiary,
    fontSize: 13,
    letterSpacing: 0.5,
  },
});

export function SectionHeader({
  title,
  right,
  style,
}: {
  title: string;
  right?: React.ReactNode;
  style?: ViewStyle;
}) {
  return (
    <View style={[sectionStyles.wrap, style]}>
      <Text style={sectionStyles.title}>{title}</Text>
      {right}
    </View>
  );
}

const sectionStyles = StyleSheet.create({
  wrap: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    paddingHorizontal: spacing.lg,
    paddingTop: spacing.xl,
    paddingBottom: spacing.sm,
  },
  title: {
    color: colors.onSurfaceTertiary,
    fontSize: 11,
    letterSpacing: 2,
    fontWeight: "700",
    textTransform: "uppercase",
  },
});

export const MONO_FAMILY = MONO;
