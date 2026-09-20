import type { CapacitorConfig } from "@capacitor/cli";

const config: CapacitorConfig = {
  appId: "com.sih26168.navigation",
  appName: "SIH26168 Navigation",
  webDir: "dist",
  bundledWebRuntime: false,
  android: {
    backgroundColor: "#070b0e",
    allowMixedContent: false,
  },
};

export default config;
