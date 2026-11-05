import { act, fireEvent, render, screen } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import { ResizableHandle, ResizablePanel, ResizablePanelGroup } from "./resizable";

function renderGroup(handleProps: Partial<React.ComponentProps<typeof ResizableHandle>> = {}, maxSize = 90) {
  return render(
    <ResizablePanelGroup direction="horizontal">
      <ResizablePanel defaultSize={50} minSize={20} maxSize={maxSize}>Left</ResizablePanel>
      <ResizableHandle aria-label="Resize panels" {...handleProps} />
      <ResizablePanel defaultSize={50} minSize={20}>Right</ResizablePanel>
    </ResizablePanelGroup>,
  );
}

const press = (handle: HTMLElement, key: string) => act(() => { fireEvent.keyDown(handle, { key }); });

it("renders a focusable separator named by aria-label with TDS token sizing", () => {
  renderGroup();
  const handle = screen.getByRole("separator", { name: "Resize panels" });
  expect(handle).toHaveAttribute("tabindex", "0");
  expect(handle).toHaveStyle({ width: "var(--spacing-8)", background: "var(--border-subtle)" });
});

it("falls back to a default accessible name", () => {
  renderGroup({ "aria-label": undefined });
  expect(screen.getByRole("separator", { name: "Resize panels" })).toBeInTheDocument();
});

it("lets the library resize with the keyboard and respect panel constraints", () => {
  renderGroup({}, 60);
  const handle = screen.getByRole("separator");
  expect(handle).toHaveAttribute("aria-valuenow", "50");
  press(handle, "ArrowRight");
  expect(handle).toHaveAttribute("aria-valuenow", "60");
  press(handle, "ArrowRight");
  expect(handle).toHaveAttribute("aria-valuenow", "60");
  press(handle, "ArrowLeft");
  expect(handle).toHaveAttribute("aria-valuenow", "50");
});

it("does not resize a disabled handle", () => {
  renderGroup({ disabled: true });
  const handle = screen.getByRole("separator");
  press(handle, "ArrowRight");
  expect(handle).toHaveAttribute("aria-valuenow", "50");
});

it("forwards props and event handlers to the handle", () => {
  const onKeyDown = vi.fn();
  renderGroup({ onKeyDown, "data-testid": "grip" } as never);
  const handle = screen.getByTestId("grip");
  press(handle, "ArrowRight");
  expect(onKeyDown).toHaveBeenCalled();
});
