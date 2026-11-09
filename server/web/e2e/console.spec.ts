import { expect, test } from "@playwright/test";
import { submitJob } from "./helpers";

const jobButton = (page: import("@playwright/test").Page, id: string) => page.getByRole("button", { name: new RegExp(`^${id} `) });

test("deep links open a job and the targets view", async ({ page }) => {
  await page.goto("/dashboard/jobs/e2e-seed-042");
  await expect(page.getByRole("heading", { name: "Job e2e-seed-042" })).toBeVisible();
  await expect(page.getByText("Seeded output 42")).toBeVisible();

  await page.goto("/dashboard/targets");
  await expect(page.getByRole("heading", { name: "Targets", level: 2 })).toBeVisible();
  await expect(page.getByRole("heading", { name: "e2e-next", level: 3 })).toBeVisible();
});

test("filters narrow the list and load more reveals the oldest seeded job", async ({ page }) => {
  await page.goto("/dashboard/");
  await expect(jobButton(page, "e2e-seed-100")).toBeVisible();
  await expect(jobButton(page, "e2e-seed-000")).toHaveCount(0);

  await page.getByRole("button", { name: "Load more jobs" }).click();
  await expect(jobButton(page, "e2e-seed-000")).toBeVisible();
  await expect(page.getByRole("button", { name: "Load more jobs" })).toHaveCount(0);

  await page.getByLabel("Search jobs").fill("e2e-seed-05");
  await page.getByLabel("Search jobs").press("Enter");
  await expect(page).toHaveURL(/[?&]q=e2e-seed-05/);
  await expect(jobButton(page, "e2e-seed-050")).toBeVisible();
  await expect(jobButton(page, "e2e-seed-100")).toHaveCount(0);

  await page.getByLabel("Search jobs").fill("");
  await page.getByLabel("Search jobs").press("Enter");
  await expect(page).not.toHaveURL(/[?&]q=/);
  await page.getByRole("combobox", { name: "Filter by state" }).click();
  await page.getByRole("option", { name: "succeeded" }).click();
  await expect(page).toHaveURL(/[?&]state=succeeded/);
  await expect(jobButton(page, "e2e-seed-100")).toBeVisible();
});

test("tabs follow the tab query parameter through back and forward", async ({ page }) => {
  await page.goto("/dashboard/jobs/e2e-seed-010");
  const transcript = page.getByRole("tab", { name: "Transcript" });
  await expect(transcript).toHaveAttribute("aria-selected", "true");

  await page.getByRole("tab", { name: "Result" }).click();
  await expect(page).toHaveURL(/[?&]tab=result/);
  await expect(page.getByRole("tabpanel", { name: "Result" })).toHaveText("Seeded result 10");

  await page.getByRole("tab", { name: "Metadata" }).click();
  await expect(page).toHaveURL(/[?&]tab=metadata/);
  await expect(page.getByRole("tabpanel", { name: "Metadata" })).toContainText("e2e-project");

  await jobButton(page, "e2e-seed-011").click();
  await expect(page.getByRole("heading", { name: "Job e2e-seed-011" })).toBeVisible();
  await expect(page).toHaveURL(/jobs\/e2e-seed-011\?tab=metadata/);

  await page.goBack();
  await expect(page.getByRole("heading", { name: "Job e2e-seed-010" })).toBeVisible();
  await expect(page.getByRole("tab", { name: "Metadata" })).toHaveAttribute("aria-selected", "true");

  await page.goForward();
  await expect(page.getByRole("heading", { name: "Job e2e-seed-011" })).toBeVisible();
  await expect(page.getByRole("tab", { name: "Metadata" })).toHaveAttribute("aria-selected", "true");

  await page.goto("/dashboard/jobs/e2e-seed-010?tab=prompt");
  await expect(page.getByRole("tabpanel", { name: "Prompt" })).toHaveText("Seeded dashboard job 10");
});

test("the transcript loads to the end after a live job finishes", async ({ page, request }) => {
  const jobId = await submitJob(request, "E2E live transcript");
  await page.goto(`/dashboard/jobs/${encodeURIComponent(jobId)}`);
  await expect(page.getByRole("heading", { name: `Job ${jobId}` })).toBeVisible();
  await expect(page.getByRole("region", { name: "Job detail" }).getByText("succeeded", { exact: true })).toBeVisible({ timeout: 20_000 });
  await expect(page.getByRole("region", { name: "Output transcript" })).toContainText("E2E backend completed", { timeout: 20_000 });
});

test("the job list and tabs work from the keyboard", async ({ page }) => {
  await page.goto("/dashboard/");
  const first = jobButton(page, "e2e-seed-100");
  await expect(first).toBeVisible();
  await first.focus();
  await page.keyboard.press("Enter");
  await expect(page).toHaveURL(/jobs\/e2e-seed-100$/);
  await expect(first).toHaveAttribute("aria-current", "page");

  await page.keyboard.press("Tab");
  await expect(jobButton(page, "e2e-seed-099")).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(page).toHaveURL(/jobs\/e2e-seed-099$/);

  const transcript = page.getByRole("tab", { name: "Transcript" });
  const prompt = page.getByRole("tab", { name: "Prompt" });
  await transcript.focus();
  await page.keyboard.press("ArrowRight");
  await expect(prompt).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(prompt).toHaveAttribute("aria-selected", "true");
  await expect(page).toHaveURL(/[?&]tab=prompt/);
  await expect(page.getByRole("tabpanel", { name: "Prompt" })).toHaveText("Seeded dashboard job 99");
});

test("the split pane resizes with the keyboard", async ({ page }) => {
  await page.goto("/dashboard/");
  const handle = page.getByRole("separator", { name: "Resize job list and detail" });
  await expect(handle).toBeVisible();
  const before = Number(await handle.getAttribute("aria-valuenow"));
  await handle.focus();
  await page.keyboard.press("ArrowRight");
  await expect.poll(async () => Number(await handle.getAttribute("aria-valuenow"))).toBeGreaterThan(before);
  const widened = Number(await handle.getAttribute("aria-valuenow"));
  await page.keyboard.press("ArrowLeft");
  await page.keyboard.press("ArrowLeft");
  await expect.poll(async () => Number(await handle.getAttribute("aria-valuenow"))).toBeLessThan(widened);
});
