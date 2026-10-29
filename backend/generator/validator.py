"""Output validation for a generated static site.

`validate_site(files)` returns a list of human-readable problems (empty = valid). It checks:

- required files: `index.html` and `style.css`;
- safe relative paths with allowed suffixes (same rules as the workspace executor);
- no empty files;
- page structure: doctype, `<html lang>`, charset and viewport meta, non-empty `<title>`,
  a stylesheet link, `<nav>` with links, `<main>`, exactly one `<h1>`;
- internal references: every relative `href`/`src` points at a generated file, and every
  `#anchor` (same page or `page.html#anchor`) exists;
- every page is reachable from the navigation on `index.html`;
- the stylesheet is responsive (`@media` rule).

Pass `spec` (normalized or raw) to also check that the file set matches it exactly.
"""
import posixpath
import re
from html.parser import HTMLParser
from typing import Any, Dict, List, Optional, Set

REQUIRED_FILES = ("index.html", "style.css")
ALLOWED_SUFFIXES = (".html", ".css", ".js", ".json", ".svg", ".txt", ".md", ".xml", ".webmanifest")
_EXTERNAL = re.compile(r"^(?:[a-z][a-z0-9+.-]*:|//)", re.IGNORECASE)
_SAFE_SCHEMES = ("http:", "https:", "mailto:", "tel:")


class _PageParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.tags: List[str] = []
        self.attrs: List[Dict[str, Optional[str]]] = []
        self.ids: Set[str] = set()
        self.refs: List[str] = []
        self.nav_refs: List[str] = []
        self.stylesheets: List[str] = []
        self.h1_count = 0
        self.title = ""
        self._in_title = False
        self._nav_depth = 0
        self.has_viewport = False
        self.has_charset = False
        self.lang = None

    def handle_starttag(self, tag: str, attrs: List[Any]) -> None:
        a = dict(attrs)
        self.tags.append(tag)
        if a.get("id"):
            self.ids.add(a["id"])
        if tag == "html":
            self.lang = a.get("lang")
        elif tag == "title":
            self._in_title = True
        elif tag == "h1":
            self.h1_count += 1
        elif tag == "nav":
            self._nav_depth += 1
        elif tag == "meta":
            if (a.get("name") or "").lower() == "viewport" and "width=device-width" in (a.get("content") or ""):
                self.has_viewport = True
            if a.get("charset"):
                self.has_charset = True
        elif tag == "link" and (a.get("rel") or "").lower() == "stylesheet" and a.get("href"):
            self.stylesheets.append(a["href"])
        for key in ("href", "src"):
            if a.get(key) is not None:
                self.refs.append(a[key] or "")
                if key == "href" and tag == "a" and self._nav_depth:
                    self.nav_refs.append(a[key] or "")

    def handle_startendtag(self, tag: str, attrs: List[Any]) -> None:
        self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            self._in_title = False
        elif tag == "nav" and self._nav_depth:
            self._nav_depth -= 1

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self.title += data


def _path_problem(path: Any) -> Optional[str]:
    if not isinstance(path, str) or not path:
        return "invalid file name %r" % (path,)
    if path.startswith(("/", "\\")) or re.match(r"^[A-Za-z]:", path) or "\\" in path:
        return "%s must be a relative POSIX path" % path
    parts = path.split("/")
    if any(part in ("", ".", "..") for part in parts):
        return "%s must not contain empty, '.' or '..' segments" % path
    if any(part.startswith(".") for part in parts):
        return "%s must not contain hidden names" % path
    if not path.lower().endswith(ALLOWED_SUFFIXES):
        return "%s has a file type that is not allowed" % path
    return None


def _resolve(page: str, ref: str) -> str:
    """Resolve `ref` relative to `page`, POSIX style, without touching the filesystem."""
    base = posixpath.dirname(page)
    return posixpath.normpath(posixpath.join(base, ref)) if base else posixpath.normpath(ref)


