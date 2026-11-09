import { randomUUID } from "node:crypto";
import { expect, test } from "@playwright/test";
import { createCard } from "./helpers";

test("creates a card, moves it to in_progress, and views timeline in side panel", async ({ page, request }) => {
  const title = `Board spec ${randomUUID()}`;
  const card = await createCard(request, title, "Card body for e2e board test");

  await page.goto("/dashboard/board");

  const todoSection = page.getByRole("region", { name: /^TODO/ });
  await expect(todoSection.getByText(title)).toBeVisible({ timeout: 20_000 });

  await card.move("in_progress", "Started progress in e2e");

  const inProgressSection = page.getByRole("region", { name: /^IN PROGRESS/ });
  await expect(inProgressSection.getByText(title)).toBeVisible({ timeout: 20_000 });

  await inProgressSection.getByRole("link", { name: new RegExp(title) }).click();

  const panel = page.getByRole("complementary", { name: "Card detail" });
  await expect(panel).toBeVisible({ timeout: 10_000 });
  await expect(panel.getByText("Timeline")).toBeVisible();
  await expect(panel.getByText("Started progress in e2e")).toBeVisible();
});
