# Architecture — PEB Designer

## Design principles

1. **Modular layers** — GUI, geometry, loads, analysis, design, and reporting stay separate.
2. **Engine-agnostic core** — Internal `Node` / `Member` / `StructuralModel` types do not depend on any solver.
3. **Incremental delivery** — Only Milestone 1 is implemented; later folders are placeholders.
4. **Documented engineering** — Every formula must cite a source; unknown assumptions are not hard-coded silently.
5. **Independent product** — Original UI, geometry logic, and workflow. No proprietary PEB software is copied.

## Package layout

```text
peb-designer/
├── app/
│   ├── main.py              # Application entry
│   ├── gui/                 # PySide6 windows and panels
│   ├── core/                # Shared structural data models
│   ├── geometry/            # PEB geometry generation + validation
│   ├── loads/               # (Milestone 3)
│   ├── analysis/            # (Milestone 4) solver abstraction
│   ├── design/              # (Milestone 5) code checks
│   ├── optimization/        # (Milestone 6)
│   ├── database/            # (sections / materials SQLite)
│   ├── visualization/       # 3D viewer (PyVista)
│   └── reports/             # (Milestone 7) PDF
├── tests/
├── data/
├── docs/
└── examples/
```

## Milestone 1 data flow

```text
Geometry panel (GUI)
        │
        ▼
Input validation (geometry/validation.py)
        │
        ▼
PEB frame builder (geometry/peb_frame.py)
        │
        ▼
StructuralModel (core/models.py)
        │
        ▼
3D Viewer (visualization/viewer_3d.py)
```

## Coordinate system (Milestone 1)

| Axis | Meaning |
|------|---------|
| X    | Building span (width) |
| Y    | Vertical (height) |
| Z    | Building length (bay direction) |

## Single portal frame topology

For each frame at position `z`:

| Node role   | Coordinates |
|-------------|-------------|
| Left base   | `(0, 0, z)` |
| Left eave   | `(0, H_eave, z)` |
| Ridge       | `(L/2, H_ridge, z)` |
| Right eave  | `(L, H_eave, z)` |
| Right base  | `(L, 0, z)` |

Where:

- `L` = span
- `H_eave` = eave height
- `θ` = roof slope (degrees from horizontal)
- `H_ridge = H_eave + (L/2) · tan(θ)`

Members per frame: left column, left rafter, right rafter, right column.

Number of frames: `n = round(Length / BaySpacing) + 1`, with Length required to be an integer multiple of BaySpacing (within tolerance).

## Future solver boundary

```text
StructuralModel  →  AnalysisEngine (interface)  →  OpenSees / other
```

The GUI and design modules will only talk to `StructuralModel` and the analysis interface, never to a specific solver API.
