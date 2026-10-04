from src.artifact.storage import (
    load_capability
)


def test_sample_artifact_loads():

    capability = load_capability(

        "artifacts/"
        "lookup_member_balance.json"
    )


    assert (
        capability.name
        ==
        "lookup_member_balance"
    )


    assert (
        "member_id"
        in capability.inputs
    )


    assert (
        len(capability.steps)
        >= 2
    )