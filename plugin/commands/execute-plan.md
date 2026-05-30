---
description: Run the active (or named) plan phase under the Plan → Execute → Review gates.
argument-hint: [plan dir/slug or phase number, optional]
---

Invoke the `superpowers-ccg:executing-plans` skill and run the requested phase under the three gates. Load `.handover.md` and the `read_first` files before acting; reuse cached `session_refs`. After the last phase, hand off to `superpowers-ccg:verifying-before-completion`.

Target (optional): $ARGUMENTS
