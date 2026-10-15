# Checking the PEB sample in STAAD.Pro CONNECT Edition

Use `PEB_CONNECT_2D_v2.std` first, then `PEB_CONNECT_3D_v2.std`. These are
sample inputs from the app defaults, not a verified project design. Keep the
original files and analyse copies so STAAD can write its output alongside them.

## 1. Check the imported model before analysis

| Check | 2D sample | 3D sample |
| --- | ---: | ---: |
| Input units in STD | m, kN | m, kN |
| Joints | 39 | 351 |
| Members | 38 | 638 |
| Base supports | 2 pinned | 18 pinned |
| Building dimensions | 40 m span, 6.5 m eave, 8.5 m ridge | 40 m span, 60 m length, 6.5 m eave, 8.5 m ridge |
| Material | `STEEL`, grade E350, `FYLD 350000` kN/m² | same |
| Sections | ISMB400 columns, ISMB350 rafters | plus ISMB300 purlins/girts |

In STAAD, verify Geometry, Properties, Materials, Supports and Loading. In
the 3D sample, Specifications should show moment releases at both ends of
purlin/girt members 37–332. The 2D sample has no member specifications; an
empty Specifications list is expected there. STAAD may *display* lengths in
feet if its current display units are set to feet; `UNIT METER KN` is the
input declaration in both files. Check the numerical dimensions after setting
display units to metres.

## 2. Run analysis and check the output

Choose **Analysis and Design → Run Analysis**. Open **Utilities → Analysis
Output** and search for `ERROR`, `WARNING`, `INSTABILITY`, `ZERO STIFFNESS`,
`STATICS CHECK`, and `CHECK CODE`. Investigate every instability and unexpected
warning. Both STD files already contain `PERFORM ANALYSIS PRINT STATICS CHECK`
and `PRINT SUPPORT REACTION`.

The applied force totals below were summed independently from every `MEMBER
LOAD` and `JOINT LOAD` entry in each STD using `check_export_loads.py`. In
STAAD's statics check, the **sum of support reactions** should have the
opposite sign to the applied force. Allow small rounding differences from
STAAD's displayed precision.

| File | Primary case | Applied load | Expected sum of support reactions |
| --- | --- | ---: | ---: |
| 2D | 1 Dead | FY = −265.869 kN | FY = +265.869 kN |
| 2D | 2 Live | FY = −225.000 kN | FY = +225.000 kN |
| 2D | 3 Wind | FX = +51.691 kN | FX = −51.691 kN |
| 3D | 1 Dead | FY = −2155.223 kN | FY = +2155.223 kN |
| 3D | 2 Live | FY = −1800.000 kN | FY = +1800.000 kN |
| 3D | 3 Wind | FX = +413.525 kN | FX = −413.525 kN |

All other force components should sum to approximately zero. Individual
supports can carry forces in other directions that cancel across all supports.
Case 2 has a simple independent check: 0.75 kN/m² × 40 m × 7.5 m = 225 kN
for the interior 2D frame, and 0.75 kN/m² × 40 m × 60 m = 1800 kN for 3D.

## 3. Inspect physical behaviour and design

In **Postprocessing**, select each primary case and inspect the deformed
shape, node displacement values, support reactions, member axial/shear/bending
diagrams, and steel design utilization. Case 1 and 2 should sag under gravity;
case 3 should sway in the wind direction. Compare results for representative
columns, rafters, and secondary members to a hand calculation. Check
connections and bracing assumptions, local/global axis orientation, and
serviceability limits against the project requirements. A successful analysis
or a strength `PASS` alone does not establish that the structure is suitable.

The export defines strength cases 100–107 and service cases 108–110. The
current `CHECK CODE` uses `LOAD LIST ENVELOPE 1` only, and no `DFF` parameter
is set. Therefore **STAAD's automated IS 800 deflection design check is not
performed** by these files; assess displacements separately until this is
added and verified. Only the rolled primary frame members are included in
`CHECK CODE`; purlins/girts need separate design verification.

The files also mark the remaining load/design assumptions in `* REVIEW:`
comments. In particular, wind is a preliminary windward-wall case with no
roof suction/zones, automatic seismic loads are absent, and blockwall dead
load is absent. Crane loads require actual project crane data. These omissions
mean reaction equilibrium and a `PASS` result cannot validate the full project
loading. Have the complete load basis and member design independently checked
before use for construction.

If a result differs from the table, retain the analysed `.std` and its STAAD
analysis output (`.anl` or `.out`), especially the first error/warning, the
`STATICS CHECK` table, support reactions, maximum displacements, and the
steel design summary. Those identify whether the issue is import syntax,
loading, stability, or member capacity.
