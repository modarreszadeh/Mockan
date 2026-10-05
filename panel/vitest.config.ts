import { defineConfig, mergeConfig } from "vitest/config"

import { createViteConfig } from "./vite.config.ts"

export default defineConfig((env) =>
  mergeConfig(createViteConfig(env), {
    test: {
      environment: "jsdom",
      globals: false,
      setupFiles: ["./src/test/setup.ts"],
      include: ["src/**/*.test.{ts,tsx}"],
      css: false,
      restoreMocks: true,
      testTimeout: 15_000,
    },
  }),
)
