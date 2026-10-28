"""`WebsiteGenerator`: Rana's implementation of `SiteGeneratorPort`.

    generate(spec) -> {relative path: text}   deterministic, no model, no I/O, no network
    validate(files) -> [problems]             empty list means the site is valid

Plug it into the application with `GENERATOR_IMPL=backend.generator:WebsiteGenerator`.
"""
from typing import Any, Dict, List, Optional

from backend.generator.spec import SITE_TYPES, normalize_spec
from backend.generator.templates import SCRIPT, render_css, render_page, starter_spec
from backend.generator.validator import validate_site


class GenerationError(ValueError):
    """The generator produced a site that fails its own validation (a bug, never user error)."""

    def __init__(self, problems: List[str]):
        self.problems = list(problems)
        super().__init__("generated site is invalid: " + "; ".join(self.problems))


class WebsiteGenerator:
    site_types = SITE_TYPES

    def generate(self, spec: Any) -> Dict[str, str]:
        """Render a whole site. Raises `SpecError` (a ValueError) for an invalid spec."""
        normalized = normalize_spec(spec)
        files: Dict[str, str] = {}
        for page in normalized["pages"]:
            files["%s.html" % page["slug"]] = render_page(normalized, page)
        files["style.css"] = render_css(normalized)
        if normalized["options"]["include_script"]:
            files["script.js"] = SCRIPT
        return files

    def validate(self, files: Any, spec: Optional[Dict[str, Any]] = None) -> List[str]:
        return validate_site(files, spec)

    def build(self, spec: Any) -> Dict[str, str]:
        """generate + validate in one call; raises instead of returning an invalid site."""
        files = self.generate(spec)
        problems = self.validate(files, spec)
        if problems:
            raise GenerationError(problems)
        return files

    @staticmethod
    def starter_spec(site_type: str, title: str) -> Dict[str, Any]:
        return starter_spec(site_type, title)
