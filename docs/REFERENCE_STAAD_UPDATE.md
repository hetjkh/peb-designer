# Reference-based STAAD update — 15 October 2026

## Using the update

1. Run the updated app and choose **Import STD**. Open
   `without optimization/Project 1.STD`. Leave `Project 1.ANL` beside it.
2. Open **Model audit** for assignments, combinations, warnings and check coverage.
   The importer compares the ANL's entire numbered input echo with the STD before
   attaching results. Changed input, incomplete runs and error reports are rejected.
3. Enable **Utilization colors** in 3D: red = native FAIL, green/orange = native
   PASS, gray = no imported result. Purple highlights the selected member.
4. Use **Select member** in **Member inspector** for dimensions, actual material,
   beta angle, releases, tension flags, FYLD/FU, LX/LY/LZ, factors, and native checks.
   STAAD's native PASS/FAIL is retained even when its allowable RATIO is not 1.
5. Choose a **2D: Z=...** station and open **2D Preview** for a geometry slice.
   This slice is not an independent analysis model or an export of that frame.
6. Export retains the full original native input, including commands that the app
   cannot evaluate. Native load diagrams must be viewed in STAAD. Sidebar changes
   create a new generated model; they do not resize the imported reference.

For generated models, **Structural → STAAD analysis** offers first-order or
**P-Delta + repeat loads (20 iterations)**. Every combination is converted to a
simultaneous repeat-load case for the second-order export. The app results still
come from its first-order 2D solver. Review convergence and displacement in STAAD;
20 iterations is an input setting, not proof of convergence.

Native IS800 LSD strength checks now include rolled and built-up primary I-members,
with STP 1/2, BEAM 1, TRACK 2, and full physical LX/LY/LZ rather than mesh lengths.
The generated built-up properties currently have equal start/end depth. Actual
restraints, effective-length factors and check applicability need project review.
No claim is made that merely changing the analysis command resolves failures.

## What the supplied files establish

The original STD and ANL match after ignoring formatting/comments and STAAD's
omitted terminal semicolons. The run identifies STAAD CONNECT 22.00.00.15.

| Item | Native reference |
|---|---|
| Nodes / members / supports | 164 / 298 / 38 |
| Primary cases / combinations | 8 / 32 |
| Tapered / round PRIS / table assignments | 154 / 60 / 84 members |
| Released / tension-only members | 91 / 60 |
| Checked / passing / failing | 235 / 171 / 64 |
| Outside CHECK CODE | 63 |
| Worst reported result | Member 154, ratio 6.995, case 118 |
| Amplification warnings | Members 18 and 19, case 111 |

The main frame is 36 m wide with central columns at X=18 m, eaves at Y=10 m,
ridge Y=11.5 m and building length 72.2 m. Ten stations have 8.1 m end bays and
8 m intermediate bays. A 3 m canopy extends to X=-3 m. The model bounding width
is therefore 39 m, not the main frame's clear span. End-wall columns, longitudinal
members, releases and bracing also differ from the earlier 40 m clear-span test.

All members have the native material name **STEEL**. Grade strength is separately
assigned through FYLD: 345 MPa for the relevant fabricated members, 310 MPa for
tubes, and 250 MPa for rods. A material name alone does not identify design strength.

## Items to resolve before using this as an engineering benchmark

- Combination **118** is titled `0.9 DL + 1.5ELX+` but contains `3 0.9 1 11.5`.
  Confirm the intended factor with the engineer. The importer flags it and preserves
  the source; it has not silently changed 11.5 to 1.5. Re-run after any correction.
- The reference combines tension-only members using regular `LOAD COMB`, and has
  amplification warnings requiring second-order review. A correctly reviewed
  analysis sequence with repeat loads is needed; merely superposing independently
  solved cases cannot establish the brace state under simultaneous loads.
- DL, LL and wind cases are all labelled `LOADTYPE Seismic`. Correct their types
  after confirming the intended cases. Labels alone do not alter the explicit forces.
- Rod members 230–289 and cold-formed members 292, 297, 298 are outside CHECK CODE.
  They need appropriate checks; absence of a failure is not a pass.
- Service envelopes exist, but no DFF check is specified. Check deflection, drift,
  appropriate service combinations and physical span endpoints separately.
- Review physical restraints and buckling lengths, joint assumptions, load takeoff,
  wind/internal pressure cases, seismic weights, supports, and connections. The
  failed reference is useful for software comparison, not an approved design.

## Implemented versus remaining

Implemented: unit-aware geometry import; TABLE/TAPERED/PRIS preservation; actual
material assignment; releases/beta/tension specifications; partial support flags;
global UDL and joint-force parsing; native load definitions/local loads retained;
combination factors/envelopes; native parameter inspection; matched ANL summaries;
audit and 2D/3D review; protected lossless re-export; generated second-order option;
native built-up primary checks and physical LX export.

Remaining: a complete 3D/nonlinear app solver, arbitrary native model editing,
native local/generated load diagrams, ANL force/displacement-table import,
automatic optimization, complete code-based wind/seismic/crane generation,
native serviceability parameter export and full design-code validation. None of
these is supplied by importing one example. Native result summaries are imported,
not recalculated, and the existing load limitations still apply.

The original reference files were not modified. `staad_test/reference_project1`
contains the application-produced audit and a preserved STD export for comparison.
Bentley was not run in this environment; re-run newly generated exports in CONNECT.

Regenerate the audit with:

```powershell
.venv\Scripts\python.exe -m app.export.staad_audit "without optimization/Project 1.STD" --output-dir staad_test/reference_project1
```

## Bentley references

- [Tension members and combination versus repeat loads](https://bentleysystems.service-now.com/community?id=kb_article_view&sysparm_article=KB0113645)
- [Tapered-member IS800 implementation history](https://bentleysystems.service-now.com/community?id=kb_article_view&sysparm_article=KB0115118)
- [CONNECT analysis-option interface](https://bentleysystems.service-now.com/community?id=kb_article&sysparm_article=KB0112363)
