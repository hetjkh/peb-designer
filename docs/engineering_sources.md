# Engineering sources & assumptions (Milestones 2–5)

This document lists formula sources and explicit simplifying assumptions.
**Do not use results for construction until independently validated.**

## Materials
- E, G, γ_m0, γ_m1: IS 800:2007 Clause 2.2.4 / Table 5
- fy / fu for E250, E350, E450: IS 2062 grade practice

## Sections
- ISMB seed properties: typical published ISMB tables (verify against SP 6 / approved section book)

## Loads
- Roof UNI = intensity (kN/m²) × average bay spacing (m) — geometric tributary assumption
- Self-weight from section mass × g
- Wind: IS 875 (Part 3) style `pz = 0.6 Vz²` with `Vz = Vb·k1·k2·k3·k4`
  - Assumptions: k1=k3=k4=1.0; coarse Terrain Category 2 k2; windward Cp=+0.8 only
- Combinations: IS 800:2007 Table 4 (partial set C1–C6)

## Analysis
- Built-in DirectStiffness2DEngine (plane frame, 3 DOF/node)
- Each constant-Z transverse frame solved in X–Y
- Classical beam stiffness (Weaver/Gere / matrix structural analysis)
- OpenSees optional later via same `AnalysisEngine` interface

## Design (IS 800:2007)
- Tension Cl. 6.2
- Compression Cl. 7.1.2 (χ, λ_nd); buckling curve ‘a’ (α=0.21) for all — simplified
- Bending Cl. 8.2.1 with βb=1.0 and Zp≈1.2 Ze — section class not computed
- Shear Cl. 8.4 with Av≈h·tw
- Combined Cl. 9.3.1 simplified interaction Nc/Pd + M/Md
- Effective length factor K=1.0 default
