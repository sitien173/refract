import "@testing-library/jest-dom/vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { createElement } from "react";
import { afterEach, beforeAll } from "vitest";

afterEach(cleanup);

// The first render and the first role query in a fresh worker cost around a second
// of one-time work. Do it in a hook so no individual test absorbs it.
beforeAll(() => {
  render(createElement("button", null, "warm up"));
  screen.getByRole("button", { name: "warm up" });
  cleanup();
});

if (!Element.prototype.scrollIntoView) Element.prototype.scrollIntoView = () => {};
if (!Element.prototype.hasPointerCapture) Element.prototype.hasPointerCapture = () => false;
if (!Element.prototype.setPointerCapture) Element.prototype.setPointerCapture = () => {};
if (!Element.prototype.releasePointerCapture) Element.prototype.releasePointerCapture = () => {};
