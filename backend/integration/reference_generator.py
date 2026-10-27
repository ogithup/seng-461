"""Deterministic static-site generator satisfying `SiteGeneratorPort`.

Spec (a plain dict):
    {"site_type": "blog" | "portfolio" | "landing",
     "title": str,
     "pages": [{"slug": "index", "title": str, "sections": [{"heading": str, "body": str}]}],
     "theme": {"primary": "#rrggbb"}}
`spec_for(site_type, title)` fills in the pages and theme for a type. No model, no
filesystem, no network: the same spec always yields the same files.
"""
import re
from html import escape
from typing import Dict, List

SITE_TYPES = ("blog", "portfolio", "landing")
_COLOR = re.compile(r"^#[0-9a-fA-F]{6}$")
_PAGES = {
    "blog": [
        ("index", "Home", [
            ("Latest posts", "Fresh writing, newest first. Posts will appear here as you publish them."),
            ("Start here", "New to the blog? Read the about page, then pick any post that catches your eye."),
        ]),
        ("about", "About", [
            ("About this blog", "A short note about who writes here and what to expect."),
            ("Get in touch", "Replies and ideas are always welcome."),
        ]),
    ],
    "portfolio": [
        ("index", "Home", [
            ("Hello", "A short introduction and a selection of recent work."),
            ("Featured work", "Three projects that show how I think and build."),
        ]),
        ("projects", "Projects", [
            ("Project one", "What it was, what I did, and what changed because of it."),
            ("Project two", "A second case study with the same structure."),
        ]),
        ("contact", "Contact", [
            ("Say hello", "The best way to reach me is by email. I reply within a few days."),
        ]),
    ],
    "landing": [
        ("index", "Home", [
            ("What it does", "One sentence that explains the product to a stranger."),
            ("Why it matters", "The problem it removes and who benefits."),
            ("Get started", "Sign up today and be running in minutes."),
        ]),
    ],
}
_THEMES = {"blog": "#2b6cb0", "portfolio": "#2d3748", "landing": "#6b46c1"}


def spec_for(site_type: str, title: str) -> Dict:
    if site_type not in SITE_TYPES:
        raise ValueError("unknown site type %r" % (site_type,))
    return {
        "site_type": site_type,
        "title": title,
        "pages": [
            {"slug": slug, "title": name, "sections": [{"heading": h, "body": b} for h, b in sections]}
            for slug, name, sections in _PAGES[site_type]
        ],
        "theme": {"primary": _THEMES[site_type]},
    }


def _check_spec(spec: Dict) -> None:
    if not isinstance(spec, dict) or spec.get("site_type") not in SITE_TYPES:
        raise ValueError("spec.site_type must be one of %s" % ", ".join(SITE_TYPES))
    if not isinstance(spec.get("title"), str) or not spec["title"].strip():
        raise ValueError("spec.title must be a non-empty string")
    pages = spec.get("pages")
    if not isinstance(pages, list) or not pages:
        raise ValueError("spec.pages must be a non-empty list")
    slugs = [p.get("slug") if isinstance(p, dict) else None for p in pages]
    for slug in slugs:
        if not isinstance(slug, str) or not re.fullmatch(r"[a-z0-9-]{1,40}", slug):
            raise ValueError("page slug %r must be 1-40 chars of a-z, 0-9, '-'" % (slug,))
    if "index" not in slugs:
        raise ValueError("spec.pages must include an 'index' page")
    if len(set(slugs)) != len(slugs):
        raise ValueError("page slugs must be unique")
    color = (spec.get("theme") or {}).get("primary", "")
    if not isinstance(color, str) or not _COLOR.match(color):
        raise ValueError("spec.theme.primary must be a #rrggbb colour")


class ReferenceSiteGenerator:
    def generate(self, spec: Dict) -> Dict[str, str]:
        _check_spec(spec)
        files = {"style.css": _css(spec["theme"]["primary"]), "script.js": _JS}
        for page in spec["pages"]:
            files["%s.html" % page["slug"]] = _page(spec, page)
        return files

    def validate(self, files: Dict[str, str]) -> List[str]:
        problems: List[str] = []
        for required in ("index.html", "style.css"):
            if required not in files:
                problems.append("missing required file %s" % required)
        for path, content in files.items():
            if not isinstance(content, str) or not content.strip():
                problems.append("%s is empty" % path)
        for path, content in files.items():
            if not path.endswith(".html") or not isinstance(content, str):
                continue
            if "<nav" not in content:
                problems.append("%s has no navigation" % path)
            if 'name="viewport"' not in content:
                problems.append("%s is not responsive (no viewport meta)" % path)
            for ref in re.findall(r'(?:href|src)="([^"#]+)"', content):
                if "://" in ref or ref.startswith(("mailto:", "/")):
                    continue
                if ref not in files:
                    problems.append("%s references missing file %s" % (path, ref))
        return problems


def _page(spec: Dict, page: Dict) -> str:
    title = escape(spec["title"])
    links = "".join(
        '<a href="%s.html"%s>%s</a>'
        % (p["slug"], ' aria-current="page"' if p["slug"] == page["slug"] else "", escape(p["title"]))
        for p in spec["pages"]
    )
    sections = "\n".join(
        "    <section>\n      <h2>%s</h2>\n      <p>%s</p>\n    </section>"
        % (escape(s["heading"]), escape(s["body"]))
        for s in page["sections"]
    )
    heading = title if page["slug"] == "index" else escape(page["title"])
    return """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>%(page)s | %(title)s</title>
  <link rel="stylesheet" href="style.css">
</head>
<body class="%(kind)s">
  <header>
    <a class="brand" href="index.html">%(title)s</a>
    <nav>%(links)s</nav>
  </header>
  <main>
    <h1>%(heading)s</h1>
%(sections)s
  </main>
  <footer>&copy; %(title)s</footer>
  <script src="script.js"></script>
</body>
</html>
""" % {
        "page": escape(page["title"]),
        "title": title,
        "kind": spec["site_type"],
        "links": links,
        "heading": heading,
        "sections": sections,
    }


def _css(primary: str) -> str:
    return """:root { --primary: %s; --text: #1a202c; --bg: #ffffff; --muted: #edf2f7; }
* { box-sizing: border-box; }
body { margin: 0; font-family: system-ui, sans-serif; color: var(--text); background: var(--bg); line-height: 1.6; }
header { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 8px; padding: 16px 24px; background: var(--primary); }
header a { color: #fff; text-decoration: none; }
.brand { font-weight: 700; font-size: 1.2rem; }
nav { display: flex; flex-wrap: wrap; gap: 16px; }
nav a[aria-current="page"] { text-decoration: underline; }
main { max-width: 720px; margin: 0 auto; padding: 24px 16px; }
section { margin: 24px 0; padding: 16px; background: var(--muted); border-radius: 8px; }
footer { padding: 16px; text-align: center; color: #4a5568; }
@media (max-width: 480px) { header { flex-direction: column; align-items: flex-start; } main { padding: 16px 12px; } }
""" % primary


_JS = """document.querySelectorAll('nav a').forEach(function (link) {
  if (link.getAttribute('href') === location.pathname.split('/').pop()) {
    link.setAttribute('aria-current', 'page');
  }
});
"""
