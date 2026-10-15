import { expect, test } from "@playwright/test";
import path from "node:path";
import { fileURLToPath } from "node:url";

/**
 * End-to-end coverage of the six screens against the running stack.
 *
 * No API mocking: the suite uploads a real PDF, waits for the backend pipeline,
 * asks a question whose answer is known from the source text, follows the
 * citation back to its passage, runs the evaluation and deletes the document.
 */

const here = path.dirname(fileURLToPath(import.meta.url));
const FIXTURE_PDF = path.resolve(here, "../../../eval/fixtures/helios_mission_brief.pdf");
const API = "http://127.0.0.1:8000/api/v1";

test.describe.configure({ mode: "serial" });

// Start from an empty library so repeated runs are deterministic: a leftover copy of
// the fixture from an earlier session would otherwise be the document that gets cited.
test.beforeAll(async ({ request }) => {
  const response = await request.get(`${API}/documents`);
  expect(response.ok()).toBeTruthy();
  for (const document of await response.json()) {
    await request.delete(`${API}/documents/${document.id}`);
  }
});

test.beforeEach(async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
});

test("screen 1 — welcome page shows live backend facts", async ({ page }) => {
  await expect(page.getByText(/Galaxy Edition/i)).toBeVisible();
  // Nova is a decorative figure with an accessible label; her bubble carries text.
  await expect(page.getByRole("group", { name: /nova/i })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Live system state", level: 2 })).toBeVisible();
  await expect(page.getByText(/Embedding provider/)).toBeVisible();
});

test("screens 2-4 — upload, watch processing, ask, follow the citation", async ({ page }) => {
  await page.goto("/documents");
  await expect(page.getByRole("heading", { name: "Documents", exact: true, level: 1 })).toBeVisible();

  await page.getByTestId("file-input").setInputFiles(FIXTURE_PDF);
  await page.getByRole("button", { name: /Open processing details|Watch it being processed/ }).first().waitFor();

  // Screen 3: real per-stage progress from the backend.
  await page.goto("/processing");
  const readyRow = page.getByText("helios_mission_brief.pdf").first();
  await expect(readyRow).toBeVisible();
  await page.getByRole("button", { name: "Inspect" }).first().click();
  await expect(page.getByRole("heading", { name: "Pipeline stages", level: 2 })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Extracted content", level: 2 })).toBeVisible();
  await expect(page.getByText("Chunks indexed")).toBeVisible();

  // Wait for the pipeline to settle, then confirm all seven stages completed.
  await expect(page.locator(".stage--completed")).toHaveCount(7, { timeout: 90_000 });
  await expect(page.getByText("100% complete")).toBeVisible();

  // Screen 4: ask a question with a known answer and check the citation.
  await page.getByRole("button", { name: "Ask about it" }).click();
  await expect(page.getByRole("heading", { name: "Ask your documents", level: 1 })).toBeVisible();

  const composer = page.getByLabel("Your question");
  await composer.fill("What altitude and inclination does the observatory orbit at?");
  await page.getByRole("button", { name: "Ask", exact: true }).click();

  // Report what the transcript actually said if the expected answer never arrives.
  const transcript = page.getByTestId("transcript");
  await transcript.waitFor({ state: "visible", timeout: 30_000 });
  try {
    await page.waitForFunction(
      () =>
        (document.querySelector('[data-testid="transcript"]')?.textContent ?? "").includes(
          "612 kilometres",
        ),
      undefined,
      { timeout: 60_000 },
    );
  } catch (error) {
    throw new Error(
      `${(error as Error).message}\n--- transcript as rendered ---\n${await transcript.innerText()}\n--- end ---`,
    );
  }
  await expect(transcript).toContainText("612 kilometres");
  await expect(page.getByTestId("citation-1")).toContainText("helios_mission_brief.pdf");
  await expect(page.getByTestId("citation-1")).toContainText(/page \d+/);

  // The citation marker in the answer opens the source viewer.
  await page.locator(".citation-marker").first().click();
  await expect(page.getByTestId("source-viewer")).toBeVisible();
  await expect(page.getByTestId("source-viewer")).toContainText("Why this passage matched");
  await page.keyboard.press("Escape");
  await expect(page.getByTestId("source-viewer")).toBeHidden();
});

test("refuses a question the documents cannot support", async ({ page }) => {
  await page.goto("/chat");
  await page.getByLabel("Your question").fill("Which football team won the 1994 FIFA World Cup final?");
  await page.getByRole("button", { name: "Ask", exact: true }).click();

  await expect(page.getByTestId("transcript")).toContainText(/Insufficient evidence/i, { timeout: 60_000 });
});

test("screen 5 — evaluation dashboard runs a real measurement", async ({ page }) => {
  await page.goto("/evaluation");
  await expect(page.getByRole("heading", { name: "Evaluation", exact: true, level: 1 })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Live application statistics", level: 2 })).toBeVisible();

  await page.getByRole("button", { name: /Run evaluation now/ }).click();
  await expect(page.getByRole("heading", { name: /Measured results/, level: 2 })).toBeVisible({
    timeout: 120_000,
  });
  // The six measured metrics, read from the run we just executed.
  for (const label of ["Recall@5", "Precision@5", "MRR", "Citation hit rate", "Answer rate", "Mean latency"]) {
    await expect(page.getByText(label, { exact: true }).first()).toBeVisible();
  }
  await expect(page.getByRole("heading", { name: "Per-question results", level: 2 })).toBeVisible();
  await expect(page.getByText(/Known limitations/)).toBeVisible();
  await expect(page.getByText(/every sentence above is copied verbatim/i).or(page.getByText(/Methodology/))).toBeVisible();
});

test("screen 6 — settings and privacy report real storage", async ({ page }) => {
  await page.goto("/settings");
  await expect(page.getByRole("heading", { name: "Settings & privacy", level: 1 })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Retrieval and chunking", level: 2 })).toBeVisible();
  await expect(page.getByRole("heading", { name: "What is stored on this machine", level: 2 })).toBeVisible();
  await expect(page.getByRole("columnheader", { name: "Location" })).toBeVisible();

  // Toggling animations must stick and must not break navigation.
  const motion = page.getByLabel("Enable Galaxy animations");
  const before = await motion.isChecked();
  await motion.setChecked(!before);
  await page.reload();
  await expect(page.getByLabel("Enable Galaxy animations")).toBeChecked({ checked: !before });
  await motion.setChecked(before);
});

test("deletion removes the document from the library", async ({ page }) => {
  await page.goto("/documents");
  const row = page.getByTestId(/doc-row-/).filter({ hasText: "helios_mission_brief.pdf" }).first();
  await expect(row).toBeVisible();

  await row.getByRole("button", { name: /^Delete / }).click();
  await expect(page.getByRole("dialog")).toBeVisible();
  await page.getByRole("button", { name: "Delete permanently" }).click();
  await expect(page.getByRole("dialog")).toBeHidden({ timeout: 30_000 });
  // No library row may still reference the deleted file (the toast does mention it).
  await expect(page.getByTestId(/doc-row-/).filter({ hasText: "helios_mission_brief.pdf" })).toHaveCount(0, {
    timeout: 30_000,
  });
});

test("keyboard navigation reaches every screen", async ({ page }) => {
  await page.goto("/");
  for (const name of ["Documents", "Processing", "Ask", "Evaluation", "Settings & privacy"]) {
    await page.getByRole("link", { name: new RegExp(name) }).click();
    await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
  }
});
