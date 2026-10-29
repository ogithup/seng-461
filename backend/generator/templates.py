"""Templates for blog, portfolio and landing-page sites.

Everything here is a pure function of a *normalized* spec (see `spec.normalize_spec`): no
clock, no randomness, no I/O. All user text goes through `html.escape`.
"""
from html import escape
from typing import Any, Dict, List

# ---------------------------------------------------------------------------------------
# Starter specs: a complete, meaningful site per type that callers can edit or extend.
# ---------------------------------------------------------------------------------------

_STARTERS: Dict[str, Dict[str, Any]] = {
    "blog": {
        "tagline": "Notes, ideas and stories, newest first.",
        "pages": [
            {"slug": "index", "title": "Home", "sections": [
                {"kind": "posts", "heading": "Latest posts", "body": "Fresh writing, newest first.",
                 "items": [
                     {"title": "Why I started writing", "meta": "Post 3",
                      "body": "What pushed me to start this blog and what I hope to learn from it.",
                      "link": "about.html"},
                     {"title": "Five lessons from my first project", "meta": "Post 2",
                      "body": "Small mistakes, quick fixes and the habits that stuck afterwards."},
                     {"title": "Hello, world", "meta": "Post 1",
                      "body": "A first post to say hello and explain what this blog will cover."},
                 ]},
                {"kind": "text", "heading": "Start here",
                 "body": "New to the blog? Read the about page, then pick any post that catches your eye.",
                 "cta": {"label": "About this blog", "href": "about.html"}},
            ]},
            {"slug": "archive", "title": "Archive", "sections": [
                {"kind": "posts", "heading": "All posts", "body": "Every post in one place.",
                 "items": [
                     {"title": "Why I started writing", "meta": "Post 3"},
                     {"title": "Five lessons from my first project", "meta": "Post 2"},
                     {"title": "Hello, world", "meta": "Post 1"},
                 ]},
            ]},
            {"slug": "about", "title": "About", "sections": [
                {"heading": "About this blog",
                 "body": "A short note about who writes here and what to expect.\n\n"
                         "Posts appear when there is something worth sharing, usually every week or two."},
                {"heading": "Get in touch", "body": "Replies and ideas are always welcome."},
            ]},
        ],
    },
    "portfolio": {
        "tagline": "Designer and developer building useful things for the web.",
        "pages": [
            {"slug": "index", "title": "Home", "sections": [
                {"kind": "hero", "heading": "Hello, I build things for the web.",
                 "body": "A short introduction and a selection of recent work.",
                 "cta": {"label": "See my projects", "href": "projects.html"}},
                {"kind": "projects", "heading": "Featured work", "items": [
                    {"title": "Project one", "meta": "Web app",
                     "body": "What it was, what I did, and what changed because of it.",
                     "link": "projects.html#selected-projects"},
                    {"title": "Project two", "meta": "Design system",
                     "body": "Reusable components that made a team ship faster."},
                    {"title": "Project three", "meta": "Open source",
                     "body": "A small library used by other developers."},
                ]},
            ]},
            {"slug": "projects", "title": "Projects", "sections": [
                {"kind": "projects", "heading": "Selected projects",
                 "body": "Each case study follows the same structure: problem, approach, result.",
                 "items": [
                     {"title": "Project one", "meta": "Web app", "body": "Problem, approach and result."},
                     {"title": "Project two", "meta": "Design system", "body": "Problem, approach and result."},
                     {"title": "Project three", "meta": "Open source", "body": "Problem, approach and result."},
                 ]},
                {"kind": "text", "heading": "Skills",
                 "body": "HTML, CSS, JavaScript, Python, accessibility and responsive design."},
            ]},
            {"slug": "contact", "title": "Contact", "sections": [
                {"kind": "cta", "heading": "Say hello",
                 "body": "The best way to reach me is by email. I reply within a few days.",
                 "cta": {"label": "Send an email", "href": "mailto:hello@example.com"}},
            ]},
        ],
    },
    "landing": {
        "tagline": "The simplest way to get the job done.",
        "pages": [
            {"slug": "index", "title": "Home", "sections": [
                {"kind": "hero", "heading": "What it does",
                 "body": "One sentence that explains the product to a stranger.",
                 "cta": {"label": "Get started", "href": "#get-started"}},
                {"kind": "features", "heading": "Why it matters", "items": [
                    {"title": "Fast", "body": "Set up in minutes, not days."},
                    {"title": "Simple", "body": "No manual, no training, no surprises."},
                    {"title": "Reliable", "body": "Works the same way every single time."},
                ]},
                {"kind": "cta", "heading": "Get started",
                 "body": "Sign up today and be running in minutes.",
                 "cta": {"label": "Contact us", "href": "mailto:hello@example.com"}},
            ]},
        ],
    },
}


