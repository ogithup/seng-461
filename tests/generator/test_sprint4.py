"""Sprint 4 generator work (Rana): page selection, WebsiteSpec v1 fields, robustness fixes.

Covers the fields Bejan's interpreter may set this sprint (site_type, title, pages, theme)
and the defects found in the Sprint 4 audit (see backend/generator/README.md).
"""
import copy
import itertools

import pytest

from backend.generator import (
    DEFAULT_PAGES,
    GenerationError,
    SITE_TYPES,
    SpecError,
    WebsiteGenerator,
    available_pages,
    normalize_spec,
    starter_spec,
    validate_site,
)
from backend.generator.validator import MAX_FILE_BYTES
from tests.generator.specs import BLOG, LANDING, PORTFOLIO


@pytest.fixture
def generator():
    return WebsiteGenerator()


def all_page_selections(site_type):
    optional = [p for p in available_pages(site_type) if p != "index"]
    for n in range(len(optional) + 1):
        for combo in itertools.combinations(optional, n):
            yield list(combo)


# --- page selection ------------------------------------------------------------------

@pytest.mark.parametrize("site_type", SITE_TYPES)
def test_every_page_selection_builds_a_valid_site(generator, site_type):
    for pages in all_page_selections(site_type):
        files = generator.build(starter_spec(site_type, "Demo", pages=pages))
        expected = {"index.html", "style.css", "script.js"} | {"%s.html" % p for p in pages}
        assert set(files) == expected, pages


@pytest.mark.parametrize("site_type", SITE_TYPES)
def test_default_pages_are_unchanged_from_sprint_3(site_type):
    spec = starter_spec(site_type, "Demo")
    assert tuple(p["slug"] for p in spec["pages"]) == DEFAULT_PAGES[site_type]


def test_index_is_always_included_and_catalogue_order_is_kept():
    spec = starter_spec("blog", "Demo", pages=["contact", "about"])
    assert [p["slug"] for p in spec["pages"]] == ["index", "about", "contact"]


def test_selection_order_does_not_change_the_output(generator):
    a = generator.generate(starter_spec("landing", "Acme", pages=["pricing", "faq"]))
    b = generator.generate(starter_spec("landing", "Acme", pages=["faq", "pricing", "index"]))
    assert a == b


def test_links_to_unselected_pages_are_removed():
    spec = starter_spec("blog", "Demo", pages=[])
    index = spec["pages"][0]
    assert all("about.html" not in str(s.get("cta")) for s in index["sections"])
    assert all(i.get("link") != "about.html" for s in index["sections"] for i in s.get("items", []))
    normalize_spec(spec)  # still a valid spec


def test_links_to_selected_pages_are_kept():
    spec = starter_spec("blog", "Demo", pages=["about", "contact"])
    about = next(p for p in spec["pages"] if p["slug"] == "about")
    assert any((s.get("cta") or {}).get("href") == "contact.html" for s in about["sections"])


@pytest.mark.parametrize("pages", [["shop"], ["index", "cart"], "about", [1]])
def test_unknown_or_malformed_page_selection_is_rejected(pages):
    with pytest.raises(ValueError):
        starter_spec("blog", "Demo", pages=pages)


def test_unknown_site_type_is_rejected():
    with pytest.raises(ValueError):
        starter_spec("shop", "Demo")
    with pytest.raises(ValueError):
        available_pages("shop")


def test_starter_spec_returns_independent_copies():
    a = starter_spec("portfolio", "A", pages=["about"])
    a["pages"][0]["sections"][0]["heading"] = "changed"
    assert starter_spec("portfolio", "A", pages=["about"])["pages"][0]["sections"][0]["heading"] != "changed"


# --- theme and title -----------------------------------------------------------------

def test_theme_choice_reaches_the_css(generator):
    theme = {"primary": "#123456", "accent": "#ABCDEF", "font": "mono"}
    css = generator.generate(starter_spec("portfolio", "Demo", theme=theme))["style.css"]
    assert "--primary: #123456" in css and "--accent: #abcdef" in css and "monospace" in css


@pytest.mark.parametrize("theme", [{"primary": "blue"}, {"font": "comic"}, "dark"])
def test_invalid_theme_is_rejected(generator, theme):
    with pytest.raises(SpecError):
        generator.generate(starter_spec("blog", "Demo", theme=theme))


def test_title_and_tagline_appear_on_every_page(generator):
    files = generator.generate(starter_spec("blog", "Ankara Eats", pages=["about"], tagline="Food notes"))
    for name in ("index.html", "about.html"):
        assert "Ankara Eats" in files[name]
    assert "Food notes" in files["index.html"]


def test_same_spec_same_files(generator):
    spec = starter_spec("landing", "Acme", pages=["features", "contact"], theme={"font": "serif"})
    assert generator.generate(copy.deepcopy(spec)) == generator.generate(copy.deepcopy(spec))


