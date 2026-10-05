import js from "@eslint/js"
import reactHooks from "eslint-plugin-react-hooks"
import reactRefresh from "eslint-plugin-react-refresh"
import globals from "globals"
import tseslint from "typescript-eslint"

/** Import boundaries (docs/frontend/project-structure.md): ui ← mockan ← features; features never import each other. */
const FEATURES = ["onboarding", "overview", "rules", "services", "settings", "admin", "design"]

/** Overlay panels are `Modal` or `ConfirmDialog` (docs/frontend/plan-responsive-overlays.md); the raw shadcn ones stay in `ui`. */
const OVERLAY_PATTERN = {
  group: ["@/components/ui/sheet", "@/components/ui/dialog", "@/components/ui/alert-dialog"],
  message: "Use Modal or ConfirmDialog from @/components/mockan (docs/frontend/plan-responsive-overlays.md).",
}

export default tseslint.config(
  { ignores: ["dist", "coverage", "playwright-report", "test-results", "public/mockServiceWorker.js", ".shot.mjs"] },
  {
    extends: [js.configs.recommended, ...tseslint.configs.recommended],
    files: ["**/*.{ts,tsx}"],
    languageOptions: { ecmaVersion: 2023, globals: globals.browser },
    plugins: { "react-hooks": reactHooks, "react-refresh": reactRefresh },
    rules: {
      ...reactHooks.configs.recommended.rules,
      "react-refresh/only-export-components": "off",
      "@typescript-eslint/no-unused-vars": ["error", { argsIgnorePattern: "^_", varsIgnorePattern: "^_" }],
      "no-restricted-syntax": [
        "error",
        {
          selector: "Literal[value=/#[0-9a-fA-F]{6}\\b/]",
          message: "No raw hex colours — use a token from globals.css.",
        },
      ],
    },
  },
  {
    files: ["src/components/ui/**"],
    rules: {
      "no-restricted-imports": [
        "error",
        {
          patterns: [
            { group: ["@/components/mockan/*", "@/features/*", "@/app/*"], message: "ui is the bottom layer." },
          ],
        },
      ],
    },
  },
  {
    files: ["src/components/mockan/**"],
    rules: {
      "no-restricted-imports": [
        "error",
        {
          patterns: [
            { group: ["@/features/*", "@/app/*"], message: "mockan components can't depend on features or app." },
            OVERLAY_PATTERN,
          ],
        },
      ],
    },
  },
  ...FEATURES.map((feature) => ({
    files: [`src/features/${feature}/**`],
    rules: {
      "no-restricted-imports": [
        "error",
        {
          patterns: [
            {
              group: FEATURES.filter((f) => f !== feature)
                .map((f) => `@/features/${f}/*`)
                .concat(["@/app/*"]),
              message:
                "Features never import each other or the app layer; move shared code to components/mockan or lib.",
            },
            OVERLAY_PATTERN,
          ],
        },
      ],
    },
  })),
  {
    // Features outside the import-boundary list above still get the overlay guard.
    files: ["src/features/logs/**", "src/features/test-route/**"],
    rules: { "no-restricted-imports": ["error", { patterns: [OVERLAY_PATTERN] }] },
  },
  {
    files: ["src/components/mockan/confirm-dialog.tsx"],
    rules: { "no-restricted-imports": "off" },
  },
  {
    files: ["src/mocks/**", "src/test/**", "**/*.test.{ts,tsx}", "e2e/**"],
    rules: { "no-restricted-syntax": "off", "no-restricted-imports": "off" },
  },
)
