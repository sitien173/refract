import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { expect, it } from "vitest";
import { AlertDialog, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogTitle, AlertDialogTrigger } from "./alert-dialog";
import { Button } from "./button";
import { Dialog, DialogContent, DialogTitle, DialogTrigger } from "./dialog";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "./select";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "./tabs";

const choose = (option: HTMLElement) => {
  fireEvent.pointerDown(option);
  fireEvent.mouseDown(option);
  fireEvent.pointerUp(option);
  fireEvent.mouseUp(option);
  fireEvent.click(option);
};

function DialogFixture() {
  return (
    <Dialog>
      <DialogTrigger render={<Button />}>Open dialog</DialogTrigger>
      <DialogContent>
        <DialogTitle>Job details</DialogTitle>
      </DialogContent>
    </Dialog>
  );
}

it("renders the dialog in a body portal with the Base UI popup role", async () => {
  const { container } = render(<DialogFixture />);
  fireEvent.click(screen.getByRole("button", { name: "Open dialog" }));
  const dialog = await screen.findByRole("dialog", { name: "Job details" });
  expect(dialog).toHaveAttribute("data-slot", "dialog-content");
  expect(dialog).toHaveAttribute("data-open");
  expect(container).not.toContainElement(dialog);
  expect(document.body).toContainElement(dialog);
});

it("closes the dialog on Escape and returns focus to the trigger", async () => {
  render(<DialogFixture />);
  const trigger = screen.getByRole("button", { name: "Open dialog" });
  trigger.focus();
  fireEvent.click(trigger);
  const dialog = await screen.findByRole("dialog");
  fireEvent.keyDown(dialog, { key: "Escape" });
  await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  await waitFor(() => expect(trigger).toHaveFocus());
});

it("renders the trigger through render without nesting buttons", () => {
  render(<DialogFixture />);
  const trigger = screen.getByRole("button", { name: "Open dialog" });
  expect(trigger.tagName).toBe("BUTTON");
  expect(trigger.querySelector("button")).toBeNull();
  expect(trigger).toHaveAttribute("data-slot", "button");
});

function AlertFixture() {
  return (
    <AlertDialog>
      <AlertDialogTrigger render={<Button variant="destructive" />}>Cancel job</AlertDialogTrigger>
      <AlertDialogContent>
        <AlertDialogTitle>Cancel this job?</AlertDialogTitle>
        <AlertDialogDescription>A running job may take time to stop.</AlertDialogDescription>
        <AlertDialogCancel render={<Button variant="secondary" />}>Keep job</AlertDialogCancel>
      </AlertDialogContent>
    </AlertDialog>
  );
}

it("exposes the alert dialog role with its title and description in a portal", async () => {
  const { container } = render(<AlertFixture />);
  fireEvent.click(screen.getByRole("button", { name: "Cancel job" }));
  const dialog = await screen.findByRole("alertdialog", { name: "Cancel this job?" });
  expect(dialog).toHaveAccessibleDescription("A running job may take time to stop.");
  expect(dialog).toHaveAttribute("data-slot", "alert-dialog-content");
  expect(container).not.toContainElement(dialog);
});

it("closes the alert dialog with Escape and its cancel button and returns focus", async () => {
  render(<AlertFixture />);
  const trigger = screen.getByRole("button", { name: "Cancel job" });
  trigger.focus();
  fireEvent.click(trigger);
  fireEvent.keyDown(await screen.findByRole("alertdialog"), { key: "Escape" });
  await waitFor(() => expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument());
  await waitFor(() => expect(trigger).toHaveFocus());
  fireEvent.click(trigger);
  fireEvent.click(await screen.findByRole("button", { name: "Keep job" }));
  await waitFor(() => expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument());
  await waitFor(() => expect(trigger).toHaveFocus());
});

function SelectFixture({ onValueChange }: { onValueChange?: (value: string | null) => void }) {
  return (
    <Select
      items={[
        { value: null, label: "All projects" },
        { value: "p1", label: "/workspace/one" },
      ]}
      onValueChange={onValueChange}
    >
      <SelectTrigger aria-label="Filter by project">
        <SelectValue />
      </SelectTrigger>
      <SelectContent>
        <SelectItem value={null}>All projects</SelectItem>
        <SelectItem value="p1">/workspace/one</SelectItem>
      </SelectContent>
    </Select>
  );
}

it("shows the label of the null item, portals the listbox, and reports the option value", async () => {
  const seen: (string | null)[] = [];
  const { container } = render(<SelectFixture onValueChange={(value) => seen.push(value)} />);
  const trigger = screen.getByRole("combobox", { name: "Filter by project" });
  expect(trigger).toHaveTextContent("All projects");
  fireEvent.click(trigger);
  const listbox = await screen.findByRole("listbox");
  expect(container).not.toContainElement(listbox);
  expect(document.body).toContainElement(listbox);
  expect(screen.getAllByRole("option").map((option) => option.textContent)).toEqual(["All projects", "/workspace/one"]);
  await act(() => new Promise((resolve) => setTimeout(resolve, 250)));
  choose(screen.getByRole("option", { name: "/workspace/one" }));
  await waitFor(() => expect(trigger).toHaveTextContent("/workspace/one"));
  expect(seen).toEqual(["p1"]);
});

it("closes the select on Escape and returns focus to the trigger", async () => {
  render(<SelectFixture />);
  const trigger = screen.getByRole("combobox");
  trigger.focus();
  fireEvent.click(trigger);
  const listbox = await screen.findByRole("listbox");
  fireEvent.keyDown(listbox, { key: "Escape" });
  await waitFor(() => expect(screen.queryByRole("listbox")).not.toBeInTheDocument());
  await waitFor(() => expect(trigger).toHaveFocus());
});

it("renders tabs with tablist, tab, and tabpanel roles and switches on click", () => {
  render(
    <Tabs defaultValue="a">
      <TabsList aria-label="Sections">
        <TabsTrigger value="a">Alpha</TabsTrigger>
        <TabsTrigger value="b">Beta</TabsTrigger>
      </TabsList>
      <TabsContent value="a">Alpha body</TabsContent>
      <TabsContent value="b">Beta body</TabsContent>
    </Tabs>,
  );
  expect(screen.getByRole("tablist", { name: "Sections" })).toHaveAttribute("data-slot", "tabs-list");
  expect(screen.getByRole("tab", { name: "Alpha" })).toHaveAttribute("aria-selected", "true");
  expect(screen.getByRole("tabpanel")).toHaveTextContent("Alpha body");
  fireEvent.click(screen.getByRole("tab", { name: "Beta" }));
  expect(screen.getByRole("tab", { name: "Beta" })).toHaveAttribute("aria-selected", "true");
  expect(screen.getByRole("tabpanel")).toHaveTextContent("Beta body");
});
