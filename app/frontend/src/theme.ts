// Dark-First Utility DARK theme — SIH NavDiag HUD
// Tokens come from /app/design_guidelines.json. Do not add color literals
// in components; use useTheme() / makeStyles() from this file.

import { useMemo } from "react";
import { Appearance, StyleSheet, useColorScheme } from "react-native";

export type ColorScheme = "light" | "dark";

const dark = {
  surface: "#090A0C",
  onSurface: "#F1F3F5",
  surfaceSecondary: "#15171C",
  onSurfaceSecondary: "#D7DBDF",
  surfaceTertiary: "#20232A",
  onSurfaceTertiary: "#9AA0A6",
  surfaceInverse: "#FFFFFF",
  onSurfaceInverse: "#090A0C",
  muted: "#6B7280",

  brand: "#00E5FF",
  onBrand: "#000000",
  brandPrimary: "#00E5FF",
  onBrandPrimary: "#000000",
  brandSecondary: "#1E88E5",
  onBrandSecondary: "#FFFFFF",
  brandTertiary: "#1B2A32",
  onBrandTertiary: "#81D4FA",

  success: "#00E676",
  onSuccess: "#000000",
  warning: "#FFAB00",
  onWarning: "#000000",
  error: "#FF1744",
  onError: "#FFFFFF",
  info: "#1E88E5",
  onInfo: "#FFFFFF",

  border: "#2D323B",
  borderStrong: "#454C59",
  divider: "#1F232B",
};

export type ThemeColors = typeof dark;

export const defaultScheme = "dark" satisfies ColorScheme;
export const themes: { light?: ThemeColors; dark: ThemeColors } = { dark };

export function setColorScheme(scheme: ColorScheme | null) {
  Appearance.setColorScheme?.(scheme ?? "unspecified");
}

// Force dark scheme for this technical HUD app.
setColorScheme?.(defaultScheme);

export function useTheme(): { scheme: ColorScheme; colors: ThemeColors } {
  const system = useColorScheme();
  const scheme: ColorScheme =
    system && themes[system as ColorScheme] ? (system as ColorScheme) : defaultScheme;
  return { scheme, colors: themes[scheme] ?? themes.dark };
}

export const colors = themes.dark;

export const spacing = {
  xs: 4,
  sm: 8,
  md: 12,
  lg: 16,
  xl: 24,
  xxl: 32,
  xxxl: 48,
} as const;

export const radius = {
  sm: 4,
  md: 8,
  lg: 12,
  pill: 999,
} as const;

export const fontFamily = {
  display: "System",
  text: "System",
  mono: "Menlo", // monospace fallback; also uses Courier on Android via style
} as const;

export function makeStyles<T extends StyleSheet.NamedStyles<T> | StyleSheet.NamedStyles<any>>(
  factory: (colors: ThemeColors) => T & StyleSheet.NamedStyles<any>,
): () => T {
  return function useStyles(): T {
    const { colors } = useTheme();
    return useMemo(() => StyleSheet.create(factory(colors)), [colors]);
  };
}