def starter_spec(site_type: str, title: str) -> Dict[str, Any]:
    """A complete example spec for `site_type` (a fresh copy every call)."""
    import copy

    if site_type not in _STARTERS:
        raise ValueError("unknown site type %r" % (site_type,))
    spec = copy.deepcopy(_STARTERS[site_type])
    spec.update({"site_type": site_type, "title": title})
    return spec


# ---------------------------------------------------------------------------------------
# HTML
# ---------------------------------------------------------------------------------------

def _paragraphs(text: str, css_class: str = "") -> str:
    attr = ' class="%s"' % css_class if css_class else ""
    return "".join(
        "<p%s>%s</p>" % (attr, escape(chunk.strip()))
        for chunk in text.split("\n\n")
        if chunk.strip()
    )


def _attr(value: str) -> str:
    return escape(value, quote=True)


def _button(cta: Dict[str, str], extra: str = "") -> str:
    if not cta:
        return ""
    return '<p class="actions"><a class="button%s" href="%s">%s</a></p>' % (
        extra, _attr(cta["href"]), escape(cta["label"])
    )


def _item(item: Dict[str, Any], tag: str) -> str:
    title = escape(item["title"])
    if item["link"]:
        title = '<a href="%s">%s</a>' % (_attr(item["link"]), title)
    meta = '<p class="meta">%s</p>' % escape(item["meta"]) if item["meta"] else ""
    return '<%s class="card"><h3>%s</h3>%s%s</%s>' % (tag, title, meta, _paragraphs(item["body"]), tag)


def _section(section: Dict[str, Any], page_h1: str) -> str:
    kind = section["kind"]
    anchor = ' id="%s"' % section["id"] if section["id"] else ""
    if kind == "hero":
        return (
            '<section class="hero"%s>\n<h1>%s</h1>\n<p class="lead">%s</p>\n%s%s\n</section>'
            % (anchor, page_h1, escape(section["heading"]), _paragraphs(section["body"]),
               _button(section["cta"]))
        )
    if kind == "cta":
        return (
            '<section class="cta-band"%s>\n<h2>%s</h2>\n%s%s\n</section>'
            % (anchor, escape(section["heading"]), _paragraphs(section["body"]),
               _button(section["cta"], " button-light"))
        )
    items = ""
    if section["items"]:
        if kind == "posts":
            items = '<div class="post-list">%s</div>' % "".join(_item(i, "article") for i in section["items"])
        elif kind == "text":
            items = '<ul class="item-list">%s</ul>' % "".join(_item(i, "li") for i in section["items"])
        else:
            items = '<div class="grid grid-%s">%s</div>' % (
                kind, "".join(_item(i, "article") for i in section["items"])
            )
    return '<section class="block block-%s"%s>\n<h2>%s</h2>\n%s%s%s\n</section>' % (
        kind, anchor, escape(section["heading"]), _paragraphs(section["body"]), items,
        _button(section["cta"]),
    )


def render_page(spec: Dict[str, Any], page: Dict[str, Any]) -> str:
    site_title = escape(spec["title"])
    is_index = page["slug"] == "index"
    page_h1 = site_title if is_index else escape(page["title"])

    links = "\n".join(
        '      <li><a href="%s.html"%s>%s</a></li>'
        % (p["slug"], ' aria-current="page"' if p["slug"] == page["slug"] else "", escape(p["title"]))
        for p in spec["pages"]
    )
    sections = page["sections"]
    if sections and sections[0]["kind"] == "hero":
        intro = ""
    else:
        tagline = (
            '\n<p class="lead">%s</p>' % escape(spec["tagline"]) if is_index and spec["tagline"] else ""
        )
        intro = '<div class="page-intro">\n<h1>%s</h1>%s\n</div>\n' % (page_h1, tagline)
    body = "\n".join(_section(s, page_h1) for s in sections)
    script = '\n  <script src="script.js" defer></script>' if spec["options"]["include_script"] else ""
    toggle = (
        '\n    <button class="nav-toggle" type="button" aria-expanded="false" '
        'aria-controls="site-nav" hidden>Menu</button>'
        if spec["options"]["include_script"] else ""
    )
    footer = escape(spec["footer"]) if spec["footer"] else "&copy; %s" % site_title
    description = escape(spec["tagline"] or spec["title"], quote=True)
    page_title = site_title if is_index else "%s | %s" % (escape(page["title"]), site_title)

    return """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="description" content="%(description)s">
  <title>%(page_title)s</title>
  <link rel="stylesheet" href="style.css">%(script)s
</head>
<body class="site-%(kind)s page-%(slug)s">
  <a class="skip-link" href="#content">Skip to content</a>
  <header class="site-header">
    <a class="brand" href="index.html">%(site_title)s</a>%(toggle)s
    <nav id="site-nav" class="site-nav" aria-label="Main">
      <ul>
%(links)s
      </ul>
    </nav>
  </header>
  <main id="content">
%(intro)s%(body)s
  </main>
  <footer class="site-footer">
    <p>%(footer)s</p>
  </footer>
</body>
</html>
""" % {
        "description": description,
        "page_title": page_title,
        "script": script,
        "kind": spec["site_type"],
        "slug": page["slug"],
        "site_title": site_title,
        "toggle": toggle,
        "links": links,
        "intro": intro,
        "body": body,
        "footer": footer,
    }


