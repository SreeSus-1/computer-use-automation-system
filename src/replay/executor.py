from __future__ import annotations

import re
from uuid import uuid4

from src.artifact.models import (
    Capability,
    ReplayResult,
    ResultStatus,
    Step,
    Target,
)
from src.config import TARGET_URL
from src.escalation.handoff import (
    HandoffController,
    InterventionRequest,
)
from src.observability.logger import RunLogger
from src.safety.policy import check_step
from src.surface.playwright_adapter import PlaywrightSurfaceAdapter


PARAM = re.compile(
    r"^\{\{([a-zA-Z_][a-zA-Z0-9_]*)\}\}$"
)


class ReplayExecutor:

    def __init__(
        self,
        surface: PlaywrightSurfaceAdapter,
        logger: RunLogger,
        handoff: HandoffController | None = None,
    ):
        self.surface = surface
        self.logger = logger
        self.handoff = handoff

    # =====================================================
    # PARAMETER RESOLUTION
    # =====================================================

    def _resolve_value(
        self,
        value: str | None,
        inputs: dict[str, str],
    ) -> str | None:

        if value is None:
            return None

        match = PARAM.match(value)

        if match:
            key = match.group(1)

            if key not in inputs:
                raise ValueError(
                    f"Missing required input: {key}"
                )

            return inputs[key]

        return value

    # =====================================================
    # EXPECTED STATE VERIFICATION
    # =====================================================

    async def _verify_expected_state(
        self,
        step: Step,
    ) -> None:

        if (
            not step.expected_state
            or step.expected_state.kind == "none"
        ):
            return

        expected = step.expected_state

        if expected.kind == "text_present":

            ok = await self.surface.has_text(
                str(expected.value)
            )

            if not ok:
                raise RuntimeError(
                    "Expected text not found: "
                    f"{expected.value}"
                )

        elif expected.kind == "one_of_texts":

            assert isinstance(
                expected.value,
                list,
            )

            ok = False

            for value in expected.value:
                if await self.surface.has_text(value):
                    ok = True
                    break

            if not ok:
                raise RuntimeError(
                    "None of expected texts found: "
                    f"{expected.value}"
                )

        elif expected.kind == "url_contains":

            assert self.surface.page

            if (
                str(expected.value)
                not in self.surface.page.url
            ):
                raise RuntimeError(
                    "Expected URL to contain "
                    f"{expected.value}; "
                    f"got {self.surface.page.url}"
                )

    # =====================================================
    # TRANSIENT ERROR RECOVERY
    # =====================================================

    async def _retry_member_search(
        self,
        run_id: str,
        step: Step,
        member_id: str,
    ) -> bool:
        """
        Recover from the demo application's transient
        search failure.

        The retry budget comes directly from the saved
        capability artifact via step.retry_count.

        Replay therefore remains deterministic:
        no LLM decides whether or how many times to retry.
        """

        max_retries = step.retry_count

        self.logger.write({
            "type": "retry_policy_loaded",
            "run_id": run_id,
            "step_id": step.id,
            "max_retries": max_retries,
            "source": "capability_artifact",
        })

        if max_retries <= 0:

            self.logger.write({
                "type": "retry_not_allowed",
                "run_id": run_id,
                "step_id": step.id,
                "max_retries": max_retries,
                "reason": (
                    "Capability artifact does not permit "
                    "a retry for this step."
                ),
            })

            return False

        for attempt in range(
            1,
            max_retries + 1,
        ):

            self.logger.write({
                "type": "retry_started",
                "run_id": run_id,
                "step_id": step.id,
                "attempt": attempt,
                "max_retries": max_retries,
                "reason": "Temporary system error",
            })

            # Return to the known application start page.
            # surface.goto() performs URL safety checking.
            await self.surface.goto(TARGET_URL)

            # Re-enter the runtime parameter.
            await self.surface.fill(
                Target(
                    label="Member ID",
                ),
                member_id,
            )

            # Repeat the search action.
            await self.surface.click(
                Target(
                    role="button",
                    name="Search Member",
                )
            )

            body = await self.surface.body_text()

            if "Temporary system error." not in body:

                self.logger.write({
                    "type": "retry_succeeded",
                    "run_id": run_id,
                    "step_id": step.id,
                    "attempt": attempt,
                    "max_retries": max_retries,
                })

                return True

            self.logger.write({
                "type": "retry_failed",
                "run_id": run_id,
                "step_id": step.id,
                "attempt": attempt,
                "max_retries": max_retries,
            })

        self.logger.write({
            "type": "retry_exhausted",
            "run_id": run_id,
            "step_id": step.id,
            "max_retries": max_retries,
        })

        return False

    # =====================================================
    # MAIN REPLAY
    # =====================================================

    async def run(
        self,
        capability: Capability,
        inputs: dict[str, str],
    ) -> ReplayResult:

        run_id = uuid4().hex[:12]

        outputs: dict[str, str] = {}

        self.logger.write({
            "type": "replay_started",
            "run_id": run_id,
            "capability": capability.name,
            "inputs": inputs,
        })

        # =================================================
        # EXECUTE SAVED STEPS
        # =================================================

        for step in capability.steps:

            try:

                check_step(step)

                value = self._resolve_value(
                    step.value,
                    inputs,
                )

                self.logger.write({
                    "type": "step_started",
                    "run_id": run_id,
                    "step_id": step.id,
                    "action": step.action.value,
                    "target": (
                        step.target.model_dump()
                        if step.target
                        else None
                    ),
                })

                # -----------------------------------------
                # FILL
                # -----------------------------------------

                if step.action.value == "fill":

                    assert step.target
                    assert value is not None

                    await self.surface.fill(
                        step.target,
                        value,
                    )

                # -----------------------------------------
                # CLICK
                # -----------------------------------------

                elif step.action.value == "click":

                    assert step.target

                    await self.surface.click(
                        step.target
                    )

                # -----------------------------------------
                # READ / EXTRACT
                # -----------------------------------------

                elif step.action.value in {
                    "read",
                    "extract",
                }:

                    assert step.target

                    text = await self.surface.read_text(
                        step.target
                    )

                    if step.output_name:
                        outputs[
                            step.output_name
                        ] = text

                # -----------------------------------------
                # WAIT
                # -----------------------------------------

                elif step.action.value == "wait":

                    await self.surface.wait(
                        float(value or "1")
                    )

                # -----------------------------------------
                # EXPLICIT ESCALATION STEP
                # -----------------------------------------

                elif step.action.value == "escalate":

                    if not self.handoff:
                        raise RuntimeError(
                            "Human handoff requested "
                            "but no handoff controller "
                            "is configured."
                        )

                    screenshot = (
                        "evidence/replay/"
                        f"{run_id}_{step.id}_"
                        "handoff.png"
                    )

                    await self.surface.screenshot(
                        screenshot
                    )

                    assert self.surface.page

                    verified = await self.handoff.escalate(
                        InterventionRequest(
                            run_id=run_id,
                            step_id=step.id,
                            reason=(
                                value
                                or
                                "Manual intervention required"
                            ),
                            current_url=(
                                self.surface.page.url
                            ),
                            screenshot_path=screenshot,
                            expected_after_handoff=None,
                        )
                    )

                    if not verified:
                        raise RuntimeError(
                            "Human intervention "
                            "could not be verified."
                        )

                # -----------------------------------------
                # UNKNOWN ACTION
                # -----------------------------------------

                else:

                    raise RuntimeError(
                        "Unsupported replay action: "
                        f"{step.action.value}"
                    )

                # -----------------------------------------
                # VERIFY STEP CHECKPOINT
                # -----------------------------------------

                await self._verify_expected_state(
                    step
                )

                body = await self.surface.body_text()

                # =========================================
                # RECOVERABLE TRANSIENT CONDITION
                # =========================================

                if (
                    "Temporary system error."
                    in body
                ):

                    self.logger.write({
                        "type":
                            "recoverable_error_detected",
                        "run_id":
                            run_id,
                        "step_id":
                            step.id,
                        "code":
                            "TEMPORARY_SYSTEM_ERROR",
                        "message":
                            "Temporary system error "
                            "detected in the UI.",
                    })

                    screenshot = (
                        "evidence/replay/"
                        f"{run_id}_{step.id}_"
                        "recoverable_error.png"
                    )

                    await self.surface.screenshot(
                        screenshot
                    )

                    member_id = inputs.get(
                        "member_id"
                    )

                    if not member_id:
                        raise RuntimeError(
                            "Cannot retry member search "
                            "because member_id is missing."
                        )

                    recovered = (
                        await self._retry_member_search(
                            run_id=run_id,
                            step=step,
                            member_id=member_id,
                        )
                    )

                    # -------------------------------------
                    # RETRY EXHAUSTED
                    # -------------------------------------

                    if not recovered:

                        result = ReplayResult(
                            status=(
                                ResultStatus
                                .recoverable_error
                            ),
                            outputs=outputs,
                            code=(
                                "TRANSIENT_RETRY_"
                                "EXHAUSTED"
                            ),
                            message=(
                                "Temporary system error "
                                "persisted after the "
                                "artifact-defined retry "
                                "budget."
                            ),
                            step_id=step.id,
                            expected=(
                                "Transient condition "
                                "to clear after retry."
                            ),
                            observed=(
                                await self.surface
                                .body_text()
                            )[:1000],
                        )

                        self.logger.write({
                            "type":
                                "replay_finished",
                            "run_id":
                                run_id,
                            **result.model_dump(),
                        })

                        return result

                    # -------------------------------------
                    # RETRY SUCCEEDED
                    # -------------------------------------

                    self.logger.write({
                        "type":
                            "recoverable_error_recovered",
                        "run_id":
                            run_id,
                        "step_id":
                            step.id,
                    })

                    continue

                # =========================================
                # KNOWN BUSINESS OUTCOME
                # =========================================

                if "No member found." in body:

                    result = ReplayResult(
                        status=(
                            ResultStatus.business_outcome
                        ),
                        outputs=outputs,
                        code="MEMBER_NOT_FOUND",
                        message=(
                            "No member exists for "
                            "the supplied ID."
                        ),
                        step_id=step.id,
                    )

                    self.logger.write({
                        "type": "replay_finished",
                        "run_id": run_id,
                        **result.model_dump(),
                    })

                    return result

                # =========================================
                # HUMAN ESCALATION CONDITION
                # =========================================

                if "Permission denied." in body:

                    screenshot = (
                        "evidence/replay/"
                        f"{run_id}_"
                        "permission_denied.png"
                    )

                    await self.surface.screenshot(
                        screenshot
                    )

                    if not self.handoff:

                        result = ReplayResult(
                            status=ResultStatus.failure,
                            outputs=outputs,
                            code=(
                                "HUMAN_HANDOFF_"
                                "UNAVAILABLE"
                            ),
                            message=(
                                "Permission denial "
                                "requires human review, "
                                "but no handoff controller "
                                "is configured."
                            ),
                            step_id=step.id,
                        )

                        self.logger.write({
                            "type": "replay_finished",
                            "run_id": run_id,
                            **result.model_dump(),
                        })

                        return result

                    assert self.surface.page

                    # -------------------------------------
                    # AUTOMATION -> HUMAN
                    # -------------------------------------

                    completed = (
                        await self.handoff.escalate(
                            InterventionRequest(
                                run_id=run_id,
                                step_id=step.id,
                                reason=(
                                    "Permission denied; "
                                    "human review required"
                                ),
                                current_url=(
                                    self.surface.page.url
                                ),
                                screenshot_path=screenshot,
                                expected_after_handoff=(
                                    "Operator action "
                                    "completed."
                                ),
                            )
                        )
                    )

                    # -------------------------------------
                    # HUMAN DID NOT COMPLETE ACTION
                    # -------------------------------------

                    if not completed:

                        result = ReplayResult(
                            status=ResultStatus.failure,
                            outputs=outputs,
                            code=(
                                "HUMAN_INTERVENTION_"
                                "NOT_COMPLETED"
                            ),
                            message=(
                                "Control returned from "
                                "the human operator, but "
                                "the expected post-handoff "
                                "state was not observed."
                            ),
                            step_id=step.id,
                            expected=(
                                "Operator action "
                                "completed."
                            ),
                            observed=(
                                await self.surface
                                .body_text()
                            )[:1000],
                        )

                        self.logger.write({
                            "type": "replay_finished",
                            "run_id": run_id,
                            **result.model_dump(),
                        })

                        return result

                    # -------------------------------------
                    # HUMAN COMPLETED ACTION
                    # -------------------------------------

                    outputs[
                        "human_intervention"
                    ] = "completed"

                    result = ReplayResult(
                        status=(
                            ResultStatus.business_outcome
                        ),
                        outputs=outputs,
                        code=(
                            "HUMAN_INTERVENTION_"
                            "COMPLETED"
                        ),
                        message=(
                            "Human operator completed "
                            "the required manual review "
                            "and returned control to "
                            "automation."
                        ),
                        step_id=step.id,
                    )

                    self.logger.write({
                        "type": "replay_finished",
                        "run_id": run_id,
                        **result.model_dump(),
                    })

                    return result

                # -----------------------------------------
                # STEP SUCCESS LOG
                # -----------------------------------------

                self.logger.write({
                    "type": "step_completed",
                    "run_id": run_id,
                    "step_id": step.id,
                })

            # =============================================
            # HARD FAILURE
            # =============================================

            except Exception as exc:

                screenshot = (
                    "evidence/replay/"
                    f"{run_id}_"
                    f"{step.id}_failure.png"
                )

                try:

                    await self.surface.screenshot(
                        screenshot
                    )

                    observed = (
                        await self.surface.body_text()
                    )

                except Exception:

                    observed = (
                        "Unable to capture page state"
                    )

                result = ReplayResult(
                    status=ResultStatus.failure,
                    outputs=outputs,
                    code="REPLAY_STEP_FAILED",
                    message=str(exc),
                    step_id=step.id,
                    expected=(
                        step.expected_state.model_dump()
                        if step.expected_state
                        else None
                    ),
                    observed=observed[:1000],
                )

                self.logger.write({
                    "type": "replay_finished",
                    "run_id": run_id,
                    **result.model_dump(),
                })

                return result

        # =================================================
        # FINAL CAPABILITY CHECKPOINT
        # =================================================

        checkpoint = capability.checkpoint

        if checkpoint.kind == "text_present":

            ok = await self.surface.has_text(
                str(checkpoint.value)
            )

        elif checkpoint.kind == "one_of_texts":

            assert isinstance(
                checkpoint.value,
                list,
            )

            ok = False

            for value in checkpoint.value:

                if await self.surface.has_text(
                    value
                ):
                    ok = True
                    break

        elif checkpoint.kind == "url_contains":

            assert self.surface.page

            ok = (
                str(checkpoint.value)
                in self.surface.page.url
            )

        else:

            ok = False

        # =================================================
        # CHECKPOINT FAILURE
        # =================================================

        if not ok:

            result = ReplayResult(
                status=ResultStatus.failure,
                outputs=outputs,
                code="CHECKPOINT_FAILED",
                message=(
                    "Final capability checkpoint "
                    "was not satisfied."
                ),
            )

            self.logger.write({
                "type": "replay_finished",
                "run_id": run_id,
                **result.model_dump(),
            })

            return result

        # =================================================
        # SUCCESS
        # =================================================

        result = ReplayResult(
            status=ResultStatus.success,
            outputs=outputs,
        )

        self.logger.write({
            "type": "replay_finished",
            "run_id": run_id,
            **result.model_dump(),
        })

        return result