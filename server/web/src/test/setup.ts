import "@testing-library/jest-dom/vitest";
import { notifyManager } from "@tanstack/react-query";
import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";

notifyManager.setScheduler((cb) => cb());

afterEach(cleanup);

if (!Element.prototype.scrollIntoView) Element.prototype.scrollIntoView = () => {};
if (!Element.prototype.hasPointerCapture) Element.prototype.hasPointerCapture = () => false;
if (!Element.prototype.setPointerCapture) Element.prototype.setPointerCapture = () => {};
if (!Element.prototype.releasePointerCapture) Element.prototype.releasePointerCapture = () => {};
