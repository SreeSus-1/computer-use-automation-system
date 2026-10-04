from __future__ import annotations

import json

from datetime import (
    datetime,
    timezone
)

from pathlib import Path

from typing import Any


SENSITIVE_KEYS = {

    "password",

    "token",

    "secret",

    "authorization",

    "api_key",

    "access_token"
}


def _redact(value: Any):

    if isinstance(value, dict):

        return {

            key: (
                "***REDACTED***"
                if key.lower() in SENSITIVE_KEYS
                else _redact(val)
            )

            for key, val in value.items()
        }

    if isinstance(value, list):

        return [
            _redact(v)
            for v in value
        ]

    return value


class RunLogger:

    def __init__(
        self,
        path: str | Path
    ):

        self.path = Path(path)

        self.path.parent.mkdir(
            parents=True,
            exist_ok=True
        )

    def write(
        self,
        event: dict[str, Any]
    ) -> None:

        record = {

            "timestamp":
                datetime.now(
                    timezone.utc
                ).isoformat(),

            **_redact(event)
        }

        with self.path.open(
            "a",
            encoding="utf-8"
        ) as file:

            file.write(
                json.dumps(
                    record,
                    ensure_ascii=False
                )
                + "\n"
            )