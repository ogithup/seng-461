"""WebsiteGenerator turns a spec into a complete, valid, deterministic static site."""
import ast
import copy
import re
from pathlib import Path

import pytest

from backend.generator import SpecError, WebsiteGenerator, starter_spec
from backend.integration.reference_generator import spec_for
from tests.generator.specs import ALL, BLOG, LANDING, PORTFOLIO


@pytest.fixture
def generator():
    return WebsiteGenerator()


@pytest.mark.parametrize("name", sorted(ALL))
def test_each_example_spec_generates_a_valid_site(generator, name):
    spec = ALL[name]
    files = generator.generate(spec)
    assert generator.validate(files) == []
    assert generator.validate(files, spec) == []


def test_blog_files_and_content(generator):
    files = generator.generate(BLOG)
    assert set(files) == {"index.html", "posts.html", "about.html", "style.css", "script.js"}
    index = files["index.html"]
    assert "<h1>Travel Notes</h1>" in index
    assert "Slow travel, good food and long walks." in index
    assert 'class="post-list"' in index and "Oct 2026" in index
    assert 'href="posts.html#kapadokya"' in index
    assert files["posts.html"].count("<p>Day") == 3  # blank lines become paragraphs
    assert "site-blog" in index


def test_portfolio_has_hero_and_project_grid(generator):
    files = generator.generate(PORTFOLIO)
    index = files["index.html"]
    assert re.search(r'<section class="hero"[^>]*>\s*<h1>Ada Lovelace</h1>', index)
    assert 'class="grid grid-projects"' in index
    assert 'href="mailto:ada@example.com"' in files["contact.html"]
    assert "<h1>Work</h1>" in files["work.html"]


def test_landing_without_script_and_with_custom_footer(generator):
    files = generator.generate(LANDING)
    assert set(files) == {"index.html", "faq.html", "style.css"}
    for page in ("index.html", "faq.html"):
        assert "<script" not in files[page]
        assert "nav-toggle" not in files[page]
        assert "Acme Inc. Made in Ankara." in files[page]
    assert 'class="cta-band" id="pricing"' in files["index.html"]


def test_site_types_look_different(generator):
    sites = {name: generator.generate(spec) for name, spec in ALL.items()}
    css = {name: site["style.css"] for name, site in sites.items()}
    assert len(set(css.values())) == 3
    assert "/* blog */" in css["blog"] and "/* portfolio */" in css["portfolio"]
    assert "/* landing */" in css["landing"]
    assert "Georgia" in css["blog"] and "system-ui" in css["portfolio"]


def test_theme_colours_reach_the_stylesheet_with_readable_text(generator):
    css = generator.generate(BLOG)["style.css"]
    assert "--primary: #1e3a8a;" in css and "--accent: #f59e0b;" in css
    assert "--on-primary: #ffffff;" in css  # dark primary -> white text
    light = generator.generate(LANDING)["style.css"]
    assert "--on-primary: #1a202c;" in light  # light primary -> dark text


@pytest.mark.parametrize("name", sorted(ALL))
def test_every_page_navigates_to_every_page(generator, name):
    spec = ALL[name]
    files = generator.generate(spec)
    slugs = [p["slug"] for p in spec["pages"]]
    for slug in slugs:
        page = files["%s.html" % slug]
        nav = page[page.index("<nav"):page.index("</nav>")]
        assert re.findall(r'href="([a-z0-9-]+)\.html"', nav) == ["index"] + [s for s in slugs if s != "index"]
        assert nav.count('aria-current="page"') == 1
        assert 'href="%s.html" aria-current="page"' % slug in nav


@pytest.mark.parametrize("name", sorted(ALL))
def test_pages_are_responsive(generator, name):
    files = generator.generate(ALL[name])
    assert "@media (max-width: 640px)" in files["style.css"]
    for path, content in files.items():
        if path.endswith(".html"):
            assert '<meta name="viewport" content="width=device-width, initial-scale=1">' in content


def test_output_is_deterministic(generator):
    first = generator.generate(copy.deepcopy(BLOG))
    second = WebsiteGenerator().generate(copy.deepcopy(BLOG))
    assert first == second


def test_generate_does_not_mutate_the_spec(generator):
    spec = copy.deepcopy(PORTFOLIO)
    generator.generate(spec)
    assert spec == PORTFOLIO


def test_user_text_is_escaped(generator):
    spec = copy.deepcopy(BLOG)
    spec["title"] = 'Tom & "Jerry" <script>alert(1)</script>'
    spec["pages"][0]["sections"][1]["body"] = "<img src=x onerror=alert(1)>"
    files = generator.generate(spec)
    assert "<script>alert" not in files["index.html"]
    assert "<img src=x" not in files["index.html"]
    assert "Tom &amp; &quot;Jerry&quot; &lt;script&gt;" in files["index.html"]
    assert generator.validate(files) == []


def test_invalid_spec_raises_spec_error(generator):
    with pytest.raises(SpecError):
        generator.generate({"site_type": "shop", "title": "x", "pages": []})


def test_build_returns_validated_files(generator):
    assert generator.build(BLOG) == generator.generate(BLOG)


@pytest.mark.parametrize("site_type", ["blog", "portfolio", "landing"])
def test_starter_specs_are_complete_sites(generator, site_type):
    spec = starter_spec(site_type, "Starter")
    files = generator.build(spec)
    assert "Starter" in files["index.html"]
    assert starter_spec(site_type, "Starter") == spec  # fresh copy each call


@pytest.mark.parametrize("site_type", ["blog", "portfolio", "landing"])
def test_accepts_the_reference_spec_format(generator, site_type):
    """The default SiteAgent builds specs with `spec_for`; they must work unchanged."""
    spec = spec_for(site_type, "Compat")
    files = generator.generate(spec)
    assert set(files) == {"%s.html" % p["slug"] for p in spec["pages"]} | {"style.css", "script.js"}
    assert generator.validate(files, spec) == []


def test_generated_files_fit_the_executor_bounds(generator):
    allowed = (".html", ".css", ".js")
    for spec in ALL.values():
        for path, content in generator.generate(spec).items():
            assert path.endswith(allowed) and "/" not in path and not path.startswith(".")
            assert len(content.encode("utf-8")) < 200_000


def test_package_depends_only_on_the_standard_library():
    """No frontend, model, API or storage imports: the generator stands alone."""
    package = Path(__file__).resolve().parents[2] / "backend" / "generator"
    for source in package.glob("*.py"):
        tree = ast.parse(source.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            names = []
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or ""]
            for name in names:
                top = name.split(".")[0]
                if top == "backend":
                    assert name.startswith("backend.generator"), (source.name, name)
                else:
                    assert top in {"argparse", "ast", "copy", "html", "json", "pathlib", "posixpath",
                                   "re", "sys", "typing"}, (source.name, name)
