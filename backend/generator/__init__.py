"""Website generation & templates (Sprint 3, owner: Rana).

Turns a validated website specification into a self-contained static site. Depends only on
the Python standard library: no frontend, no AI model, no filesystem access, no network.
"""
from backend.generator.generator import GenerationError, WebsiteGenerator
from backend.generator.spec import SITE_TYPES, SpecError, normalize_spec
from backend.generator.templates import starter_spec
from backend.generator.validator import validate_site

__all__ = [
    "GenerationError",
    "SITE_TYPES",
    "SpecError",
    "WebsiteGenerator",
    "normalize_spec",
    "starter_spec",
    "validate_site",
]
