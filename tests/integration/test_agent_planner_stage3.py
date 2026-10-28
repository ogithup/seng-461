import pytest

from backend.agent.planner import _planning_info, plan


@pytest.mark.parametrize(
    ("user_request", "site_type", "title"),
    [
        ("Create a blog", "blog", "My Blog"),
        ("Build a portfolio", "portfolio", "My Portfolio"),
        ("Make a landing page", "landing", "My Product"),
    ],
)
def test_planning_info_classifies_site_and_uses_default_title(user_request, site_type, title):
    info = _planning_info(user_request)

    assert info.site_type == site_type
    assert info.title == title


def test_planning_info_extracts_an_explicit_title():
    assert _planning_info("Create a blog called Travel Notes").title == "Travel Notes"


@pytest.mark.parametrize("user_request", ["", " ", "\n\t"])
def test_planning_info_rejects_blank_requests(user_request):
    with pytest.raises(ValueError):
        _planning_info(user_request)


def test_planning_info_rejects_non_string_requests():
    with pytest.raises(TypeError):
        _planning_info(None)


def test_plan_preserves_list_of_strings_interface_without_file_names():
    result = plan("Create a blog called Travel Notes")

    assert result == ["Create a blog site titled 'Travel Notes'"]
    assert isinstance(result, list)
    assert all(isinstance(step, str) for step in result)
    assert not any(".html" in step for step in result)


def test_plan_is_deterministic():
    request = "Build a portfolio named Ada Lovelace"

    assert plan(request) == plan(request)