# ---------------------------------------------------------------------------------------
# CSS
# ---------------------------------------------------------------------------------------

_FONTS = {
    "sans": 'system-ui, -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif',
    "serif": 'Georgia, "Times New Roman", Times, serif',
    "mono": 'ui-monospace, SFMono-Regular, Menlo, Consolas, monospace',
}


def _on_color(hex_color: str) -> str:
    """Readable text colour (white or near-black) on top of `hex_color` (WCAG luminance)."""
    channels = []
    for i in (1, 3, 5):
        c = int(hex_color[i:i + 2], 16) / 255
        channels.append(c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4)
    luminance = 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2]
    return "#ffffff" if luminance < 0.4 else "#1a202c"


_BASE_CSS = """*, *::before, *::after { box-sizing: border-box; }
html { -webkit-text-size-adjust: 100%; }
body { margin: 0; font-family: var(--font); color: var(--text); background: var(--bg); line-height: 1.6; }
img { max-width: 100%; height: auto; }
a { color: var(--primary); }
a:focus-visible, button:focus-visible { outline: 3px solid var(--accent); outline-offset: 2px; }
.skip-link { position: absolute; left: -9999px; top: 0; padding: 8px 12px; background: var(--bg); }
.skip-link:focus { left: 8px; z-index: 10; }

.site-header { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between;
  gap: 8px 24px; padding: 16px clamp(16px, 4vw, 40px); background: var(--primary); color: var(--on-primary); }
.site-header a { color: var(--on-primary); text-decoration: none; }
.brand { font-weight: 700; font-size: 1.25rem; }
.site-nav ul { display: flex; flex-wrap: wrap; gap: 4px 20px; margin: 0; padding: 0; list-style: none; }
.site-nav a { display: inline-block; padding: 4px 0; border-bottom: 2px solid transparent; }
.site-nav a:hover, .site-nav a[aria-current="page"] { border-bottom-color: var(--accent); }
.nav-toggle { font: inherit; padding: 6px 12px; color: var(--on-primary); background: transparent;
  border: 1px solid currentColor; border-radius: 6px; cursor: pointer; }
.nav-toggle[hidden] { display: none; }

main { max-width: var(--width); margin: 0 auto; padding: 32px clamp(16px, 4vw, 40px) 48px; }
.page-intro { margin-bottom: 32px; }
h1 { font-size: clamp(2rem, 5vw, 2.75rem); line-height: 1.15; margin: 0 0 12px; }
h2 { font-size: 1.5rem; margin: 0 0 12px; }
h3 { font-size: 1.15rem; margin: 0 0 6px; }
.lead { font-size: 1.15rem; color: var(--muted-text); margin: 0 0 12px; }
.meta { font-size: 0.875rem; color: var(--muted-text); margin: 0 0 6px; }

.block { margin: 0 0 40px; }
.hero { margin: 0 0 48px; padding: clamp(32px, 6vw, 64px) clamp(20px, 4vw, 48px); border-radius: 16px;
  background: var(--surface); }
.hero .lead { font-size: 1.3rem; color: var(--text); font-weight: 600; }
.cta-band { margin: 0 0 40px; padding: 32px clamp(20px, 4vw, 40px); border-radius: 16px;
  background: var(--primary); color: var(--on-primary); text-align: center; }
.cta-band a:not(.button) { color: var(--on-primary); }

.grid { display: grid; gap: 20px; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); margin-top: 16px; }
.card { padding: 20px; border-radius: 12px; background: var(--surface); border: 1px solid var(--border); }
.card p:last-child { margin-bottom: 0; }
.post-list { display: flex; flex-direction: column; gap: 16px; margin-top: 16px; }
.item-list { list-style: none; padding: 0; display: grid; gap: 12px; }

.actions { margin: 20px 0 0; }
.button { display: inline-block; padding: 12px 22px; border-radius: 999px; font-weight: 600;
  text-decoration: none; background: var(--accent); color: var(--on-accent); }
.button:hover { filter: brightness(1.08); }
.button-light { background: var(--on-primary); color: var(--primary); }

.site-footer { padding: 24px 16px; text-align: center; color: var(--muted-text); border-top: 1px solid var(--border); }

@media (max-width: 640px) {
  .site-header { align-items: flex-start; }
  .js .site-nav { flex-basis: 100%; display: none; }
  .js .site-nav.open { display: block; }
  .site-nav ul { flex-direction: column; gap: 4px; }
  .grid { grid-template-columns: 1fr; }
  .hero, .cta-band { border-radius: 12px; }
}
@media (prefers-reduced-motion: reduce) { * { scroll-behavior: auto !important; transition: none !important; } }
"""

