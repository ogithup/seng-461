"""validate_site catches missing files, empty content, broken references and bad structure."""
import pytest

from backend.generator import WebsiteGenerator, validate_site
from tests.generator.specs import BLOG, PORTFOLIO


@pytest.fixture
def site():
    return WebsiteGenerator().generate(BLOG)


def has(problems, text):
    return any(text in p for p in problems)


def test_a_generated_site_is_valid(site):
    assert validate_site(site) == []


def test_non_mapping_is_rejected():
    assert validate_site(["index.html"]) == ["files must be a mapping of path -> text"]


@pytest.mark.parametrize("name", ["index.html", "style.css"])
def test_required_files(site, name):
    del site[name]
    assert has(validate_site(site), "missing required file %s" % name)


def test_empty_file(site):
    site["about.html"] = "   \n"
    assert has(validate_site(site), "about.html is empty")


@pytest.mark.parametrize("path", ["../x.html", "/abs.html", ".hidden.html", "a//b.html", "run.exe", "C:/x.html"])
def test_unsafe_paths(site, path):
    site[path] = "x"
    assert validate_site(site) != []


def test_broken_internal_link(site):
    site["about.html"] = site["about.html"].replace('href="posts.html"', 'href="gone.html"')
    assert has(validate_site(site), "about.html references missing file gone.html")


def test_broken_anchor(site):
    site["index.html"] = site["index.html"].replace("posts.html#kapadokya", "posts.html#nope")
    assert has(validate_site(site), "references missing anchor posts.html#nope")


def test_missing_script_file_is_a_broken_reference(site):
    del site["script.js"]
    assert has(validate_site(site), "references missing file script.js")


def test_unsafe_link_scheme(site):
    site["about.html"] = site["about.html"].replace('href="index.html"', 'href="javascript:alert(1)"', 1)
    assert has(validate_site(site), "unsafe link")


@pytest.mark.parametrize(
    "old, new, message",
    [
        ("<!doctype html>", "", "does not start with <!doctype html>"),
        ('<html lang="en">', "<html>", "no <html lang>"),
        ('<meta charset="utf-8">', "", "no charset meta"),
        ('name="viewport"', 'name="x"', "not responsive"),
        ("<nav ", "<div ", "has no navigation"),
        ('<main id="content">', "<div>", "has no <main>"),
        ('<link rel="stylesheet" href="style.css">', "", "does not link a stylesheet"),
        ("<h1>", "<h2>", "exactly one <h1> (found 0)"),
    ],
)
def test_page_structure(site, old, new, message):
    assert old in site["about.html"]
    site["about.html"] = site["about.html"].replace(old, new, 1)
    problems = validate_site(site)
    assert any(p.startswith("about.html ") and message in p for p in problems), problems


def test_two_h1_headings(site):
    site["about.html"] = site["about.html"].replace("</main>", "<h1>Again</h1></main>")
    assert has(validate_site(site), "exactly one <h1> (found 2)")


def test_empty_title(site):
    site["about.html"] = site["about.html"].replace(
        site["about.html"][site["about.html"].index("<title>"):site["about.html"].index("</title>") + 8],
        "<title> </title>",
    )
    assert has(validate_site(site), "about.html has an empty <title>")


def test_page_missing_from_navigation(site):
    site["orphan.html"] = site["about.html"]
    assert has(validate_site(site), "orphan.html is not linked from the navigation on index.html")


def test_stylesheet_must_be_responsive(site):
    site["style.css"] = "body { color: red; }"
    assert has(validate_site(site), "style.css has no @media rule")


def test_spec_mismatch_is_reported():
    generator = WebsiteGenerator()
    files = generator.generate(PORTFOLIO)
    del files["contact.html"]
    files["extra.txt"] = "hello"
    problems = validate_site(files, PORTFOLIO)
    assert has(problems, "missing file contact.html for the spec")
    assert has(problems, "unexpected file extra.txt for the spec")


def test_spec_errors_are_reported_not_raised(site):
    assert has(validate_site(site, {"site_type": "nope"}), "spec: ")


def test_missing_section_for_the_spec():
    generator = WebsiteGenerator()
    files = generator.generate(BLOG)
    files["posts.html"] = files["posts.html"].replace('id="ankara-on-foot"', "")
    assert has(validate_site(files, BLOG), "posts.html is missing section ankara-on-foot")
