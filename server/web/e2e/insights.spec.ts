import { expect, test } from "@playwright/test";

test("insights shows seeded job metrics and switches the window", async ({ page }) => {
  await page.goto("/dashboard/insights");
  await expect(page.getByRole("heading", { name: "Insights" })).toBeVisible();

  const jobsFinished = page.getByText("Jobs finished", { exact: true }).locator("xpath=following-sibling::dd");
  await expect(jobsFinished).toHaveText("101");
  await expect(page.getByRole("button", { name: "7 days" })).toHaveAttribute("aria-pressed", "true");
  await expect(page.getByRole("table", { name: "Tokens by model" }).getByRole("row", { name: /^e2e / })).toBeVisible();
  await expect(page.getByText("Unpriced models: e2e.")).toBeVisible();

  await page.getByRole("button", { name: "30 days" }).click();
  await expect(page.getByRole("button", { name: "30 days" })).toHaveAttribute("aria-pressed", "true");
  await expect(jobsFinished).toHaveText("102");

  await page.getByRole("button", { name: "1 day" }).click();
  await expect(jobsFinished).toHaveText("101");
});
