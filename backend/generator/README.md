# Website generator — Sprint 3 (Rana)

Deterministic component that turns a validated website specification into a self-contained
static website. Standard library only: it does not depend on the frontend, the AI model,
the API, storage, the filesystem or the network. Same spec in, same files out.

```python
from backend.generator import WebsiteGenerator, starter_spec

generator = WebsiteGenerator()
files = generator.generate(starter_spec("blog", "Travel Notes"))  # {"index.html": "...", ...}
assert generator.validate(files) == []                            # [] means valid
files = generator.build(spec)        # generate + validate, raises if anything is wrong
```

It implements `SiteGeneratorPort` (`backend/api/services/ports.py`). To use it in the app:

```
GENERATOR_IMPL=backend.generator:WebsiteGenerator
```

The default `SiteAgent` then plans one `write_file` action per file this generator returns.

## Files

| File | Purpose |
|---|---|
| `spec.py` | Website specification, `normalize_spec()` validation and defaults, `SpecError` |
| `templates.py` | Blog, portfolio and landing templates; HTML, CSS and the optional JS; `starter_spec()` |
| `validator.py` | `validate_site()` output checks |
| `generator.py` | `WebsiteGenerator` (`generate`, `validate`, `build`, `starter_spec`) |
| `__main__.py` | Demo CLI that writes a site to a folder |

## Specification

```json
{
  "site_type": "blog",
  "title": "Travel Notes",
  "tagline": "Slow travel, good food and long walks.",
  "pages": [
    {"slug": "index", "title": "Home", "sections": [
      {"kind": "posts", "heading": "Latest posts", "body": "Newest first.",
       "items": [{"title": "Ankara on foot", "meta": "Sep 2026", "body": "...", "link": "about.html"}]},
      {"heading": "Start here", "body": "...", "cta": {"label": "About me", "href": "about.html"}}
    ]},
    {"slug": "about", "title": "About", "sections": [{"heading": "Who writes here", "body": "..."}]}
  ],
  "theme": {"primary": "#1e3a8a", "accent": "#f59e0b", "font": "serif"},
  "footer": "Optional footer text",
  "options": {"include_script": true}
}
```

- Required: `site_type` (`blog|portfolio|landing`), `title`, `pages` (1–12, must contain `index`),
  each page `slug` (`a-z0-9-`), `title` and 1–20 `sections` with a `heading` and a `body` or `items`.
- Section `kind`: `text` (default), `hero`, `cards`, `posts`, `projects`, `features`, `cta`.
  On portfolio and landing sites the first section of `index` defaults to `hero`.
- Links (`items[].link`, `cta.href`) may only be `<page>.html[#anchor]`, `#anchor`, `http(s)://`
  or `mailto:`; internal targets must exist. Section anchors default to a slug of the heading.
- Theme defaults per site type; text colour on `primary`/`accent` is picked for contrast.
- `options.include_script: false` produces HTML + CSS only.
- `normalize_spec` reports every problem at once in `SpecError.problems`.

The stand-in `reference_generator.spec_for()` format is a subset of this, so it works unchanged.

## Output

One `<slug>.html` per page, `style.css`, and `script.js` unless disabled. Every page has a
doctype, `lang`, charset and viewport meta, a skip link, a `<nav>` linking every page (current
page marked with `aria-current`), one `<h1>`, `<main>` and a footer. The CSS uses theme tokens,
a fluid layout and a `@media (max-width: 640px)` breakpoint; the JS only adds a mobile menu
toggle, so pages work without it.

## Validation (`validate_site`)

Required files (`index.html`, `style.css`); safe relative paths with the executor's allowed
suffixes; no empty files; per-page structure (doctype, lang, charset, viewport, title, nav with
links, main, exactly one h1, stylesheet); every relative `href`/`src` and `#anchor` resolves;
no unsafe link schemes; every page reachable from the home page navigation; responsive CSS.
`validate(files, spec)` also checks the file set and section anchors match the spec.

## Demo and tests

```bash
python -m backend.generator blog "Travel Notes" out/blog
python -m backend.generator --spec my_site.json out/my_site
python -m pytest tests/generator
```

`tests/generator/specs.py` holds three example specs (blog, portfolio, landing) used by the tests.
`tests/integration/test_website_generator_api.py` runs the whole API with this generator.
