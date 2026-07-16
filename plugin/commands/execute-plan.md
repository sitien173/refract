---
description: Run the active (or named) plan phase under the Plan → Execute → Review gates.
argument-hint: [plan dir/slug or phase number, optional]
---

Invoke the `superpowers-ccg:executing-plans` skill. Run the requested phase under the three gates. Require folder layout. Initialize project OpenMCP files when needed. Load `.handover.md`, validated `read_first` files, and matching project jobs before resolving new routing. Coordinator selects configured nicknames and execution roles. Existing phase chains retain stored routing. After the last phase, hand off to `superpowers-ccg:verifying-before-completion`.

Target (optional): $ARGUMENTS
