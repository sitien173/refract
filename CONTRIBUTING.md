# Contributing to Refract

This guide records the coding conventions already used in this repository.
Follow it for new code. Where a rule here and the existing file disagree, match
the file you are editing and note the mismatch in review.

[`AGENTS.md`](AGENTS.md) holds the build and test commands and the repository
invariants: versions, changelog, dashboard bundle, pinned docs, manifests,
example config, and credentials. Read it first. This guide covers style only.

## 1. General

- All text files: UTF-8, LF line endings, final newline, no trailing
  whitespace. Indent with 2 spaces, or 4 spaces in Python and shell.
  [`.editorconfig`](.editorconfig) is the source of truth.
- Keep every change portable across Linux, macOS, and Windows. Server CI runs
  on all three.
- Launch subprocesses with argv lists. Never use a shell string.
- Comments explain why. Leave out comments that restate the code.

## 2. Python: `server/`

Python 3.12. No formatter, linter, or type checker runs in CI, so these rules
are enforced by review.

### Formatting

- 4-space indent, double quotes, magic trailing commas on multi-line calls and
  literals.
- Keep lines under 100 characters. About 97% of current lines comply.
- Two blank lines between top-level definitions.
- Imports in three groups separated by blank lines: stdlib, third-party, local.
- Use absolute `from refract...` imports. Relative imports are used only inside
  `backends/`.
- Start each module with `from __future__ import annotations`.

### Naming

| Item | Convention | Example |
|---|---|---|
| Modules | `snake_case` | `codex_rollout.py` |
| Private helper modules | `_snake_case` | `backends/_process.py` |
| Functions, methods | `snake_case`; `_` prefix when module-private | `_read_tail` |
| Classes | `PascalCase` | `BackendResult` |
| Per-run backend state | `<Name>Run` | `CodexRun` |
| Constants | `UPPER_SNAKE`; `_UPPER_SNAKE` when private | `TAIL_BYTES` |
| Module logger | `log = get_logger("<area>")` | `drivers.py` |

Prefer module-private helpers. About 80% of module-level functions are private.

### Types

- Annotate every function, including the return type.
- Use built-in generics and unions: `list[str]`, `dict[str, int]`,
  `X | None`. Use `collections.abc` for `Callable`, `Sequence`, `Mapping`, and
  `Iterable`.
- Use `@dataclass(slots=True, frozen=True)` for value objects.
- Use Pydantic `BaseModel` only for API-facing models in `models.py`.
- Avoid `# type: ignore`. Source code has three, all in `updater.py`.

### Docstrings and comments

- Every module starts with a docstring.
- Function docstrings are plain prose. Skip `Args:` or `:param:` sections.
  Add a docstring when the name and signature do not explain the behavior.

### Errors and logging

- Raise a domain exception: `AskError`, `CardError`, `OrchestrationError`,
  `ConfigurationLoadError`, or a new subclass next to them. Chain with
  `raise ... from err` when translating an exception.
- Backends return a `BackendResult` for worker failures instead of raising.
- Catch `Exception` only at boundaries. Log it with `exc_info` or mark it with
  `# noqa: BLE001` and a reason. Never use a bare `except:`.
- Log through `log`. Pass structured context with `extra={"event": ...}`.
  Use lazy `%` arguments, not f-strings, in log calls. Never `print()` in
  `src/`.
- Use `pathlib.Path` for filesystem paths.

### Backends

Each driver in `server/src/refract/backends/` exposes
`async def execute(params, *, cancel=None, on_event=None) -> BackendResult`
and keeps per-run state in a `<Name>Run` class. Shared helpers live in
`_common.py` and `_process.py`. Argv builders live in `drivers.py`.

### Tests

- pytest. Module-level `test_*` functions only, no test classes.
- Name tests as behavior sentences: `test_notes_does_not_match_version_prefix`.
  Prefix live tests with `test_live_` and mark them `@pytest.mark.live`.
- Mark async tests with `@pytest.mark.asyncio`. `asyncio_mode` is strict.
- Prefer `tmp_path`, `monkeypatch`, and hand-written fakes over `MagicMock`.
- Use `@pytest.mark.parametrize` with `ids=` for case tables.
- Fake worker CLIs come from `tests/fixtures/fake_cli/`, reached through
  `tests/cli_stub.py` or `tests/launchers.py` so they run on Windows.

## 3. TypeScript: `server/web/`

Biome and `tsconfig.json` enforce formatting and strictness. Run
`pnpm exec biome ci .` before committing. Current settings: 2-space indent,
double quotes, semicolons, 180-column lines, organized imports, `strict`, and
no unused locals or parameters.

### Layout

| Path | Contents |
|---|---|
| `src/api.ts` | Zod schemas, inferred types, `request()` fetch wrapper |
| `src/components/` | Feature components, `PascalCase.tsx` |
| `src/components/ui/` | shadcn components on Base UI, `kebab-case.tsx` |
| `src/views/` | Page views |
| `src/hooks/` | TanStack Query hooks; `queries.ts` plus `useX.ts` files |
| `src/lib/` | Pure helpers, including `cn` |
| `src/test/` | Shared test setup |
| `e2e/` | Playwright specs |

Colocate unit tests: `Foo.test.tsx` beside `Foo.tsx`.

### Code

- Components are `export function Name()` declarations. Use named exports
  only. Skip `React.FC` and `forwardRef`.
