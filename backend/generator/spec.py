"""Website specification: the only input the generator accepts.

A spec is a plain dict so it can travel as JSON between the agent, the API and the tests.
`normalize_spec` checks it and returns a new, fully filled-in copy; everything after that
works on the normalized form only.

    {
      "site_type": "blog" | "portfolio" | "landing",       # required
      "title": "Travel Notes",                              # required, 1-80 chars
      "tagline": "Short subtitle",                          # optional
      "pages": [                                            # required, 1-12, must include "index"
        {
          "slug": "index",                                  # a-z, 0-9, "-" (file = <slug>.html)
          "title": "Home",                                  # nav label
          "sections": [                                     # 1-20 per page
            {
              "heading": "Latest posts",                    # required
              "body": "Intro text",                         # optional if items are given
              "kind": "text|hero|cards|posts|projects|features|cta",   # optional
              "id": "latest",                               # optional anchor (default: from heading)
              "items": [{"title": "...", "body": "...", "meta": "...", "link": "about.html"}],
              "cta": {"label": "Read more", "href": "about.html"}
            }
          ]
        }
      ],
      "theme": {"primary": "#2b6cb0", "accent": "#ed8936", "font": "sans|serif|mono"},
      "footer": "Optional footer text",
      "options": {"include_script": true}
    }

This is a superset of the stand-in `reference_generator` spec, so `spec_for()` output (and
anything the agent built for it) is accepted unchanged.
"""
import re
from typing import Any, Dict, List, Optional

SITE_TYPES = ("blog", "portfolio", "landing")
SECTION_KINDS = ("text", "hero", "cards", "posts", "projects", "features", "cta")
FONTS = ("sans", "serif", "mono")

MAX_PAGES = 12
MAX_SECTIONS = 20
MAX_ITEMS = 24
MAX_TITLE = 80
MAX_TEXT = 4000

_SLUG = re.compile(r"^[a-z0-9-]{1,40}$")
_COLOR = re.compile(r"^#[0-9a-fA-F]{6}$")
_ANCHOR = re.compile(r"^[a-z][a-z0-9-]{0,59}$")
_EXTERNAL = re.compile(r"^(https?://[^\s\"'<>]+|mailto:[^\s\"'<>]+)$", re.IGNORECASE)
_INTERNAL = re.compile(r"^(?P<page>[a-z0-9-]{1,40})\.html(?:#(?P<anchor>[a-z][a-z0-9-]{0,59}))?$")
_LOCAL_ANCHOR = re.compile(r"^#(?P<anchor>[a-z][a-z0-9-]{0,59})$")

DEFAULT_THEMES = {
    "blog": {"primary": "#2b6cb0", "accent": "#dd6b20", "font": "serif"},
    "portfolio": {"primary": "#2d3748", "accent": "#38b2ac", "font": "sans"},
    "landing": {"primary": "#6b46c1", "accent": "#ed8936", "font": "sans"},
}


class SpecError(ValueError):
    """Raised for an invalid spec. `problems` lists every issue found, not just the first."""

    def __init__(self, problems: List[str]):
        self.problems = list(problems)
        super().__init__("invalid website spec: " + "; ".join(self.problems))


def slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    slug = slug[:60].strip("-")
    if not slug or not slug[0].isalpha():
        slug = "s-" + slug if slug else "section"
    return slug


def _text(value: Any, where: str, problems: List[str], required: bool, limit: int = MAX_TEXT) -> str:
    if value is None:
        if required:
            problems.append("%s is required" % where)
        return ""
    if not isinstance(value, str):
        problems.append("%s must be a string" % where)
        return ""
    value = value.strip()
    if required and not value:
        problems.append("%s must not be empty" % where)
    if len(value) > limit:
        problems.append("%s is longer than %d characters" % (where, limit))
    return value


def _link(value: Any, where: str, problems: List[str]) -> Optional[str]:
    """Accept only links we can prove are safe; internal targets are checked later."""
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        problems.append("%s must be a non-empty string" % where)
        return None
    value = value.strip()
    if _EXTERNAL.match(value) or _INTERNAL.match(value) or _LOCAL_ANCHOR.match(value):
        return value
    problems.append(
        "%s %r must be <page>.html[#anchor], #anchor, http(s):// or mailto:" % (where, value)
    )
    return None


