"""Website generation & templates (Sprints 3-4, owner: Rana).

Turns a validated website specification into a self-contained static site. Depends only on
the Python standard library: no frontend, no AI model, no filesystem access, no network.
"""
from backend.generator.generator import GenerationError, WebsiteGenerator
from backend.generator.spec import SITE_TYPES, SpecError, normalize_spec
from backend.generator.templates import DEFAULT_PAGES, available_pages, starter_spec
from backend.generator.validator import validate_site

__all__ = [
    "DEFAULT_PAGES",
    "GenerationError",
    "SITE_TYPES",
    "SpecError",
    "WebsiteGenerator",
    "available_pages",
    "normalize_spec",
    "starter_spec",
    "validate_site",
]
