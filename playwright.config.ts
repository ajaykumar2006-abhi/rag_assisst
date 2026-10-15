import { defineConfig, devices } from "@playwright/test";

/**
 * Browser end-to-end configuration.
 *
 * The suite drives the *real* application: a running FastAPI backend on :8000 and
 * the Vite dev server on :5173, which proxies /api to the backend. Nothing is
 * mocked, so a passing run means the upload → index → ask → cite → delete flow
 * actually works through the browser.
 *
 * Start the stack first (or let `webServer` do it):
 *   backend:  uvicorn app.main:app --port 8000
 *   frontend: npm run dev
 */
export default defineConfig({
  testDir: "./tests/e2e",
  timeout: 120_000,
  expect: { timeout: 20_000 },
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: [["list"], ["html", { open: "never" }]],
  use: {
    baseURL: process.env.PLAYWRIGHT_BASE_URL ?? "http://127.0.0.1:5173",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    video: "off",
    actionTimeout: 20_000,
    navigationTimeout: 30_000,
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: [
    {
      command: "npm run dev -- --host 127.0.0.1 --port 5173 --strictPort",
      url: "http://127.0.0.1:5173",
      reuseExistingServer: true,
      timeout: 120_000,
      stdout: "pipe",
    },
  ],
});
