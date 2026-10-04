import pytest

from src.replay.executor import ReplayExecutor


def make_executor() -> ReplayExecutor:
    """
    Create an executor without running its normal constructor.

    _resolve_value() does not require a browser, logger,
    or handoff controller, so this keeps these tests small
    and isolated.
    """
    return ReplayExecutor.__new__(ReplayExecutor)


def test_parameter_substitution():
    executor = make_executor()

    result = executor._resolve_value(
        "{{member_id}}",
        {
            "member_id": "12345",
        },
    )

    assert result == "12345"


def test_literal_value_is_not_modified():
    executor = make_executor()

    result = executor._resolve_value(
        "literal",
        {
            "member_id": "12345",
        },
    )

    assert result == "literal"


def test_none_value_remains_none():
    executor = make_executor()

    result = executor._resolve_value(
        None,
        {
            "member_id": "12345",
        },
    )

    assert result is None


def test_missing_required_parameter_raises_error():
    executor = make_executor()

    with pytest.raises(
        ValueError,
        match="Missing required input: member_id",
    ):
        executor._resolve_value(
            "{{member_id}}",
            {},
        )


def test_different_runtime_member_id_is_substituted():
    executor = make_executor()

    result = executor._resolve_value(
        "{{member_id}}",
        {
            "member_id": "77777",
        },
    )

    assert result == "77777"