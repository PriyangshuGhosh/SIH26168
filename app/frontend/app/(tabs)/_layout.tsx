import { Tabs } from "expo-router";
import { Platform } from "react-native";
import Icon from "@react-native-vector-icons/material-design-icons";

import { EngineProvider } from "@/src/engine/EngineController";
import { colors } from "@/src/theme";

export default function TabsLayout() {
  return (
    <EngineProvider>
      <Tabs
        screenOptions={{
          headerShown: false,
          tabBarActiveTintColor: colors.brandPrimary,
          tabBarInactiveTintColor: colors.onSurfaceTertiary,
          tabBarStyle: {
            backgroundColor: colors.surfaceSecondary,
            borderTopColor: colors.divider,
            ...(Platform.OS === "web" ? { height: 64 } : {}),
          },
          tabBarItemStyle: { alignSelf: "center" },
          tabBarLabelStyle: { fontSize: 11, letterSpacing: 1 },
        }}
      >
        <Tabs.Screen
          name="index"
          options={{
            title: "NAV",
            tabBarIcon: ({ color, size }) => (
              <Icon name="navigation-variant" size={size} color={color} />
            ),
          }}
        />
        <Tabs.Screen
          name="diagnostics"
          options={{
            title: "DIAG",
            tabBarIcon: ({ color, size }) => (
              <Icon name="pulse" size={size} color={color} />
            ),
          }}
        />
        <Tabs.Screen
          name="simulation"
          options={{
            title: "SIM",
            tabBarIcon: ({ color, size }) => (
              <Icon name="test-tube" size={size} color={color} />
            ),
          }}
        />
        <Tabs.Screen
          name="docs"
          options={{
            title: "DOCS",
            tabBarIcon: ({ color, size }) => (
              <Icon name="checkbox-marked-circle-outline" size={size} color={color} />
            ),
          }}
        />
      </Tabs>
    </EngineProvider>
  );
}
