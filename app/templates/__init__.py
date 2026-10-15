"""Pre-built building templates."""

from app.templates.catalog import (
    BuildingTemplate,
    get_template,
    list_templates,
    templates_by_id,
)

__all__ = [
    "BuildingTemplate",
    "get_template",
    "list_templates",
    "templates_by_id",
]