def _items(raw: Any, where: str, problems: List[str]) -> List[Dict[str, Any]]:
    if raw is None:
        return []
    if not isinstance(raw, list):
        problems.append("%s must be a list" % where)
        return []
    if len(raw) > MAX_ITEMS:
        problems.append("%s has more than %d items" % (where, MAX_ITEMS))
    items = []
    for i, item in enumerate(raw[:MAX_ITEMS]):
        at = "%s[%d]" % (where, i)
        if not isinstance(item, dict):
            problems.append("%s must be an object" % at)
            continue
        items.append({
            "title": _text(item.get("title"), at + ".title", problems, True, MAX_TITLE * 2),
            "body": _text(item.get("body"), at + ".body", problems, False),
            "meta": _text(item.get("meta"), at + ".meta", problems, False, MAX_TITLE),
            "link": _link(item.get("link"), at + ".link", problems),
        })
    return items


def _section(raw: Any, where: str, problems: List[str], default_kind: str) -> Optional[Dict[str, Any]]:
    if not isinstance(raw, dict):
        problems.append("%s must be an object" % where)
        return None
    kind = raw.get("kind", default_kind)
    if kind not in SECTION_KINDS:
        problems.append("%s.kind must be one of %s" % (where, ", ".join(SECTION_KINDS)))
        kind = "text"
    heading = _text(raw.get("heading"), where + ".heading", problems, True, MAX_TITLE * 2)
    items = _items(raw.get("items"), where + ".items", problems)
    body = _text(raw.get("body"), where + ".body", problems, not items)
    anchor = raw.get("id")
    if anchor is None:
        anchor = slugify(heading) if heading else None
    elif not isinstance(anchor, str) or not _ANCHOR.match(anchor):
        problems.append("%s.id must start with a letter and use a-z, 0-9, '-'" % where)
        anchor = None
    cta = raw.get("cta")
    if cta is not None:
        if not isinstance(cta, dict):
            problems.append("%s.cta must be an object" % where)
            cta = None
        else:
            cta = {
                "label": _text(cta.get("label"), where + ".cta.label", problems, True, MAX_TITLE),
                "href": _link(cta.get("href"), where + ".cta.href", problems),
            }
            if cta["href"] is None:
                problems.append("%s.cta.href is required" % where)
    return {"kind": kind, "heading": heading, "body": body, "id": anchor, "items": items, "cta": cta}


def _theme(raw: Any, site_type: str, problems: List[str]) -> Dict[str, str]:
    theme = dict(DEFAULT_THEMES.get(site_type, DEFAULT_THEMES["landing"]))
    if raw is None:
        return theme
    if not isinstance(raw, dict):
        problems.append("spec.theme must be an object")
        return theme
    for key in ("primary", "accent"):
        if key in raw:
            if isinstance(raw[key], str) and _COLOR.match(raw[key]):
                theme[key] = raw[key].lower()
            else:
                problems.append("spec.theme.%s must be a #rrggbb colour" % key)
    if "font" in raw:
        if raw["font"] in FONTS:
            theme["font"] = raw["font"]
        else:
            problems.append("spec.theme.font must be one of %s" % ", ".join(FONTS))
    return theme


def _default_kind(site_type: str, slug: str, index: int) -> str:
    if slug == "index" and index == 0 and site_type in ("portfolio", "landing"):
        return "hero"
    return "text"


