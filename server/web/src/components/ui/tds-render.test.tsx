import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeAll, beforeEach, expect, it, vi } from "vitest";
import { settle } from "../../test/async";
import { warmUpComponents } from "../../test/warmup";
import { Button } from "./button";
import { Dialog, DialogContent, DialogTitle } from "./dialog";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "./select";

beforeAll(warmUpComponents);
beforeEach(() => {
  vi.useFakeTimers();
});
afterEach(() => {
  cleanup();
  vi.useRealTimers();
});

it("applies TDS button class", () => {
  render(<Button>Save</Button>);
  expect(screen.getByRole("button", { name: "Save" })).toHaveClass("tds-btn--primary");
});
it("portals TDS dialog content to document.body", () => {
  render(
    <Dialog defaultOpen>
      <DialogContent>
        <DialogTitle>Portal dialog</DialogTitle>
      </DialogContent>
    </Dialog>,
  );
  const node = screen.getByRole("dialog");
  expect(node).toHaveClass("tds-dialog__panel");
  expect(document.body).toContainElement(node);
});
it("portals TDS select content to document.body", async () => {
  render(
    <Select open defaultValue="one">
      <SelectTrigger aria-label="Choice">
        <SelectValue />
      </SelectTrigger>
      <SelectContent>
        <SelectItem value="one">One</SelectItem>
      </SelectContent>
    </Select>,
  );
  await settle();
  const option = screen.getByRole("option", { name: "One" });
  expect(option.parentElement?.parentElement).toHaveClass("tds-dropdown-panel");
  expect(document.body).toContainElement(option);
});
