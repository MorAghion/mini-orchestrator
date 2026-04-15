import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

/** Separate from vite.config.ts so test-only config (jsdom, setup files)
 * doesn't leak into the dev server. */
export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test/setup.ts"],
    include: ["src/**/*.test.{ts,tsx}"],
    css: false, // no need to parse our metallic stylesheet for unit tests
  },
});
