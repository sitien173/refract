import { expect, test } from "@playwright/test";
import { jobState, submitJob } from "./helpers";

test("cancel reports the request and later the final state", async ({ page, request }) => {
  const jobId = await submitJob(request, "E2E_MODE=block\nE2E blocking job");
  try {
    await expect.poll(() => jobState(request, jobId), { timeout: 20_000 }).toBe("running");
    await page.goto(`/dashboard/jobs/${encodeURIComponent(jobId)}`);
    await expect(page.getByRole("heading", { name: `Job ${jobId}` })).toBeVisible();
    await page.getByRole("button", { name: "Cancel job" }).click();
    await page.getByRole("button", { name: "Confirm cancellation" }).click();
    await expect(page.getByRole("status", { name: "Announcements" })).toHaveText("Cancellation requested");
    await expect.poll(() => jobState(request, jobId), { timeout: 20_000 }).toBe("cancelled");
    await expect(page.getByRole("region", { name: "Job detail" }).getByText("cancelled", { exact: true })).toBeVisible({ timeout: 20_000 });
  } finally {
    await request.post(`/dashboard/api/jobs/${encodeURIComponent(jobId)}/cancel`, { headers: { "X-Refract-Dashboard": "1" }, data: {} }).catch(() => undefined);
  }
});

test("retry opens the new job", async ({ page, request }) => {
  await page.goto("/dashboard/jobs/e2e-seed-020");
  await expect(page.getByRole("heading", { name: "Job e2e-seed-020" })).toBeVisible();
  await page.getByRole("button", { name: "Retry job" }).click();
  await expect(page.getByRole("status", { name: "Announcements" })).toHaveText("Retry started");
  await expect(page).toHaveURL(/\/dashboard\/jobs\/(?!e2e-seed-020$)[^/?]+/);
  const retriedId = decodeURIComponent(new URL(page.url()).pathname.split("/").pop() ?? "");
  expect(retriedId).not.toBe("e2e-seed-020");
  await expect(page.getByRole("heading", { name: `Job ${retriedId}` })).toBeVisible();
  await expect.poll(() => jobState(request, retriedId), { timeout: 20_000 }).toBe("succeeded");
});

test("answer delivers through the pending question", async ({ page, request }) => {
  const question = "Which actions e2e branch should run?";
  const jobId = await submitJob(request, `E2E_MODE=ask\nE2E_ASK: ${question}`);
  await page.goto(`/dashboard/jobs/${encodeURIComponent(jobId)}`);
  await page.getByRole("button", { name: "Answer question" }).click();
  await expect(page.getByText(question)).toBeVisible();
  await page.getByLabel("Your answer").fill("branch a");
  await page.getByRole("button", { name: "Send answer" }).click();
  await expect(page.getByRole("status", { name: "Announcements" })).toHaveText("Answer sent");
  await expect.poll(() => jobState(request, jobId), { timeout: 20_000 }).toBe("succeeded");
});
