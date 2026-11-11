import { randomUUID } from "node:crypto";
import { expect, test } from "@playwright/test";
import { createCard } from "./helpers";

test("creates a card, moves it to in_progress, and views timeline in card dialog", async ({ page, request }) => {
  const title = `Board spec ${randomUUID()}`;
  const card = await createCard(request, title, "Card body for e2e board test");

  await page.goto("/dashboard/board");

  const todoSection = page.getByRole("region", { name: /^TODO/ }).filter({ has: page.getByText(title) });
  await expect(todoSection.getByText(title)).toBeVisible({ timeout: 20_000 });

  await card.move("in_progress", "Started progress in e2e");

  const inProgressSection = page.getByRole("region", { name: /^IN PROGRESS/ }).filter({ has: page.getByText(title) });
  await expect(inProgressSection.getByText(title)).toBeVisible({ timeout: 20_000 });

  const cardLink = inProgressSection.getByRole("link", { name: new RegExp(title) });
  await cardLink.click();

  const dialog = page.getByRole("dialog", { name: "Card detail" });
  await expect(dialog).toBeVisible({ timeout: 10_000 });
  await expect(dialog.getByText("Timeline")).toBeVisible();
  await expect(dialog.getByText("Started progress in e2e")).toBeVisible();

  await page.keyboard.press("Escape");
  await expect(dialog).toBeHidden({ timeout: 10_000 });
  await expect(page).not.toHaveURL(/[?&]card=/);
  await expect(cardLink).toBeFocused();
});
