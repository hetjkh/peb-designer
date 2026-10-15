# Sidebar and STAAD CONNECT audit — 2026-09-25

## What is delivered

Inputs automatically regenerate the model, analysis, checks and STD text after a
350 ms typing pause. Invalid/incomplete inputs produce an inline error and prevent
copy/export of an older model. The button is now an optional immediate update.
Dynamic mezzanine fields, extension toggles, crane fields, section/material/base
selections and deflection-limit edits participate in this update path.

The **2D Preview** displays actual connected analytical joints and members at the
frame with the largest tributary width. **Layout / clearances** retains the
architectural sketch and crane annotation. **3D Model** displays the entire model;
it refreshes when visible and preserves the camera. These views have different
purposes: an annotation is not evidence that a structural member/load exists.

Choose **Structural model → STAAD export**:

- **2D frame** (UI default): STAAD PLANE, one transverse frame, its actual
  tributary loads, Z coordinates relocated to zero. This corresponds to the
  built-in transverse solver. It is not a whole-building 3D stability analysis.
- **Full 3D model**: STAAD SPACE, all frame and secondary members. Connections are
  rigid unless supports say otherwise. Bracing, diaphragm behavior and
  longitudinal stability require engineering review in STAAD.

## Control audit

| Sidebar input | Calculation / model behavior | Remaining boundary |
|---|---|---|
| Templates | Fill geometry, roof loads, mezzanine/crane presets; loading a template updates automatically | Presets are examples, not designed buildings |
| Width, length, frame type, interior spacing | Generate all frame joints and members for clear span, multi-span, multi-gable, mono-slope and asymmetric gable | Asymmetric ridge rise retains the half-width reference; individual left/right roof slopes are not independently specified |
| Bay spacing | Equal spacing or a complete expression such as `6+8+6`; totals must match length | Explicit list must include every bay |
| Eave, slope, ridge auto/manual, FFL | Affect model coordinates; derived labels use the generated geometry | Flat mezzanine mode uses its floor geometry |
| Blockwall height | Layout annotation | Main wall dead weight is not generated; no wall density/thickness input exists |
| Purlin/girt spacing | Generates longitudinal members with connections at split frame joints; spacing is a maximum, subdivided equally within each original member | Secondary sections use existing defaults; no verified purlin/girt design or automatic bracing assumptions |
| Base auto/pinned/fixed | Supports exported and applied in analysis; explicit choice is retained | Auto is a proportion/crane heuristic, not a foundation design |
| Column/rafter sections | Assigned to primary and corresponding extension members | Built-up sections are prismatic plate I sections; continuously varying PEB taper design is not implemented |
| Steel grade | E250/E350/E450 feed analysis and native rolled-member yield/ultimate parameters; the STAAD material is named STEEL and carries FY/FU values | Thickness-dependent material strengths require review |
| Secondary connections | Pinned releases both local bending moments at both ends of purlins/girts in the SPACE model; rigid option omits these releases | Connection stiffness and bracing must be checked in STAAD; primary portal joints remain rigid |
| Run analysis | Built-in 2D direct stiffness solution; unstable solves report an error | No built-in 3D, second-order, dynamic or torsional analysis |
| Run design | Preliminary IS800 LSD strength and nodal serviceability checks | Classification, LTB, connection design, effective lengths and continuous deflection envelopes are not fully implemented |
| Deflection limits | Rafter DL+LL / LL nodal displacement and wind/seismic column sway checks respond to edited limits | Internal checks at joints; not a full continuous member deflection envelope or native STAAD DFF design |
| Roof dead/collateral/live | Loads per horizontal plan area; correct half-bays at building ends and adjacent half-bays inside | Separate roof-surface-area intensity mode not implemented |
| Wind speed, k1, k3, k4 | Affect preliminary IS windward wall pressure | Not a full IS875 wind generator |
| **New: user k2** | Applied directly to design wind speed | Engineer must supply a verified terrain/height factor; terrain selector alone does not perform a table lookup |
| Terrain, enclosure | Retained and exported as input metadata | Enclosure/internal pressure and complete roof/wall zoning are not automatically generated |
| **New: net roof uplift** | Separate uniform uplift primary case plus strength/service combinations | User must supply net pressure; automatic zoning and concurrent wall/uplift patterns are not generated |
| IS zone, soil, R | Retained and exported as input metadata | Do not automatically calculate seismic forces |
| **New: seismic Ah** | Positive Ah generates separate +X and −X static joint-load cases; elevated dead weight, height-squared force distribution within each frame | User coefficient; excludes live-load mass, dynamic/torsional effects and longitudinal earthquake action; not automatic IS1893 compliance |
| ASCE family/exposure/site/Ss/S1/method flags | Retained as input metadata; manual Ah/uplift remain usable | ASCE automatic loading and strength combinations are unavailable; no IS loading silently relabeled as ASCE |
| IS800 WSD / ASCE combination choices | Explicit warning, service cases only, LSD strength design skipped | Code-specific strength combinations still need implementation |
| Mezzanine levels/start/width/height/column spacing | Floor beams connect to split main columns; shared stacked-column joints are merged | No diaphragm or slab plate model |
| Mezzanine DL/collateral/LL/blockwall | Applied to transverse girders using actual frame tributary width; blockwall is a line load on selected floor beams | Wall layout/distribution must be reviewed |
| Mezzanine joist spacing | Retained in input metadata | Individual joists are not modeled; changing this does not change the total floor load |
| Mezzanine base connection / flat mode | Pinned/fixed bases applied, including flat mode | This control sets column bases, not beam-end releases |
| Lean-to left/right/dimensions/base | Connected rafters/columns, matching supports, self-weight and entered roof area loads | No separate lean-to cladding pressure zoning |
| Roof extensions / canopies | Connected members; roof extension follows the adjacent roof slope; self-weight and roof area loads | Bracket/connection design not performed |
| Roof monitor | Connected posts and pitched cap members with self-weight | Cladding and monitor wind pressure require separate loading |
| Fascia / cover ridge | Architectural annotation | No invented coincident structural member or fascia dead/wind load; cover-ridge intent needs a defined geometry specification |
| Crane manufacturer/name/capacity/hook/bridge/trolley/wheels/span | Stored; clearance annotation; capacity participates in Auto base recommendation | No wheel positions, runway beams, impact, surge, braking, moving-load envelope or complete crane load cases |
| Preferences / section database | Defaults and catalog changes feed subsequent updates | Actual catalog data are approximate and require approved section-property verification |

