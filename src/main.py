from __future__ import annotations

import argparse
import asyncio

from src.agent.discovery import DiscoveryAgent
from src.artifact.storage import load_capability
from src.config import TARGET_URL
from src.escalation.handoff import HandoffController
from src.observability.logger import RunLogger
from src.replay.executor import ReplayExecutor
from src.surface.playwright_adapter import PlaywrightSurfaceAdapter


# =========================================================
# DETERMINISTIC REPLAY
# =========================================================

async def run_replay(args) -> None:
    """
    Execute a previously saved capability artifact.

    Important:
    Replay does NOT use an LLM to decide what action to take.
    The steps come entirely from the saved capability artifact.
    """

    logger = RunLogger(
        "evidence/replay/replay.jsonl"
    )

    surface = PlaywrightSurfaceAdapter(
        headless=False
    )

    await surface.start(TARGET_URL)

    # The handoff controller receives the SAME live browser
    # surface used by automation.
    #
    # This allows:
    # automation -> human -> automation
    # without creating a new browser session.
    handoff = HandoffController(
        logger=logger,
        surface=surface,
    )

    try:
        capability = load_capability(
            args.artifact
        )

        executor = ReplayExecutor(
            surface=surface,
            logger=logger,
            handoff=handoff,
        )

        result = await executor.run(
            capability=capability,
            inputs={
                "member_id": args.member_id,
            },
        )

        print("\n=== REPLAY RESULT ===")

        print(
            result.model_dump_json(
                indent=2
            )
        )

    finally:
        input(
            "\nPress Enter to close "
            "the browser... "
        )

        await surface.close()


# =========================================================
# LLM-DRIVEN DISCOVERY
# =========================================================

async def run_discovery(args) -> None:
    """
    Run the LLM-driven discovery process.

    During discovery the model observes the current UI,
    chooses an action, performs it through the surface
    adapter, and records reusable steps.

    The resulting capability can later be replayed without
    an LLM.
    """

    logger = RunLogger(
        "evidence/discovery/discovery.jsonl"
    )

    surface = PlaywrightSurfaceAdapter(
        headless=False
    )

    await surface.start(TARGET_URL)

    try:
        agent = DiscoveryAgent(
            surface=surface,
            logger=logger,
        )

        capability = await agent.run(
            goal=args.goal
        )

        print(
            "\n=== DISCOVERED CAPABILITY ==="
        )

        print(
            capability.model_dump_json(
                indent=2
            )
        )

    finally:
        input(
            "\nPress Enter to close "
            "the browser... "
        )

        await surface.close()


# =========================================================
# COMMAND-LINE INTERFACE
# =========================================================

def build_parser() -> argparse.ArgumentParser:

    parser = argparse.ArgumentParser(
        description=(
            "Computer-use automation system: "
            "LLM discovery + deterministic replay"
        )
    )

    subparsers = parser.add_subparsers(
        dest="command",
        required=True,
    )

    # -----------------------------------------------------
    # REPLAY COMMAND
    # -----------------------------------------------------

    replay_parser = subparsers.add_parser(
        "replay",
        help=(
            "Replay a saved capability "
            "without LLM decisions."
        ),
    )

    replay_parser.add_argument(
        "--artifact",
        default=(
            "artifacts/"
            "lookup_member_balance.json"
        ),
        help=(
            "Path to the capability artifact."
        ),
    )

    replay_parser.add_argument(
        "--member-id",
        required=True,
        help=(
            "Member ID supplied to the "
            "capability at runtime."
        ),
    )

    # -----------------------------------------------------
    # DISCOVERY COMMAND
    # -----------------------------------------------------

    discovery_parser = subparsers.add_parser(
        "discover",
        help=(
            "Run genuine LLM-driven discovery "
            "against the live UI."
        ),
    )

    discovery_parser.add_argument(
        "--goal",
        required=True,
        help=(
            "Natural-language goal for "
            "the discovery agent."
        ),
    )

    return parser


# =========================================================
# ENTRY POINT
# =========================================================

def main() -> None:

    parser = build_parser()

    args = parser.parse_args()

    if args.command == "replay":

        asyncio.run(
            run_replay(args)
        )

    elif args.command == "discover":

        asyncio.run(
            run_discovery(args)
        )


if __name__ == "__main__":
    main()