def test_different_requests_differ_meaningfully(generator):
    blog = generator.generate(starter_spec("blog", "Same"))
    portfolio = generator.generate(starter_spec("portfolio", "Same"))
    landing = generator.generate(starter_spec("landing", "Same"))
    assert len({frozenset(blog), frozenset(portfolio), frozenset(landing)}) == 3
    assert len({blog["style.css"], portfolio["style.css"], landing["style.css"]}) == 3
    # Same type, different page choice: different file set and navigation.
    small = generator.generate(starter_spec("landing", "Same"))
    full = generator.generate(starter_spec("landing", "Same", pages=["pricing", "faq"]))
    assert set(small) != set(full) and "pricing.html" in full["index.html"]


# --- audit fixes ---------------------------------------------------------------------

def test_hero_after_the_first_section_keeps_a_single_h1(generator):
    spec = copy.deepcopy(LANDING)
    spec["pages"][0]["sections"].append({"kind": "hero", "heading": "Second hero", "body": "More."})
    files = generator.build(spec)
    assert files["index.html"].count("<h1") == 1
    assert "hero-secondary" in files["index.html"]


def test_repeated_headings_get_unique_anchors():
    spec = copy.deepcopy(BLOG)
    spec["pages"][2]["sections"] += [
        {"heading": "Notes", "body": "a"},
        {"heading": "Notes", "body": "b"},
        {"id": "notes-2", "heading": "Explicit", "body": "c"},
    ]
    ids = [s["id"] for s in normalize_spec(spec)["pages"][2]["sections"]]
    assert len(ids) == len(set(ids))
    assert "notes" in ids and "notes-2" in ids and "notes-3" in ids


@pytest.mark.parametrize("heading", ["Content", "Site nav"])
def test_section_anchors_never_reuse_layout_ids(generator, heading):
    spec = copy.deepcopy(BLOG)
    spec["pages"][2]["sections"].append({"heading": heading, "body": "x"})
    files = generator.build(spec)
    assert files["about.html"].count('id="content"') == 1
    assert files["about.html"].count('id="site-nav"') == 1


@pytest.mark.parametrize("anchor", ["content", "site-nav"])
def test_explicit_layout_ids_are_rejected(anchor):
    spec = copy.deepcopy(BLOG)
    spec["pages"][2]["sections"][0]["id"] = anchor
    with pytest.raises(SpecError) as info:
        normalize_spec(spec)
    assert any("reserved" in p for p in info.value.problems)


@pytest.mark.parametrize("kind", ["hero", "cta"])
def test_items_in_hero_and_cta_sections_are_rendered(generator, kind):
    spec = copy.deepcopy(PORTFOLIO)
    spec["pages"][2]["sections"][0]["kind"] = kind
    spec["pages"][2]["sections"][0]["items"] = [{"title": "Visible item", "body": "shown"}]
    assert "Visible item" in generator.build(spec)["contact.html"]


def test_oversized_site_is_rejected_before_anything_is_written(generator):
    item = {"title": "t", "body": "y" * 4000}
    spec = {"site_type": "blog", "title": "Big", "pages": [{"slug": "index", "title": "Home", "sections": [
        {"heading": "Part %d" % i, "body": "x" * 4000, "items": [item] * 24} for i in range(3)
    ]}]}
    with pytest.raises(GenerationError) as info:
        generator.build(spec)
    assert any("larger than %d bytes" % MAX_FILE_BYTES in p for p in info.value.problems)


# --- validator: duplicate / invalid output paths -------------------------------------

def test_duplicate_ids_in_a_page_are_reported(generator):
    files = generator.build(starter_spec("blog", "Demo"))
    files["about.html"] = files["about.html"].replace('id="get-in-touch"', 'id="about-this-blog"')
    assert any("more than once" in p for p in validate_site(files))


@pytest.mark.parametrize("path", ["../index.html", "/etc/passwd.html", "a//b.html", "C:/x.html",
                                  ".hidden.html", "page.exe", "dir\\page.html", ""])
def test_invalid_output_paths_are_reported(generator, path):
    files = generator.build(starter_spec("landing", "Demo"))
    files[path] = "<!doctype html>"
    assert validate_site(files)


def test_too_many_files_are_reported(generator):
    files = generator.build(starter_spec("landing", "Demo"))
    files.update({"extra-%d.txt" % i: "x" for i in range(30)})
    assert any("at most" in p for p in validate_site(files))


def test_duplicate_page_slugs_cannot_produce_duplicate_paths():
    spec = starter_spec("blog", "Demo", pages=["about"])
    spec["pages"].append(copy.deepcopy(spec["pages"][1]))
    with pytest.raises(SpecError) as info:
        normalize_spec(spec)
    assert any("unique" in p for p in info.value.problems)


def test_missing_content_is_rejected():
    spec = starter_spec("blog", "Demo")
    spec["pages"][0]["sections"][1]["body"] = "   "
    spec["pages"][0]["sections"][1].pop("items", None)
    with pytest.raises(SpecError):
        normalize_spec(spec)
