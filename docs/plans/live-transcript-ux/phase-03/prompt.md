# Phase 3: Package and verify the dashboard

## Objective

Package the completed frontend into `src/openmcp/dashboard_static`. Prove generated assets match source. Perform full test and browser verification.

This phase changes generated build outputs only. Do not intentionally change application source behavior.

## Scope

Generated modifications only:

- `src/openmcp/dashboard_static/index.html`
- `src/openmcp/dashboard_static/assets/`

Do not hand-edit generated files. Use the existing Vite build path.

## Tasks

### 1. Establish source baseline and build

Run the full frontend suite first. Stop if it fails. Fix source failures in their owning earlier phase.

Then run:

```bash
npm --prefix web run build
```

The configured build must empty the output directory and replace stale hashed assets.

### 2. Verify generated parity and full suites

After building:

- rerun the frontend suite;
- run the full Python suite;
- run `git diff --check`;
- confirm every referenced asset exists;
- confirm stale hashed assets are absent;
- produce a second clean build in `/tmp`;
- compare it against packaged output.

Any difference must be explained before commit.

### 3. Browser verification

Use Playwright on the requested route:

```text
http://127.0.0.1:8765/dashboard/projects/ad9a3a2d-4583-4ac7-a954-ba21c7162055/jobs/a41dab52-ca27-4139-b982-f990eaab4de8
```

At desktop width verify:

- chronological assistant and tool ordering;
- readable assistant typography;
- collapsed tool rows;
- pointer and keyboard disclosure;
- input and output formatting;
- status presentation;
- no variable-height overlap;
- manual scroll pause;
- Jump to live restoration.

At narrow width verify:

- summary wrapping;
- contained JSON and command output;
- no page-width blowout;
- usable transcript scrolling;
- reachable Jump to live control;
- expanded tools do not overlap later rows.

Check browser console errors and React warnings.

Use a transcript containing structured input, multiline output, multiple messages, and enough rows for virtualization when available. Historical jobs cannot show details discarded before Phase 1.

If browser verification finds a source defect, fix it in Phase 2 source with tests and rebuild. Never patch generated assets manually.

## Constraints

- Generated assets must come directly from Vite.
- Do not edit hashed JS, CSS, or HTML manually.
- Do not retain stale bundles.
- Do not manually select hash names.
- Do not change Vite configuration.
- Do not mix source changes into the packaging commit.
- Do not weaken tests.
- Do not alter backend behavior, quotas, lifecycle, or persistence.

## Acceptance criteria

- Production build succeeds from committed source.
- `index.html` references only current generated assets.
- Every referenced asset exists.
- Stale bundles are removed.
- A clean independent build matches packaged output.
- Full frontend tests pass.
- Full Python tests pass.
- `git diff --check` passes.
- Browser layout shows no transcript overlap.
- Expanded tools push later rows downward.
- Structured and multiline payloads remain readable.
- Manual scrolling disables following.
- Jump to live restores following.
- Pointer and keyboard disclosure both work.
- Desktop and narrow layouts remain usable.
- No unexpected console errors remain.
- The final Phase 3 diff contains generated output only.

## Verification

```bash
npm --prefix web test
npm --prefix web run build
npm --prefix web test
uv run pytest -q
git diff --check
python - <<'PY'
from pathlib import Path
import re

root = Path('src/openmcp/dashboard_static')
html = (root / 'index.html').read_text(encoding='utf-8')
refs = re.findall(r'(?:src|href)="(?:/dashboard/)?([^"]+)"', html)
missing = [ref for ref in refs if ref.startswith('assets/') and not (root / ref).is_file()]
assert not missing, f'Missing dashboard assets: {missing}'
print('All referenced dashboard assets exist.')
PY
rm -rf /tmp/openmcp-dashboard-build
npm --prefix web run build -- --outDir /tmp/openmcp-dashboard-build --emptyOutDir
diff -qr /tmp/openmcp-dashboard-build src/openmcp/dashboard_static
```

Confirm only generated dashboard output changed.

## Commit

```text
build(dashboard): package transcript improvements
```
