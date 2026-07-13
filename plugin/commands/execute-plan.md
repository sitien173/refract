---
description: Run the active (or named) plan phase under the Plan → Execute → Review gates.
argument-hint: [plan dir/slug or phase number, optional]
---

Invoke the `superpowers-ccg:executing-plans` skill and run the requested phase under the three gates. Require folder layout. Load `.handover.md` and validated `read_first` files before acting. Reuse session identifiers only within their recorded phase. After the last phase, hand off to `superpowers-ccg:verifying-before-completion`.

Target (optional): $ARGUMENTS
