# PEB Designer

Free, independent **Pre-Engineered Building (PEB)** structural design and optimization desktop software.

Built from scratch with open-source technologies. Not affiliated with, derived from, or a copy of STAGen or any proprietary PEB software.

> **Engineering notice:** Results are for development and educational use until calculations are independently validated by a qualified structural engineer. Do not use unvalidated output for real construction.

## Current status — v0.3.0 (Milestones 1–5 foundation)

Working desktop app that:

- Generates PEB geometry (single / multi-span / multi-gable) with templates
- Assigns steel sections, materials, and pinned/fixed supports
- Builds dead / live / simplified wind loads and IS 800 Table 4 combinations
- Runs a built-in 2D direct-stiffness analysis engine
- Performs simplified IS 800:2007 member checks with utilization
- Exports STAAD `.std` and shows 2D/3D views with member info

> Results are **not** validated for construction design.

## Live updates and STAAD CONNECT audit

Inputs now update automatically. The default UI export is a transverse **STAAD
PLANE** frame; full SPACE export is also selectable. See
[the detailed option audit](docs/SIDEBAR_STAAD_AUDIT.md) for implemented controls,
load assumptions and remaining automatic wind/seismic/crane limitations.

STAAD reference import now retains the original native input, reads section and
material assignments, releases, design parameters, loads and combinations, and
attaches code-check results only from a matching, completed `.ANL` file. Use
**Import STD**, then **Model audit**, **Member inspector**, and the 2D station
selector. See [reference review and limitations](docs/REFERENCE_STAAD_UPDATE.md).
Generated models offer a **STAAD analysis** choice of first-order or P-Delta
with repeat loads. The app's internal analysis remains first-order 2D.

STAAD reference import now retains the original native input, reads section and
material assignments, releases, design parameters, loads and combinations, and
attaches code-check results only from a matching, completed `.ANL` file. Use
**Import STD**, then **Model audit**, **Member inspector**, and the 2D station
selector. See [reference review and limitations](docs/REFERENCE_STAAD_UPDATE.md).
Generated models offer a **STAAD analysis** choice of first-order or P-Delta
with repeat loads. The app's internal analysis remains first-order 2D.

## Requirements

- Python 3.10+
- See `requirements.txt`

## Install

```bash
cd peb-designer
python -m venv .venv

# Windows
.venv\Scripts\activate

# Linux / macOS
# source .venv/bin/activate

pip install -r requirements.txt
```

## Run

```bash
python -m app.main
```

## Share with testers (Windows package)

Build a zip that others can run **without Python**:

```powershell
cd peb-designer
.\.venv\Scripts\activate
powershell -ExecutionPolicy Bypass -File scripts\build_windows.ps1
```

Send them: `dist\PEBDesigner-Windows.zip`  
They unzip and double-click `PEBDesigner\PEBDesigner.exe`  
Instructions for testers: `docs\HOW_TO_TEST.txt`

## Architecture

See [docs/architecture.md](docs/architecture.md).

## License

Third-party licenses for dependencies will be documented under `docs/` as packages are added. Application code license TBD.