## STD content and fixes

- Joint coordinates retain sufficient precision for round trips.
- Rolled sections use compact STAAD names (`ISMB400`). Built-up I sections use
  dimensional TAPERED properties with equal end depths, not fictitious TABLE names.
- Isotropic materials, material assignments and supports are written.
- For one selected grade, STAAD's isotropic material is named `STEEL`; its
  strength definition and `FYLD`/`FU` design parameters retain the selected
  E-grade. Secondary simple-span releases populate STAAD Specifications only
  in the SPACE model. The PLANE portal frame has no release specification.
- Every defined primary case has a stable number. Nodal-only cases are retained.
  Member GX/GY/GZ and joint FX/FY/FZ components are exported.
- Self-weight is represented by explicit loads, **not** also added with SELFWEIGHT.
  Secondary longitudinal-member weight transfers as simple-span end reactions.
- Strength/service combinations, envelopes, analysis, statics check, support
  reactions and member force output are included. Rolled and built-up primary
  I-members receive optional native IS800 LSD strength checks when design is
  enabled, with STP, BEAM, TRACK and physical LX/LY/LZ parameters. Native run
  validation and restraint review are required. See the
  [reference-based update](REFERENCE_STAAD_UPDATE.md) for P-Delta export and import.
- Long input lines are continued within STAAD's input width.
- Unknown load targets/cases, nonfinite values and invalid combinations are rejected.
- Imported STD files keep their original command text for export; the geometry
  importer is not a complete parser for arbitrary STAAD analysis/design commands.
- Analytical subdivisions retain original member lengths for preliminary buckling
  checks; adding joints must not pretend to shorten unbraced physical members.

Wind/seismic metadata comments are **not native wind/seismic generator definitions**.
The generated cases contain explicit equivalent loads. The file is not a complete
code-compliant project until the unresolved loading and design requirements above
are supplied and checked.

## Verification

175 tests passed at this audit checkpoint (existing suite plus new regressions).
New checks cover automatic updates, invalid-input export protection, dynamic
mezzanine fields, irregular bays, roof/floor load conservation, connected
extensions, material/section syntax, all force axes, equivalent seismic base
shear, deflection limits, unsupported-code behavior and unstable frames.

The analytical 2D view was rendered to a PNG successfully. A full desktop smoke
test in the headless environment failed during VTK/OpenGL initialization before
the window could be exercised. STAAD.Pro is not installed in the checked program
directories; neither actual CONNECT import nor Bentley analysis was executed.
String/round-trip tests are not a substitute for running Bentley's parser/solver.

## Bentley references checked

- [Material definitions and CONSTANTS assignments](https://bentleysystems.service-now.com/community?id=kb_article&sysparm_article=KB0113765)
- [STAAD PLANE assumptions and incompatible out-of-plane loads](https://bentleysystems.service-now.com/community?id=kb_article_view&sysparm_article=KB0112760)
- [IS800 serviceability and strength envelopes](https://bentleysystems.service-now.com/community?id=kb_article&sysparm_article=KB0114350)
- [CONNECT V22 Update 12 notes, including tapered-section limitations](https://bentleysystems.service-now.com/community?id=kb_article&sysparm_article=KB0112363)
- [Later correction documenting IS800 tapered-member support limitations](https://bentleysystems.service-now.com/community?id=kb_article_view&sysparm_article=KB0048348)
