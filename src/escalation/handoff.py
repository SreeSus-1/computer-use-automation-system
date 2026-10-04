from __future__ import annotations

from dataclasses import dataclass

from src.observability.logger import RunLogger
from src.surface.playwright_adapter import PlaywrightSurfaceAdapter


@dataclass
class InterventionRequest:
    run_id: str
    step_id: str
    reason: str
    current_url: str
    screenshot_path: str
    expected_after_handoff: str | None = None


class HandoffController:

    def __init__(
        self,
        logger: RunLogger,
        surface: PlaywrightSurfaceAdapter,
    ):
        self.logger = logger
        self.surface = surface
        self.control_owner = "automation"

    async def escalate(
        self,
        request: InterventionRequest,
    ) -> bool:

        self.control_owner = "human"

        self.logger.write({
            "type": "human_handoff_started",
            "run_id": request.run_id,
            "step_id": request.step_id,
            "reason": request.reason,
            "current_url": request.current_url,
            "screenshot_path": request.screenshot_path,
            "control_owner": self.control_owner,
        })

        print("\n=== HUMAN INTERVENTION REQUIRED ===")
        print(f"Run ID: {request.run_id}")
        print(f"Step: {request.step_id}")
        print(f"Reason: {request.reason}")
        print(f"Current URL: {request.current_url}")
        print(f"Evidence: {request.screenshot_path}")

        print(
            "\nUse the SAME open browser session "
            "to perform the required manual action."
        )

        input(
            "\nWhen the manual action is complete, "
            "press Enter to return control to automation..."
        )

        self.control_owner = "automation"

        self.logger.write({
            "type": "human_control_returned",
            "run_id": request.run_id,
            "step_id": request.step_id,
            "control_owner": self.control_owner,
        })

        if request.expected_after_handoff:

            verified = await self.surface.has_text(
                request.expected_after_handoff
            )

            self.logger.write({
                "type": "human_handoff_verification",
                "run_id": request.run_id,
                "step_id": request.step_id,
                "expected": request.expected_after_handoff,
                "verified": verified,
            })

            if not verified:
                return False

        self.logger.write({
            "type": "human_handoff_completed",
            "run_id": request.run_id,
            "step_id": request.step_id,
            "control_owner": "automation",
        })

        return True