import { vi } from "vitest";

export const mockMotion = ({ reduced = false, transitions = true } = {}) => {
  vi.stubGlobal("matchMedia", (query: string) => ({ matches: reduced && query.includes("reduce"), media: query, addEventListener() {}, removeEventListener() {} }));
  const start = vi.fn((update: () => void) => {
    update();
    return { finished: Promise.resolve() };
  });
  if (transitions) Object.assign(document, { startViewTransition: start });
  else Reflect.deleteProperty(document, "startViewTransition");
  return start;
};
