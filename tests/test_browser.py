import asyncio

from src.surface.playwright_adapter import (
    PlaywrightSurfaceAdapter
)

from src.artifact.models import Target


async def main():

    surface = PlaywrightSurfaceAdapter(
        headless=False
    )

    await surface.start(
        "http://127.0.0.1:8000"
    )

    print("Browser opened successfully.")

    observation = await surface.observe()

    print("\nCurrent page:")
    print(observation)

    member_field = Target(
        label="Member ID"
    )

    await surface.fill(
        member_field,
        "12345"
    )

    print("\nEntered member ID.")

    search_button = Target(
        role="button",
        name="Search Member"
    )

    await surface.click(
        search_button
    )

    print("Clicked Search Member.")

    await asyncio.sleep(2)

    final_state = await surface.observe()

    print("\nAfter search:")
    print(final_state)

    await surface.screenshot(
        "evidence/playwright_test.png"
    )

    print(
        "\nScreenshot saved to "
        "evidence/playwright_test.png"
    )

    input(
        "\nPress Enter to close browser..."
    )

    await surface.close()


if __name__ == "__main__":

    asyncio.run(main())