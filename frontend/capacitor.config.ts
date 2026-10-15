import type { CapacitorConfig } from "@capacitor/cli";

const config: CapacitorConfig = {
  appId: "com.lambchat.app",
  appName: "LambChat",
  webDir: "dist",
  plugins: {
    // MainActivity owns window insets and IME resizing.
    SystemBars: { insetsHandling: "disable" },
  },
  android: {
    allowMixedContent: false,
  },
  ios: {
    contentInset: "automatic",
  },
};

export default config;
