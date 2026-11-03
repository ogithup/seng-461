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

---

# Sprint 4 (Rana, branch `feature/sprint4-generator`)

No WebsiteSpec field was added or made required; everything below uses the approved v1 fields
(`docs/sprint4-contracts.md` §3).

## Page selection for the interpreter (Bejan)

```python
from backend.generator import WebsiteGenerator, starter_spec, available_pages

spec = starter_spec("landing", "Acme", pages=["pricing", "faq"],
                    theme={"primary": "#1e3a8a", "font": "serif"})
files = WebsiteGenerator().build(spec)
```

| Type | `available_pages()` | Default (`pages=None`, unchanged from Sprint 3) |
|---|---|---|
| blog | index, archive, about, contact | index, archive, about |
| portfolio | index, projects, about, contact | index, projects, contact |
| landing | index, features, pricing, faq, contact | index |

`index` is always included and navigation keeps the catalogue order, so the same selection in
any order gives the same files. Links to pages that were not selected are removed. An unknown
page raises `ValueError` naming the available ones. `theme` and `tagline` are passed through
and checked by `normalize_spec`. The result always passes `normalize_spec`, so `interpret()` can
return it directly, and `spec_for()` can be retired once the interpreter uses it.

## Audit (task R1) and fixes

| # | Problem found | Fix |
|---|---|---|
| 1 | Only fixed starter sites; the interpreter could not choose pages | `starter_spec(pages=, theme=, tagline=)`, a page catalogue per type, `available_pages()` |
| 2 | A `hero` section that was not first produced a second `<h1>`, so the build failed | later heroes render with `<h2>` (`.hero-secondary`) |
| 3 | Two sections with the same heading were rejected (duplicate anchor) | generated anchors are made unique (`notes`, `notes-2`); explicit duplicate ids are still rejected |
| 4 | A heading such as "Content" produced `id="content"`, clashing with the skip-link target | `content` and `site-nav` are reserved; generated ids avoid them, explicit ones are rejected |
| 5 | `items` on `hero` and `cta` sections were silently dropped | rendered as a card grid |
| 6 | A page over the executor's 200 000-byte limit failed only while writing, after earlier files were written | the validator rejects oversized files (and more than 20 files) before any action is returned |
| 7 | The validator did not detect duplicate element ids | reported per page |

## Tests

`tests/generator/test_sprint4.py`: every page selection of every type, defaults, determinism,
theme, meaningful differences, invalid pages and themes, missing content, duplicate and invalid
output paths, oversized output, and each audit fix. `pytest tests/generator` needs no API.

## Known limits

- Starter content is placeholder text; real content comes from the spec (or a future LLM).
- `lang="en"` is fixed; a language field would need a contract change.
