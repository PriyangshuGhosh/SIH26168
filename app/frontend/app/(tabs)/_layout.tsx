import { Tabs } from "expo-router";
import { Platform, Text } from "react-native";

import { EngineProvider } from "@/src/engine/EngineController";
import { colors } from "@/src/theme";

function TabIcon({ icon, color }: { icon: string; color: string }) {
  return <Text style={{ fontSize: 20, color }}>{icon}</Text>;
}

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
            tabBarIcon: ({ color }) => <TabIcon icon="🧭" color={color} />,
          }}
        />
        <Tabs.Screen
          name="diagnostics"
          options={{
            title: "DIAG",
            tabBarIcon: ({ color }) => <TabIcon icon="📊" color={color} />,
          }}
        />
        <Tabs.Screen
          name="simulation"
          options={{
            title: "SIM",
            tabBarIcon: ({ color }) => <TabIcon icon="🧪" color={color} />,
          }}
        />
        <Tabs.Screen
          name="docs"
          options={{
            title: "DOCS",
            tabBarIcon: ({ color }) => <TabIcon icon="📋" color={color} />,
          }}
        />
      </Tabs>
    </EngineProvider>
  );
}
