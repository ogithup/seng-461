"""Deterministic request interpreter for the approved website spec."""
import re

from backend.generator import normalize_spec, starter_spec

from .planner import _planning_info


class UnsupportedRequest(ValueError):
    code = "unsupported_request"
    user_message = "Online shops are not supported yet. Try a blog, portfolio or landing page."


_SHOP = re.compile(r"\b(?:online\s+shops?|shops?|stores?|e[ -]?commerce|shopping\s+cart|checkout)\b", re.IGNORECASE)
_OTHER_UNSUPPORTED = re.compile(r"\b(?:mobile app|native app|web app|social network|booking system|payment processing)\b", re.IGNORECASE)
_FIELD = re.compile(r"^(pages?|section|primary|accent|font)\s*:\s*(.*)$", re.IGNORECASE)


def default_spec(site_type: str, title: str) -> dict:
    """Use the generator starter while preserving the Sprint 3 default blog files."""
    spec = starter_spec(site_type, title)
    if site_type == "blog":
        spec["pages"] = [page for page in spec["pages"] if page["slug"] != "archive"]
    return normalize_spec(spec)


def interpret(message: str) -> dict:
    """Interpret a request and optional semicolon-separated, labelled fields."""
    if not isinstance(message, str):
        raise TypeError("message must be a string")
    if _SHOP.search(message):
        raise UnsupportedRequest(UnsupportedRequest.user_message)
    if _OTHER_UNSUPPORTED.search(message):
        exc = UnsupportedRequest("Only blogs, portfolios and landing pages are supported yet.")
        exc.user_message = str(exc)
        raise exc
    parts = [part.strip() for part in message.split(";")]
    info = _planning_info(parts[0])
    spec = default_spec(info.site_type, info.title)
    for part in parts[1:]:
        match = _FIELD.fullmatch(part)
        if not match:
            raise ValueError("unknown request field: %s" % part)
        field, value = match.group(1).lower(), match.group(2).strip()
        if field in ("page", "pages"):
            for name in value.split(","):
                name = name.strip()
                slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
                if not name or not slug:
                    raise ValueError("page name must not be empty")
                if slug not in {page["slug"] for page in spec["pages"]}:
                    spec["pages"].append({"slug": slug, "title": name, "sections": [
                        {"heading": name, "body": "Content coming soon."}
                    ]})
        elif field == "section":
            if not value:
                raise ValueError("section heading must not be empty")
            spec["pages"][0]["sections"].append({"heading": value, "body": "Content coming soon."})
        else:
            spec["theme"][field] = value.lower()
    return normalize_spec(spec)
