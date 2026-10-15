"""Reproducible CONNECT examples; illustrative inputs, not project designs."""
from dataclasses import replace
from pathlib import Path

from app.core.pipeline import PipelineOptions, run_pipeline
from app.templates.catalog import list_templates


def main():
    destination = Path("examples/audited")
    destination.mkdir(parents=True, exist_ok=True)
    params = list_templates()[0].to_params()
    for name, p, plane in (
        ("CONNECT_2D.std", params, True),
        ("CONNECT_3D.std", params, False),
        ("CONNECT_2D_user_seismic_uplift.std", replace(params,
            wind_seismic=replace(params.wind_seismic, seismic_ah=0.1, wind_roof_uplift_kn_m2=0.6)), True),
    ):
        result = run_pipeline(p, options=PipelineOptions(export_plane=plane,
            staad_version="STAAD.Pro CONNECT Edition"))
        (destination / name).write_text(result.staad_text, encoding="utf-8")
        print(name, result.analysis_ok, len(result.model.nodes), "joints in building")


if __name__ == "__main__":
    main()
