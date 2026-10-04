from pathlib import Path

from .models import Capability


def save_capability(
    capability: Capability,
    path: str | Path
) -> None:

    path = Path(path)

    path.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    path.write_text(
        capability.model_dump_json(indent=2),
        encoding="utf-8"
    )


def load_capability(
    path: str | Path
) -> Capability:

    raw = Path(path).read_text(
        encoding="utf-8"
    )

    return Capability.model_validate_json(raw)