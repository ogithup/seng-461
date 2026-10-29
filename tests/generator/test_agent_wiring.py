"""The generator plugs into the application's default SiteAgent through GENERATOR_IMPL."""
from types import SimpleNamespace

from backend.generator import WebsiteGenerator
from backend.integration import load_object
from backend.integration.site_agent import SiteAgent


def run_agent(agent, request):
    """Plan, then ask for one action per task, like the API's task runner does."""
    files = {}
    for prompt in agent.plan(request):
        action = agent.next_action(SimpleNamespace(prompt=prompt), None)
        assert action["type"] == "write_file"
        files[action["path"]] = action["content"]
        assert agent.next_action(SimpleNamespace(prompt=prompt), {"success": True}) is None
    return files


def test_generator_impl_path_loads_the_generator():
    factory = load_object("backend.generator:WebsiteGenerator")
    assert isinstance(factory(), WebsiteGenerator)


def test_site_agent_with_this_generator_writes_a_valid_blog():
    agent = SiteAgent(WebsiteGenerator())
    files = run_agent(agent, "Create a blog called Travel Notes")
    assert set(files) == {"index.html", "about.html", "style.css", "script.js"}
    assert "Travel Notes" in files["index.html"]
    assert WebsiteGenerator().validate(files) == []


def test_blog_and_portfolio_requests_produce_different_sites():
    agent = SiteAgent(WebsiteGenerator())
    blog = run_agent(agent, "Create a blog")
    portfolio = run_agent(agent, "Build me a portfolio for Ada Lovelace")
    assert set(blog) != set(portfolio)
    assert "projects.html" in portfolio and "Ada Lovelace" in portfolio["index.html"]
    assert "site-portfolio" in portfolio["index.html"] and "site-blog" in blog["index.html"]


def test_landing_request_is_valid_and_index_is_planned_first():
    agent = SiteAgent(WebsiteGenerator())
    plan = agent.plan("Create a landing page for Acme")
    assert plan[0].startswith("Write index.html")
    assert WebsiteGenerator().validate(run_agent(agent, "Create a landing page for Acme")) == []
