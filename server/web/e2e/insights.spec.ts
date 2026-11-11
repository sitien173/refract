import { expect, test } from "@playwright/test";

test("insights shows seeded job metrics and switches the window", async ({ page }) => {
  await page.goto("/dashboard/insights");
  await expect(page.getByRole("heading", { name: "Insights" })).toBeVisible();

  // Other e2e tests finish jobs on the same daemon, so count only the seeded profile's row.
  await expect(page.getByText("Jobs finished", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "7 days" })).toHaveAttribute("aria-pressed", "true");
  await expect(page.getByRole("group", { name: /^Daily jobs finished/ })).toBeVisible();
  const breakdownTable = page.getByRole("table", { name: "Jobs by profile, workflow, target, and state" });
  await expect(breakdownTable).toBeVisible();
  const seededJobs = breakdownTable
    .getByRole("row")
    .filter({ has: page.getByRole("cell", { name: "seed", exact: true }) })
    .getByRole("cell")
    .last();
  await expect(seededJobs).toHaveText("101");
  for (const heading of ["Profile", "Workflow", "Target", "State", "Jobs"]) {
    await expect(breakdownTable.getByRole("columnheader", { name: heading })).toBeVisible();
  }
  await expect(page.getByRole("table", { name: "Tokens by model" }).getByRole("row", { name: /^e2e / })).toBeVisible();
  await expect(page.getByText("Unpriced models: e2e.")).toBeVisible();

  await page.getByRole("button", { name: "30 days" }).click();
  await expect(page.getByRole("button", { name: "30 days" })).toHaveAttribute("aria-pressed", "true");
  await expect(seededJobs).toHaveText("102");

  await page.getByRole("button", { name: "1 day" }).click();
  await expect(seededJobs).toHaveText("101");
});