def _check_links(pages: List[Dict[str, Any]], problems: List[str]) -> None:
    anchors = {p["slug"]: {s["id"] for s in p["sections"] if s["id"]} for p in pages}

    def check(link: Optional[str], page: str, where: str) -> None:
        if not link:
            return
        local = _LOCAL_ANCHOR.match(link)
        if local:
            if local.group("anchor") not in anchors[page]:
                problems.append("%s points at missing anchor %s" % (where, link))
            return
        internal = _INTERNAL.match(link)
        if internal:
            target = internal.group("page")
            if target not in anchors:
                problems.append("%s points at missing page %s" % (where, link))
            elif internal.group("anchor") and internal.group("anchor") not in anchors[target]:
                problems.append("%s points at missing anchor %s" % (where, link))

    for page in pages:
        seen = set()
        for s_i, section in enumerate(page["sections"]):
            where = "page %s section %d" % (page["slug"], s_i)
            if section["id"] in seen:
                problems.append("%s: duplicate section id %r" % (where, section["id"]))
            seen.add(section["id"])
            if section["cta"]:
                check(section["cta"]["href"], page["slug"], where + " cta")
            for i_i, item in enumerate(section["items"]):
                check(item["link"], page["slug"], "%s item %d" % (where, i_i))


def normalize_spec(spec: Any) -> Dict[str, Any]:
    """Validate `spec` and return a normalized copy. Raises SpecError listing all problems."""
    if not isinstance(spec, dict):
        raise SpecError(["spec must be an object"])
    problems: List[str] = []

    site_type = spec.get("site_type")
    if site_type not in SITE_TYPES:
        problems.append("spec.site_type must be one of %s" % ", ".join(SITE_TYPES))
    title = _text(spec.get("title"), "spec.title", problems, True, MAX_TITLE)
    tagline = _text(spec.get("tagline"), "spec.tagline", problems, False, MAX_TITLE * 2)
    footer = _text(spec.get("footer"), "spec.footer", problems, False, MAX_TITLE * 2)

    raw_pages = spec.get("pages")
    pages: List[Dict[str, Any]] = []
    if not isinstance(raw_pages, list) or not raw_pages:
        problems.append("spec.pages must be a non-empty list")
        raw_pages = []
    elif len(raw_pages) > MAX_PAGES:
        problems.append("spec.pages has more than %d pages" % MAX_PAGES)
    for p_i, raw in enumerate(raw_pages[:MAX_PAGES]):
        where = "spec.pages[%d]" % p_i
        if not isinstance(raw, dict):
            problems.append("%s must be an object" % where)
            continue
        slug = raw.get("slug")
        if not isinstance(slug, str) or not _SLUG.match(slug):
            problems.append("%s.slug %r must be 1-40 chars of a-z, 0-9, '-'" % (where, slug))
            continue
        name = _text(raw.get("title"), where + ".title", problems, True, MAX_TITLE)
        raw_sections = raw.get("sections")
        if not isinstance(raw_sections, list) or not raw_sections:
            problems.append("%s.sections must be a non-empty list" % where)
            raw_sections = []
        elif len(raw_sections) > MAX_SECTIONS:
            problems.append("%s.sections has more than %d sections" % (where, MAX_SECTIONS))
        sections = []
        for s_i, section in enumerate(raw_sections[:MAX_SECTIONS]):
            parsed = _section(
                section,
                "%s.sections[%d]" % (where, s_i),
                problems,
                _default_kind(site_type, slug, s_i),
            )
            if parsed:
                sections.append(parsed)
        pages.append({"slug": slug, "title": name, "sections": sections})

    slugs = [p["slug"] for p in pages]
    if raw_pages and "index" not in slugs:
        problems.append("spec.pages must include an 'index' page")
    duplicates = sorted({s for s in slugs if slugs.count(s) > 1})
    if duplicates:
        problems.append("page slugs must be unique (duplicated: %s)" % ", ".join(duplicates))
    else:
        _check_links(pages, problems)

    theme = _theme(spec.get("theme"), site_type, problems)

    options = spec.get("options") or {}
    if not isinstance(options, dict):
        problems.append("spec.options must be an object")
        options = {}
    include_script = options.get("include_script", True)
    if not isinstance(include_script, bool):
        problems.append("spec.options.include_script must be true or false")
        include_script = True

    if problems:
        raise SpecError(problems)

    # index first, the rest in the order given: this is also the navigation order.
    pages.sort(key=lambda p: p["slug"] != "index")
    return {
        "site_type": site_type,
        "title": title,
        "tagline": tagline,
        "footer": footer,
        "pages": pages,
        "theme": theme,
        "options": {"include_script": include_script},
    }