_TYPE_CSS = {
    "blog": """
/* blog */
.site-blog .post-list .card { background: transparent; border: 0; border-bottom: 1px solid var(--border);
  border-radius: 0; padding: 0 0 16px; }
.site-blog .post-list h3 { font-size: 1.35rem; }
.site-blog .post-list h3 a { text-decoration: none; }
.site-blog .post-list h3 a:hover { text-decoration: underline; }
""",
    "portfolio": """
/* portfolio */
.site-portfolio .hero { background: linear-gradient(135deg, var(--surface), var(--bg)); }
.site-portfolio .grid-projects .card { transition: transform 0.15s ease, box-shadow 0.15s ease; }
.site-portfolio .grid-projects .card:hover { transform: translateY(-3px); box-shadow: 0 8px 24px rgba(0, 0, 0, 0.08); }
.site-portfolio .meta { text-transform: uppercase; letter-spacing: 0.06em; color: var(--accent); }
""",
    "landing": """
/* landing */
.site-landing .hero { text-align: center; background: var(--primary); color: var(--on-primary); }
.site-landing .hero .lead { color: var(--on-primary); }
.site-landing .grid-features { text-align: center; }
.site-landing .grid-features .card { border-top: 4px solid var(--accent); }
""",
}

_WIDTHS = {"blog": "760px", "portfolio": "1040px", "landing": "1080px"}


def render_css(spec: Dict[str, Any]) -> str:
    theme = spec["theme"]
    tokens = """:root {
  --primary: %(primary)s;
  --on-primary: %(on_primary)s;
  --accent: %(accent)s;
  --on-accent: %(on_accent)s;
  --text: #1a202c;
  --muted-text: #4a5568;
  --bg: #ffffff;
  --surface: #f7fafc;
  --border: #e2e8f0;
  --font: %(font)s;
  --width: %(width)s;
}
""" % {
        "primary": theme["primary"],
        "on_primary": _on_color(theme["primary"]),
        "accent": theme["accent"],
        "on_accent": _on_color(theme["accent"]),
        "font": _FONTS[theme["font"]],
        "width": _WIDTHS[spec["site_type"]],
    }
    return tokens + _BASE_CSS + _TYPE_CSS[spec["site_type"]]


# ---------------------------------------------------------------------------------------
# JavaScript (optional): progressive enhancement only, every page works without it.
# ---------------------------------------------------------------------------------------

SCRIPT = """(function () {
  'use strict';
  var root = document.documentElement;
  root.classList.add('js');

  var toggle = document.querySelector('.nav-toggle');
  var nav = document.getElementById('site-nav');
  if (toggle && nav) {
    toggle.hidden = false;
    toggle.addEventListener('click', function () {
      var open = nav.classList.toggle('open');
      toggle.setAttribute('aria-expanded', open ? 'true' : 'false');
    });
    var wide = window.matchMedia('(min-width: 641px)');
    var sync = function () { toggle.hidden = wide.matches; };
    sync();
    if (wide.addEventListener) { wide.addEventListener('change', sync); }
  }
})();
"""


def page_filename(page: Dict[str, Any]) -> str:
    return "%s.html" % page["slug"]


def expected_files(spec: Dict[str, Any]) -> List[str]:
    files = [page_filename(p) for p in spec["pages"]] + ["style.css"]
    if spec["options"]["include_script"]:
        files.append("script.js")
    return files