- Prefer `type` over `interface`. Name props types `<Component>Props`.
- Name Zod schemas `<Name>Schema` and derive types with `z.infer`. Parse every
  API response through `request()` so failures map to `DashboardApiError`.
- Query keys are arrays starting with the resource: `["job", id]`,
  `["jobs", filters]`. Mutations invalidate the keys they affect.
- Query hooks accept an optional injected loader for tests.
- Module-level shared constants use `UPPER_SNAKE`.
- Import `components/ui` and `lib/utils` through the `@/` alias. Import
  `api`, hooks, and sibling modules with relative paths.
- Use `cn` to merge class names in `components/ui`. Static class strings are
  fine in feature components.
- Use no `as any` or `@ts-ignore`. Give every `biome-ignore` a reason.

### Tests

- Vitest: `it("does something")` with behavior titles. Import from
  `"vitest"` explicitly.
- Query by role first: `getByRole`, then `getByLabelText`, then `getByText`.
  Avoid `getByTestId`.
- Mock by injection: pass `load`, `post`, or `fetcher`. Use `vi.mock` only
  as a last resort.
- Playwright: role and label locators, web-first assertions, `expect.poll`
  for server state. Never use fixed sleeps.
- After editing `src/`, rebuild and commit the bundle. See `AGENTS.md`.

## 4. Shell and plugin: `plugin/`, `scripts/`

### Shell

- Start with `#!/usr/bin/env bash` and `set -euo pipefail`. Set the exec bit.
- Resolve the repo root from `${BASH_SOURCE[0]}`, as the existing tests do.
- Quote every expansion. Name functions in `snake_case`.
- Use quoted heredoc delimiters, such as `<<'PY'`, for embedded code.
- Create temp dirs with `mktemp -d` and clean them up with `trap ... EXIT`.
- End a test script with a `printf '... tests passed\n'` line.

### Python scripts and hooks

Follow section 2. Guard entry points with `if __name__ == "__main__":`.

### Pi extension

`plugin/pi/extensions/refract.ts` follows the dashboard formatting: 2 spaces,
double quotes, semicolons, `node:` import specifiers. Run processes with
`execFileSync` and an argv array.

## 5. Markdown and skills

- Use `-` bullets and one H1 per file. Give every code fence a language;
  use `text` for templates.
- Write without em dashes. Use a hyphen or restructure the sentence.
- Skill frontmatter has `name` and a double-quoted `description`. Add
  `compatibility` or `disable-model-invocation` only when needed.
- Skill H2s use Title Case. Reuse the standard sections: `## Role`,
  `## Workflow`, `## Constraints`, `## Output Format`.
- In skills, name other skills in plain backticks, such as
  `` `coordinating-multi-model-work` ``. Write tools as bare calls, such as
  `list(path)`. The SessionStart hook adds host prefixes.
- Link files with relative paths.
- Skill files have line caps checked by `plugin/tests/test-contracts.sh`.
  Read its assertions before editing a pinned file.
- Command files in `plugin/commands/` hold frontmatter and a single
  "Invoke `<skill>`" line.

## 6. Commits and changelog

- Use Conventional Commits: `type(scope): subject`. Write the subject in
  lowercase and the imperative mood, without a trailing period.
  - Types in use: `fix`, `docs`, `test`, `refactor`, `chore`.
  - Scopes in use: `server`, `plugin`, `site`, `release`.
- Wrap commit bodies at 72 columns. One logical change per commit.
- Add each user-visible change to `CHANGELOG.md` under `## Unreleased` as a
  `- ` bullet. Write it in sentence case and end it with a period.
- Release headings use `## <version> - <YYYY-MM-DD>`. Do not edit them by
  hand; `scripts/bump_version.py` owns versions.

## 7. Known deviations

These files currently differ from the majority pattern. Fix them when you are
already editing nearby code. Do not open changes only to fix them.

| Area | Deviation |
|---|---|
| Python future import | Missing in `workers.py`, `__init__.py`, `backends/__init__.py` |
| Python logger | `scheduler.py` uses `logging.getLogger(__name__)` |
| Python blank lines | `models.py:16`, `dashboard.py:164`, `config.py:126`, `server.py:321`, `backends/__init__.py:29` |
| Python line length | `server.py:371` is 399 characters |
| Python broad catches | Most `except Exception` sites lack `# noqa: BLE001` or `exc_info` |
| TS imports | `JobActions.tsx` and `BoardView.tsx` mix `@/` and relative paths |
| TS schema names | `JobPageSchema`, `OutputPageSchema` lack the `Response` suffix |
| TS constants | `const base` in `api.ts` is not `UPPER_SNAKE` |
| TS helpers | `messageOf` has two different signatures in `App.tsx` and `useJobPages.ts` |
| TS query options | Mutations repeat `retry: false`, which `main.tsx` already sets globally |
| Biome config | `biome.json` uses the deprecated `recommended` key |
| Scripts | `scripts/bump_version.py` lacks the exec bit |
| Hook | `refract-session-start.py` runs at module level, without a `__main__` guard |
| Skill frontmatter | `setting-up-refract/SKILL.md` has an unquoted `description` |
| Plugin portability | Plugin tests run only on Ubuntu and use GNU `date +%s%N` and `timeout` |

## 8. Changing this guide

Propose changes in the same pull request as the code that motivates them.
When a rule becomes tool-enforced, replace the rule with a pointer to the
tool's config.
