from urllib.parse import urlparse

from src.artifact.models import (
    ActionType,
    Step
)


ALLOWED_HOSTS = {
    "127.0.0.1",
    "localhost"
}


ALLOWED_ACTIONS = {

    ActionType.click,

    ActionType.fill,

    ActionType.read,

    ActionType.extract,

    ActionType.wait,

    ActionType.navigate,

    ActionType.complete,

    ActionType.escalate
}


RISKY_ACTIONS = {

    "delete",

    "transfer",

    "submit_payment",

    "download_file"
}


class PolicyViolation(RuntimeError):
    pass


def check_url(url: str) -> None:

    host = urlparse(url).hostname

    if host not in ALLOWED_HOSTS:

        raise PolicyViolation(
            f"Host is not allowlisted: {host}"
        )


def check_step(step: Step) -> None:

    if step.action not in ALLOWED_ACTIONS:

        raise PolicyViolation(
            f"Action is not allowlisted: "
            f"{step.action}"
        )