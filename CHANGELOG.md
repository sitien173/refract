# Changelog

## 1.2.0 - 2026-10-12

- `executing-plans`: removed the consult step and the first, resumed, and fix submission templates from `implementer-prompt.md`; phase prompts drop the `SKILLS` section and use minimal rules.
- `writing-plans`: removed the recommended phase-detailing consult step.
- Phase prompt `Rules` now carry absolute pointers to the bundled worker contract, ERP, and templates; Gate 2 job prompts name the phase prompt path.
- Gate 1 no longer consults: the route is `implement -> review`, and handover drops `guidance.consult` and `job_refs.latest_consult`. `brainstorming` still uses `consult`.

## 1.0.0 - 2026-10-08

- Refract 1.0.0 combines the plugin, server, and dashboard under one product name.
- Lineage: superpowers-ccg 12.0.0 and openmcp 2.0.0.
