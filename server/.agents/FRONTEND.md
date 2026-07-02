<!-- ccg-shared-version: 5.3.1 -->
# FRONTEND.md — Frontend Engineering Rules

Domain rules for client-side work: UI, components, state, styling, UX, and design. Extends the global AGENTS.md — global rules always apply.

## 1. Components & Architecture

- Components do one job. Split when a component handles unrelated concerns; don't split for splitting's sake.
- Props down, events up. No reaching into children, no implicit global coupling.
- Reuse what exists. Before creating a button/modal/input, search the codebase for the existing one. A second slightly-different button is a bug.
- Colocate by feature, not by file type, unless the codebase says otherwise. Match the existing structure exactly.
- Derive, don't duplicate: computed values come from source state, never stored in parallel.

## 2. State Management

- Start with local state. Lift only when two components genuinely share it. Reach for a global store only when lifting becomes painful — and only the store the codebase already uses.
- Server data belongs in the data-fetching layer (React Query/SWR/equivalent), not copied into component state.
- Single source of truth per piece of data. If you can compute it, compute it.
- Handle all four fetch states: loading, error, empty, success. Skipping empty and error states is the most common LLM frontend bug.
- No state mutations the framework can't see. Follow the framework's reactivity rules strictly.

## 3. Styling & Design

- Use the design system first: existing tokens, spacing scale, color variables, and components. Hardcoded hex values and magic pixel numbers are forbidden when tokens exist.
- Match the established styling approach (Tailwind, CSS modules, styled-components, …). Never mix in a second one.
- Consistency beats novelty in product UI: same spacing rhythm, same type scale, same interaction patterns as the rest of the app.
- For new/standalone designs, make deliberate choices — palette, type pairing, layout — grounded in the product's subject. Avoid the generic AI defaults (cream + serif + terracotta; dark + neon accent). One signature element, restraint everywhere else.
- Respect specificity: avoid selector wars and `!important`. Style through the codebase's intended mechanism.

## 4. UX Fundamentals

- Every async action gives feedback: pending state on the trigger, success confirmation, actionable error message. Buttons disable while submitting.
- Errors tell the user what went wrong and what to do next — never raw API errors, never a bare "Something went wrong" when you know more.
- Empty states invite action; they are not blank screens.
- Preserve user input: no data loss on validation errors, navigation warnings on unsaved changes, optimistic updates roll back cleanly.
- Microcopy is design: plain verbs, sentence case, name actions by outcome ("Save changes", not "Submit"), consistent vocabulary across the flow.
- Don't break browser behavior: real links for navigation, working back button, no hijacked scroll.

## 5. Accessibility (non-negotiable)

- Semantic HTML first: `button` for actions, `a` for navigation, real headings in order, `label` for every input. ARIA only when semantics can't do it.
- Everything interactive is keyboard-reachable and operable, with visible focus. Modals trap focus and close on Escape.
- Images have meaningful `alt` (or empty `alt` if decorative). Icon-only buttons have accessible names.
- Meet contrast requirements (WCAG AA). Never communicate by color alone.
- Respect `prefers-reduced-motion` for any non-trivial animation.

## 6. Performance

- Don't ship what isn't needed: code-split routes, lazy-load below-the-fold and heavy dependencies, tree-shakeable imports only.
- Images: correct format, sized, `loading="lazy"` where appropriate.
- Fix unnecessary re-renders by fixing state shape and component boundaries first; memoize only with a measured reason.
- Debounce/throttle high-frequency handlers (input, scroll, resize). Clean up every listener, timer, and subscription.
- No layout thrash: batch DOM reads/writes; animate `transform`/`opacity`, not layout properties.

## 7. Frontend Tests

- Test what the user sees and does: queries by role/label/text, interactions via user events — not implementation details or CSS selectors.
- Cover the states that break: error, empty, loading, edge-length content, rapid interaction.
- Mock at the network boundary (MSW or equivalent), not inside components.
- Snapshot tests only for genuinely stable output; they are not a substitute for behavioral assertions.
- Run the relevant suite (and type-check/lint) before declaring work done.

## <RULES> — Hard rules

- No hardcoded colors/spacing when design tokens exist.
- No new UI primitive without first searching for the existing one.
- No interactive element that is mouse-only or focus-invisible.
- Every async UI handles loading, error, and empty — not just success.
- No second styling system, state library, or component pattern alongside the established one.
