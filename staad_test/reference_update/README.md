# Updated application exports for STAAD CONNECT testing

These files were generated through the updated application input panel:

- `PEB_CONNECT_2D_v3.std`: one transverse PLANE frame, 39 nodes / 38 members.
- `PEB_CONNECT_3D_v3.std`: full SPACE model, 351 nodes / 638 members. The internal
  app solver does not verify longitudinal stability.

They retain the default 40 m × 60 m clear-span geometry, 6.5 m eaves, 1:10 pitch,
7.5 m bays, E350 grade, ISMB400 columns and ISMB350 rafters. The 36 m centrally
supported reference is a different structure; its dimensions and restraints have
not been substituted into these files.

New native export features: simultaneous REPEAT LOAD cases, PDELTA 20 ANALYSIS
SMALLDELTA, full physical LX/LY/LZ, STP, BEAM 1 and TRACK 2. Load case numbers,
combination factors and geometry were checked through re-import. App calculations
remain first-order. These files have not been executed in Bentley STAAD here.

Open the **2D v3** file first, run analysis/design, and return its `.ANL` together
with the exact `.STD` used. Check analysis errors, amplification/convergence
messages, displacements, reactions and failed-member ratios. The current sections
have not been optimized or declared adequate; P-Delta may increase demands.

Loading remains preliminary (see comments inside the STD). Complete engineering
loads and verified restraints are still required before construction use.

The unchanged supplied reference export and its audit are in
`../reference_project1/`. That original run reports 171 PASS, 64 FAIL and 63
unchecked members, including an unusually large case-118 factor of 11.5.

To regenerate these application exports without overwriting older v2 files:

```powershell
.venv\Scripts\python.exe -m scripts.create_connect_test_files --output-dir staad_test/reference_update --revision v3 --staad-analysis pdelta
```
