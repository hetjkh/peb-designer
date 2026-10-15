"""
# Running the full test suite

```bash
cd peb-designer
.\.venv\Scripts\activate
pytest -q
```

## Coverage map

| Area | Folder |
|------|--------|
| Core model / assign | `tests/core/` |
| Geometry / validation | `tests/geometry/` |
| Templates + 2D | `tests/templates/` |
| Sections / materials | `tests/database/` |
| Loads / wind / combos | `tests/loads/` |
| Analysis engine | `tests/analysis/` |
| IS 800 design | `tests/design/` |
| STAAD export | `tests/export/` |
| Full pipeline E2E | `tests/e2e/` |

End-to-end tests run **every pre-built template** through:
geometry → sections/supports → loads → analysis → design → STAAD text → 2D preview.
"""
