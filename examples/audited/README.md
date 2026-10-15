# CONNECT import examples

These files use the **Small warehouse** preset: 20 × 40 m, eaves 7 m,
pitch 1:10, eight 5 m bays. They are illustrative, not a design of your project.

- `CONNECT_2D.std`: one interior transverse frame, 5 m tributary width.
- `CONNECT_3D.std`: full building geometry. The app's solver checks transverse
  frames only; check the complete space model and connections in STAAD.
- `CONNECT_2D_user_seismic_uplift.std`: the same frame with example user inputs
  Ah = 0.1 and net roof uplift = 0.6 kN/m². These are **not site design values**.

In STAAD.Pro CONNECT Edition, open the STD and run analysis. Inspect input
errors/warnings, statics balance, supports, properties, load cases, envelopes,
deformed shape and design failures. Actual Bentley import/run was not available
in the development environment. Read `docs/SIDEBAR_STAAD_AUDIT.md` before use.

Regenerate from the workspace root: `python -m scripts.generate_audit_examples`.
