import { expect, test } from "@playwright/test";
import { jobState, submitJob } from "./helpers";

test("daemon serves seeded jobs, deep links, and pending questions", async ({ page, request }) => {
  await page.goto("/dashboard/");
  await expect(page.getByText("e2e-seed-100")).toBeVisible();

  await page.goto("/dashboard/jobs/e2e-seed-100");
  await expect(page.getByRole("heading", { name: "Job e2e-seed-100" })).toBeVisible();

  const question = "Should we proceed with the e2e check?";
  const jobId = await submitJob(request, `E2E_MODE=ask\nE2E_ASK: ${question}`);

  await page.goto(`/dashboard/jobs/${encodeURIComponent(jobId)}`);
  await expect(page.getByRole("heading", { name: `Job ${jobId}` })).toBeVisible();
  await page.getByRole("button", { name: "Answer question" }).click();
  await expect(page.getByText(question)).toBeVisible();
  await page.getByLabel("Your answer").fill("e2e answer");
  await page.getByRole("button", { name: "Send answer" }).click();
  await expect.poll(() => jobState(request, jobId), { timeout: 20_000 }).toBe("succeeded");
});
