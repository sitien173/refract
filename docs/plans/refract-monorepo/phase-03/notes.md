
## Recovery Findings

### Root README migration and startup instructions

- Reproduced the invalid documented database/log wildcard sequence in an isolated `/tmp` home containing `openmcp.db`, `openmcp.db-wal`, `openmcp.db-shm`, and log files. The second `mv` exited 1: `mv: target '<temporary-home>/.refract/refract.db*': No such file or directory`.
- Removed the invalid destination-wildcard commands. README now retains `mv ~/.openmcp ~/.refract` and describes renaming database/log prefixes while preserving suffixes. The temporary directory was removed; no real migration was run.
- Added a required configuration prerequisite before server start, linked to `server/README.md#configuration`, and specified installed targets, profiles, and `default_profile`.

### Marketplace legacy-guard coverage

- Before correction, a copied temporary plugin tree with root marketplace description `OpenMCP legacy fixture` passed the contract test. This reproduced the missing coverage.
- Added `../.claude-plugin/marketplace.json` to the guard's scan. Repeating the same copied-tree fixture then failed on that path. Temporary copies were removed.
- Changed the two non-guard test diagnostic messages to Refract without removing or weakening their guards.

### Recovery verification

- `plugin/tests/run.sh`: passed, including contract guard and hook path-with-spaces check.
- Both Claude plugin validation commands passed.
- `cd server && uv run pytest`: 546 passed, 3 deselected.
- The tracked npm lockfile is unchanged from `HEAD`. Decoded embedded source in all five exported PNGs contains Refract and no old product name.
- The updated design explicitly classifies `ccG` substrings in opaque hashes or compressed pixels as non-name data. All remaining textual matches outside historical plans are only README migration/lineage, changelog lineage, and contract guard patterns.

## Review Follow-up: PNG Export Resolution

- Verified draw.io 31.1.5 help: `-s, --scale <scale>` scales diagram output; `-e` embeds the diagram; `-p` uses 1-based page indices.
- Re-exported all five existing sources with scale 2 and embedded XML. The sources, SVGs, labels, and geometry were not changed:
  - `drawio -x -f png -e -s 2 -p 1 -o docs/diagrams/refract_c4_context.drawio.png docs/diagrams/refract_c4_model.drawio`
  - `drawio -x -f png -e -s 2 -p 2 -o docs/diagrams/refract_c4_container.drawio.png docs/diagrams/refract_c4_model.drawio`
  - `drawio -x -f png -e -s 2 -p 3 -o docs/diagrams/refract_c4_component.drawio.png docs/diagrams/refract_c4_model.drawio`
  - `drawio -x -f png -e -s 2 -o docs/diagrams/refract_system_architecture.drawio.png docs/diagrams/refract_system_architecture.drawio`
  - `drawio -x -f png -e -s 2 -o docs/diagrams/refract_data_flow_diagram.drawio.png docs/diagrams/refract_data_flow_diagram.drawio`
- All five PNG signatures are valid; each contains one compressed `mxGraphModel` source with Refract labels and no OpenMCP source text. `markitdown` produced no image text; images were then visually inspected.
- Dimensions now match the original plan-base assets exactly: context 1611×1105, container 1305×1845, component 2145×2105, system architecture 1685×2085, data flow 1405×1425.
- `plugin/tests/run.sh`, `claude plugin validate .`, `claude plugin validate plugin`, and `git diff --check` passed. Textual residual search found only the approved README/CHANGELOG and contract-guard matches. The broad raw-byte search still reports the documented opaque `ccG` hash/pixel substrings, not product text.
- No plugin, manifest, documentation, draw.io source, SVG, runtime state, or dependency file was changed in this review fix; only the five PNG outputs and phase notes/journal changed.
