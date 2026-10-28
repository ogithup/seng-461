from typing import Literal, Union, get_args, get_origin, get_type_hints

from backend.agent.action_schema import AgentAction, RunCommandAction, WriteFileAction


def test_agent_action_is_a_union_of_api_action_variants():
    assert get_origin(AgentAction) is Union
    assert set(get_args(AgentAction)) == {RunCommandAction, WriteFileAction}


def test_run_command_fields_match_api_contract():
    assert RunCommandAction.__required_keys__ == {"type", "command"}
    assert RunCommandAction.__optional_keys__ == {"requires_approval", "reason"}
    assert get_type_hints(RunCommandAction)["type"] == Literal["run_command"]


def test_write_file_fields_match_api_contract_without_approval():
    assert WriteFileAction.__required_keys__ == {"type", "path", "content"}
    assert WriteFileAction.__optional_keys__ == {"reason"}
    assert get_type_hints(WriteFileAction)["type"] == Literal["write_file"]
