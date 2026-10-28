"""normalize_spec accepts good specs, fills defaults, and reports every problem."""
import copy

import pytest

from backend.generator import SpecError, normalize_spec
from tests.generator.specs import BLOG, LANDING, PORTFOLIO


def problems_of(spec):
    with pytest.raises(SpecError) as info:
        normalize_spec(spec)
    return info.value.problems


def minimal(**overrides):
    spec = {
        "site_type": "blog",
        "title": "T",
        "pages": [{"slug": "index", "title": "Home", "sections": [{"heading": "H", "body": "B"}]}],
    }
    spec.update(overrides)
    return spec


def test_defaults_are_filled_in():
    spec = normalize_spec(minimal())
    assert spec["theme"] == {"primary": "#2b6cb0", "accent": "#dd6b20", "font": "serif"}
    assert spec["options"] == {"include_script": True}
    assert spec["tagline"] == "" and spec["footer"] == ""
    section = spec["pages"][0]["sections"][0]
    assert section == {"kind": "text", "heading": "H", "body": "B", "id": "h", "items": [], "cta": None}


def test_first_index_section_defaults_to_hero_for_portfolio_and_landing():
    for site_type in ("portfolio", "landing"):
        spec = normalize_spec(minimal(site_type=site_type))
        assert spec["pages"][0]["sections"][0]["kind"] == "hero"


def test_index_page_is_moved_first():
    spec = minimal()
    spec["pages"].insert(0, {"slug": "about", "title": "About", "sections": [{"heading": "A", "body": "b"}]})
    assert [p["slug"] for p in normalize_spec(spec)["pages"]] == ["index", "about"]


def test_example_specs_are_valid():
    for spec in (BLOG, PORTFOLIO, LANDING):
        normalize_spec(spec)


def test_text_is_trimmed_and_colours_lowercased():
    spec = normalize_spec(minimal(title="  Hi  ", theme={"primary": "#ABCDEF"}))
    assert spec["title"] == "Hi" and spec["theme"]["primary"] == "#abcdef"


@pytest.mark.parametrize(
    "spec, expected",
    [
        ("not a dict", "spec must be an object"),
        (minimal(site_type="shop"), "spec.site_type must be one of"),
        (minimal(title="   "), "spec.title must not be empty"),
        (minimal(title=None), "spec.title is required"),
        (minimal(title="x" * 81), "longer than 80"),
        (minimal(pages=[]), "spec.pages must be a non-empty list"),
        (minimal(pages=[{"slug": "about", "title": "A", "sections": [{"heading": "h", "body": "b"}]}]),
         "must include an 'index' page"),
        (minimal(pages=[{"slug": "Index!", "title": "A", "sections": []}]), "slug"),
        (minimal(theme={"primary": "blue"}), "spec.theme.primary must be a #rrggbb colour"),
        (minimal(theme={"font": "comic"}), "spec.theme.font"),
        (minimal(options={"include_script": "yes"}), "include_script"),
    ],
)
def test_invalid_specs_are_rejected(spec, expected):
    assert any(expected in p for p in problems_of(spec)), problems_of(spec)


def test_duplicate_slugs_are_rejected():
    page = {"slug": "index", "title": "Home", "sections": [{"heading": "h", "body": "b"}]}
    assert any("unique" in p for p in problems_of(minimal(pages=[page, copy.deepcopy(page)])))


def test_section_needs_body_or_items():
    spec = minimal()
    spec["pages"][0]["sections"] = [{"heading": "Empty"}]
    assert any("body is required" in p for p in problems_of(spec))
    spec["pages"][0]["sections"] = [{"heading": "Items", "items": [{"title": "one"}]}]
    normalize_spec(spec)


def test_unknown_section_kind_is_rejected():
    spec = minimal()
    spec["pages"][0]["sections"][0]["kind"] = "carousel"
    assert any("kind must be one of" in p for p in problems_of(spec))


@pytest.mark.parametrize("href", ["javascript:alert(1)", "data:text/html,x", "../secret.html",
                                  "/etc/passwd", "page.php", "about.html#Bad Anchor"])
def test_unsafe_or_unsupported_links_are_rejected(href):
    spec = minimal()
    spec["pages"][0]["sections"][0]["cta"] = {"label": "Go", "href": href}
    assert any("cta.href" in p for p in problems_of(spec))


@pytest.mark.parametrize("href", ["missing.html", "#nowhere", "index.html#nowhere"])
def test_links_to_missing_pages_or_anchors_are_rejected(href):
    spec = minimal()
    spec["pages"][0]["sections"][0]["items"] = [{"title": "x", "link": href}]
    assert any("points at missing" in p for p in problems_of(spec))


def test_duplicate_section_ids_on_a_page_are_rejected():
    spec = minimal()
    spec["pages"][0]["sections"] = [{"heading": "Same", "body": "a"}, {"heading": "Same", "body": "b"}]
    assert any("duplicate section id" in p for p in problems_of(spec))


def test_all_problems_are_reported_at_once():
    problems = problems_of({"site_type": "x", "title": "", "pages": [], "theme": {"primary": "red"}})
    assert len(problems) >= 4


def test_limits_are_enforced():
    page = lambda i: {"slug": "p%d" % i, "title": "P", "sections": [{"heading": "h", "body": "b"}]}
    pages = [dict(page(0), slug="index")] + [page(i) for i in range(1, 14)]
    assert any("more than 12 pages" in p for p in problems_of(minimal(pages=pages)))
