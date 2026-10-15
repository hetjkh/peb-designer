"""Database package — sections, materials, plate catalog."""

from app.database.materials import MATERIALS, Material, get_material, list_materials
from app.database.plate_catalog import (
    PlateCatalog,
    get_plate_catalog,
    load_plate_catalog,
    save_plate_catalog,
    set_plate_catalog,
)
from app.database.sections import SectionDatabase, SteelSection, default_section_for_type

__all__ = [
    "MATERIALS",
    "Material",
    "get_material",
    "list_materials",
    "PlateCatalog",
    "get_plate_catalog",
    "load_plate_catalog",
    "save_plate_catalog",
    "set_plate_catalog",
    "SectionDatabase",
    "SteelSection",
    "default_section_for_type",
]