def validate_site(files: Any, spec: Optional[Dict[str, Any]] = None) -> List[str]:
    if not isinstance(files, dict):
        return ["files must be a mapping of path -> text"]
    problems: List[str] = []

    for required in REQUIRED_FILES:
        if required not in files:
            problems.append("missing required file %s" % required)

    for path, content in files.items():
        issue = _path_problem(path)
        if issue:
            problems.append(issue)
        if not isinstance(content, str):
            problems.append("%s content must be text" % path)
        elif not content.strip():
            problems.append("%s is empty" % path)

    pages: Dict[str, _PageParser] = {}
    for path, content in sorted(files.items()):
        if not (isinstance(path, str) and path.endswith(".html") and isinstance(content, str) and content.strip()):
            continue
        parser = _PageParser()
        try:
            parser.feed(content)
            parser.close()
        except Exception as exc:  # html.parser is lenient; this is a last resort
            problems.append("%s could not be parsed (%s)" % (path, exc.__class__.__name__))
            continue
        pages[path] = parser
        if not content.lstrip().lower().startswith("<!doctype html>"):
            problems.append("%s does not start with <!doctype html>" % path)
        if not parser.lang:
            problems.append("%s has no <html lang>" % path)
        if not parser.has_charset:
            problems.append("%s has no charset meta" % path)
        if not parser.has_viewport:
            problems.append("%s is not responsive (no viewport meta)" % path)
        if not parser.title.strip():
            problems.append("%s has an empty <title>" % path)
        if "nav" not in parser.tags:
            problems.append("%s has no navigation" % path)
        elif not parser.nav_refs:
            problems.append("%s has a navigation without links" % path)
        if "main" not in parser.tags:
            problems.append("%s has no <main>" % path)
        if parser.h1_count != 1:
            problems.append("%s must have exactly one <h1> (found %d)" % (path, parser.h1_count))
        if not parser.stylesheets:
            problems.append("%s does not link a stylesheet" % path)

    # Internal references and anchors.
    for path, parser in pages.items():
        for ref in parser.refs:
            ref = ref.strip()
            if not ref:
                problems.append("%s has an empty link" % path)
                continue
            lowered = ref.lower()
            if _EXTERNAL.match(ref):
                if not lowered.startswith(_SAFE_SCHEMES):
                    problems.append("%s uses an unsafe link %s" % (path, ref))
                continue
            target, _, anchor = ref.partition("#")
            target = target.split("?", 1)[0]
            resolved = _resolve(path, target) if target else path
            if target and resolved not in files:
                problems.append("%s references missing file %s" % (path, ref))
                continue
            if anchor:
                target_page = pages.get(resolved)
                if target_page is None or anchor not in target_page.ids:
                    problems.append("%s references missing anchor %s" % (path, ref))

    # Every page reachable from the home page's navigation.
    home = pages.get("index.html")
    if home is not None:
        linked = {_resolve("index.html", r.split("#", 1)[0]) for r in home.nav_refs if r and not _EXTERNAL.match(r)}
        for path in sorted(pages):
            if path != "index.html" and path not in linked:
                problems.append("%s is not linked from the navigation on index.html" % path)

    css = files.get("style.css")
    if isinstance(css, str) and css.strip() and "@media" not in css:
        problems.append("style.css has no @media rule (not responsive)")

    if spec is not None:
        problems.extend(_spec_problems(files, spec))
    return problems


def _spec_problems(files: Dict[str, Any], spec: Dict[str, Any]) -> List[str]:
    from backend.generator.spec import SpecError, normalize_spec
    from backend.generator.templates import expected_files

    try:
        normalized = normalize_spec(spec)
    except SpecError as exc:
        return ["spec: %s" % p for p in exc.problems]
    expected = set(expected_files(normalized))
    actual = set(files)
    problems = ["missing file %s for the spec" % p for p in sorted(expected - actual)]
    problems += ["unexpected file %s for the spec" % p for p in sorted(actual - expected)]
    for page in normalized["pages"]:
        content = files.get("%s.html" % page["slug"])
        if not isinstance(content, str):
            continue
        for section in page["sections"]:
            if section["id"] and ('id="%s"' % section["id"]) not in content:
                problems.append("%s.html is missing section %s" % (page["slug"], section["id"]))
    return problems
