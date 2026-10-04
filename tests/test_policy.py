import pytest

from src.safety.policy import (
    check_url,
    PolicyViolation
)


def test_localhost_is_allowed():

    check_url(
        "http://127.0.0.1:8000"
    )


def test_external_host_is_blocked():

    with pytest.raises(
        PolicyViolation
    ):

        check_url(
            "https://example.com"
        )