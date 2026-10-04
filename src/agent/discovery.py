from __future__ import annotations

import asyncio
import json
import re

from uuid import uuid4

from openai import OpenAI

from src.agent.prompts import (
    DISCOVERY_SYSTEM_PROMPT,
)

from src.artifact.models import (
    ActionType,
    Capability,
    Checkpoint,
    ExpectedState,
    FieldSpec,
    Step,
    Target,
)

from src.artifact.storage import (
    save_capability,
)

from src.config import (
    OPENAI_API_KEY,
    OPENAI_MODEL,
)

from src.observability.logger import (
    RunLogger,
)

from src.safety.policy import (
    check_step,
)

from src.surface.playwright_adapter import (
    PlaywrightSurfaceAdapter,
)


# =========================================================
# DISCOVERY AGENT
# =========================================================


class DiscoveryAgent:

    def __init__(
        self,
        surface: PlaywrightSurfaceAdapter,
        logger: RunLogger,
    ):

        if not OPENAI_API_KEY:

            raise RuntimeError(
                "OPENAI_API_KEY is required "
                "for a genuine discovery run."
            )

        self.client = OpenAI(
            api_key=OPENAI_API_KEY,
        )

        self.surface = surface
        self.logger = logger

    # =====================================================
    # MODEL CALL
    # =====================================================

    def _ask_model_sync(
        self,
        goal: str,
        observation: dict,
        extracted_outputs: dict[str, str],
    ) -> dict:

        prompt = (
            f"Goal:\n"
            f"{goal}\n\n"
            f"Current UI observation:\n"
            f"{json.dumps(observation, indent=2)}\n\n"
            f"Values already extracted:\n"
            f"{json.dumps(extracted_outputs, indent=2)}"
        )

        response = self.client.responses.create(
            model=OPENAI_MODEL,
            input=[
                {
                    "role": "system",
                    "content": DISCOVERY_SYSTEM_PROMPT,
                },
                {
                    "role": "user",
                    "content": prompt,
                },
            ],
        )

        text = response.output_text.strip()

        try:

            decision = json.loads(text)

        except json.JSONDecodeError as exc:

            raise RuntimeError(
                "Discovery model returned invalid JSON: "
                f"{text}"
            ) from exc

        if not isinstance(decision, dict):

            raise RuntimeError(
                "Discovery model response must be "
                "a JSON object."
            )

        return decision

    async def _ask_model(
        self,
        goal: str,
        observation: dict,
        extracted_outputs: dict[str, str],
    ) -> dict:
        """
        Run the synchronous OpenAI SDK call in a worker
        thread so the async Playwright loop is not blocked.
        """

        return await asyncio.to_thread(
            self._ask_model_sync,
            goal,
            observation,
            extracted_outputs,
        )

    # =====================================================
    # DECISION VALIDATION
    # =====================================================

    def _validate_decision(
        self,
        decision: dict,
    ) -> ActionType:

        if "action" not in decision:

            raise RuntimeError(
                "Model decision is missing 'action'."
            )

        try:

            action = ActionType(
                decision["action"]
            )

        except ValueError as exc:

            raise RuntimeError(
                "Model returned unsupported action: "
                f"{decision.get('action')}"
            ) from exc

        if action in {
            ActionType.fill,
            ActionType.click,
            ActionType.extract,
        }:

            if not decision.get("target"):

                raise RuntimeError(
                    f"Action '{action.value}' "
                    "requires a target."
                )

        if action == ActionType.fill:

            if decision.get("value") is None:

                raise RuntimeError(
                    "Fill action requires a value."
                )

        if action == ActionType.extract:

            if not decision.get("output_name"):

                raise RuntimeError(
                    "Extract action requires "
                    "output_name."
                )

        return action

    # =====================================================
    # PARAMETERIZATION
    # =====================================================

    def _extract_member_id_from_goal(
        self,
        goal: str,
    ) -> str | None:
        """
        Extract the concrete member ID used during discovery.

        This avoids hard-coding a specific demo ID such as
        12345 in the discovery implementation.
        """

        patterns = [
            r"\bmember\s+(?:id\s+)?([A-Za-z0-9_-]+)\b",
            r"\bmember_id\s*[=:]\s*([A-Za-z0-9_-]+)\b",
        ]

        for pattern in patterns:

            match = re.search(
                pattern,
                goal,
                flags=re.IGNORECASE,
            )

            if match:
                return match.group(1)

        return None

    # =====================================================
    # MAIN DISCOVERY LOOP
    # =====================================================

    async def run(
        self,
        goal: str,
        max_steps: int = 12,
    ) -> Capability:

        run_id = uuid4().hex[:12]

        recorded_steps: list[Step] = []

        extracted_outputs: dict[str, str] = {}

        discovery_member_id = (
            self._extract_member_id_from_goal(
                goal
            )
        )

        completed = False

        self.logger.write({
            "type": "discovery_started",
            "run_id": run_id,
            "goal": goal,
        })

        # =================================================
        # OBSERVE -> DECIDE -> ACT
        # =================================================

        for index in range(max_steps):

            # ---------------------------------------------
            # OBSERVE
            # ---------------------------------------------

            observation = (
                await self.surface.observe()
            )

            self.logger.write({
                "type": "discovery_observation",
                "run_id": run_id,
                "step_number": index + 1,
                "observation": observation,
            })

            # ---------------------------------------------
            # DECIDE
            # ---------------------------------------------

            decision = await self._ask_model(
                goal=goal,
                observation=observation,
                extracted_outputs=extracted_outputs,
            )

            self.logger.write({
                "type": "model_decision",
                "run_id": run_id,
                "step_number": index + 1,
                "observation": observation,
                "decision": decision,
            })

            action = self._validate_decision(
                decision
            )

            # ---------------------------------------------
            # GOAL COMPLETE
            # ---------------------------------------------

            if action == ActionType.complete:

                if not extracted_outputs:

                    body = observation.get(
                        "text",
                        "",
                    )

                    known_business_outcome = (
                        "No member found."
                        in body
                    )

                    if not known_business_outcome:

                        raise RuntimeError(
                            "Model attempted to complete "
                            "discovery before extracting "
                            "the requested output."
                        )

                completed = True

                self.logger.write({
                    "type": "discovery_goal_completed",
                    "run_id": run_id,
                    "step_number": index + 1,
                    "outputs": extracted_outputs,
                })

                break

            # ---------------------------------------------
            # ESCALATION
            # ---------------------------------------------

            if action == ActionType.escalate:

                reason = decision.get(
                    "reasoning_summary",
                    "Discovery escalated",
                )

                self.logger.write({
                    "type": "discovery_escalated",
                    "run_id": run_id,
                    "step_number": index + 1,
                    "reason": reason,
                })

                raise RuntimeError(
                    reason
                )

            # ---------------------------------------------
            # CREATE TARGET
            # ---------------------------------------------

            target_data = (
                decision.get("target")
                or {}
            )

            target = (
                Target(**target_data)
                if target_data
                else None
            )

            value = decision.get(
                "value"
            )

            output_name = decision.get(
                "output_name"
            )

            step = Step(
                id=f"step_{index + 1}",
                action=action,
                target=target,
                value=(
                    str(value)
                    if value is not None
                    else None
                ),
                output_name=(
                    str(output_name)
                    if output_name
                    else None
                ),
            )

            # ---------------------------------------------
            # SAFETY CHECK BEFORE ACTING
            # ---------------------------------------------

            check_step(step)

            # ---------------------------------------------
            # ACT: FILL
            # ---------------------------------------------

            if action == ActionType.fill:

                assert target
                assert value is not None

                actual_value = str(value)

                await self.surface.fill(
                    target,
                    actual_value,
                )

                # -----------------------------------------
                # Convert the concrete discovery input into
                # a reusable invocation-time parameter.
                # -----------------------------------------

                if (
                    discovery_member_id
                    and actual_value.strip()
                    == discovery_member_id.strip()
                ):

                    step.value = "{{member_id}}"

            # ---------------------------------------------
            # ACT: CLICK
            # ---------------------------------------------

            elif action == ActionType.click:

                assert target

                await self.surface.click(
                    target
                )

            # ---------------------------------------------
            # ACT: EXTRACT
            # ---------------------------------------------

            elif action == ActionType.extract:

                assert target
                assert step.output_name

                extracted = (
                    await self.surface.read_text(
                        target
                    )
                )

                extracted_outputs[
                    step.output_name
                ] = extracted

                self.logger.write({
                    "type": "extracted_value",
                    "run_id": run_id,
                    "name": step.output_name,
                    "value": extracted,
                })

            # ---------------------------------------------
            # ACT: WAIT
            # ---------------------------------------------

            elif action == ActionType.wait:

                await self.surface.wait(
                    float(value or "1")
                )

            # ---------------------------------------------
            # SAVE STRUCTURED STEP
            # ---------------------------------------------

            recorded_steps.append(
                step
            )

            # ---------------------------------------------
            # SCREENSHOT EVIDENCE
            # ---------------------------------------------

            await self.surface.screenshot(
                "evidence/discovery/"
                f"{run_id}_"
                f"step_{index + 1}.png"
            )

        # =================================================
        # DISCOVERY VALIDATION
        # =================================================

        if not completed:

            raise RuntimeError(
                "Discovery reached the maximum "
                "number of steps without the model "
                "declaring the goal complete."
            )

        if not recorded_steps:

            raise RuntimeError(
                "Discovery completed without "
                "recording reusable steps."
            )

        # =================================================
        # NORMALIZE CLICK CHECKPOINT
        # =================================================
        #
        # These states belong to the known contract of our
        # demo surface. The LLM discovers the interaction
        # path; the capability compiler adds deterministic
        # replay verification and recovery metadata.
        # =================================================

        for step in recorded_steps:

            if step.action == ActionType.click:

                step.expected_state = (
                    ExpectedState(
                        kind="one_of_texts",
                        value=[
                            "Member Details",
                            "No member found",
                            "Permission denied",
                            "Temporary system error.",
                        ],
                    )
                )

                step.retry_count = 1

                break

        # =================================================
        # BUILD OUTPUT SCHEMA
        # =================================================

        output_specs: dict[
            str,
            FieldSpec,
        ] = {}

        for output_name in extracted_outputs:

            output_specs[
                output_name
            ] = FieldSpec(
                type="string",
                required=False,
                description=(
                    "Value extracted from the "
                    "application during capability "
                    "execution."
                ),
            )

        # The successful balance workflow should contain
        # an extracted output.
        if not output_specs:

            output_specs["balance"] = FieldSpec(
                type="string",
                required=False,
                description=(
                    "Savings balance when the "
                    "member exists."
                ),
            )

        # =================================================
        # BUILD CAPABILITY
        # =================================================

        capability = Capability(
            schema_version="1.0",

            name="lookup_member_balance",

            description=(
                "Look up a member and return "
                "the current savings balance."
            ),

            inputs={
                "member_id": FieldSpec(
                    type="string",
                    required=True,
                    description=(
                        "Member identifier supplied "
                        "at invocation time."
                    ),
                )
            },

            outputs=output_specs,

            steps=recorded_steps,

            checkpoint=Checkpoint(
                kind="one_of_texts",
                value=[
                    "Member Details",
                    "No member found",
                    "Permission denied",
                ],
            ),
        )

        # =================================================
        # SAVE CAPABILITY
        # =================================================

        artifact_path = (
            "artifacts/"
            "discovered_lookup_member_balance.json"
        )

        save_capability(
            capability,
            artifact_path,
        )

        self.logger.write({
            "type": "discovery_finished",
            "run_id": run_id,
            "artifact": artifact_path,
            "outputs": extracted_outputs,
            "recorded_step_count": len(
                recorded_steps
            ),
        })

        return capability