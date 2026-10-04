from __future__ import annotations

import asyncio
from pathlib import Path

from playwright.async_api import (
    async_playwright,
    Page,
)

from src.artifact.models import Target
from src.safety.policy import check_url


class PlaywrightSurfaceAdapter:

    def __init__(
        self,
        headless: bool = False,
    ):
        self.headless = headless
        self._pw = None
        self.browser = None
        self.page: Page | None = None

    # =====================================================
    # BROWSER LIFECYCLE
    # =====================================================

    async def start(
        self,
        url: str,
    ):
        """
        Start Playwright and open the initial allowed URL.
        """

        check_url(url)

        self._pw = await async_playwright().start()

        self.browser = await self._pw.chromium.launch(
            headless=self.headless
        )

        context = await self.browser.new_context()

        self.page = await context.new_page()

        await self.page.goto(url)

        await self.page.wait_for_load_state(
            "domcontentloaded"
        )

        return self

    async def close(self):
        """
        Close the browser and Playwright runtime.
        """

        if self.browser:
            await self.browser.close()

        if self._pw:
            await self._pw.stop()

    # =====================================================
    # SAFE NAVIGATION
    # =====================================================

    async def goto(
        self,
        url: str,
    ) -> None:
        """
        Navigate only after the URL passes the safety policy.
        """

        assert self.page

        check_url(url)

        await self.page.goto(url)

        await self.page.wait_for_load_state(
            "domcontentloaded"
        )

    # =====================================================
    # OBSERVATION
    # =====================================================

    async def observe(self) -> dict:
        """
        Return a structured observation of the current UI.

        Visible page text alone is not sufficient because
        values inside form inputs are not normally included
        in body.inner_text().

        Discovery therefore receives:

        - URL
        - page title
        - visible text
        - input fields and their current values
        - buttons
        - links
        - useful visible elements with IDs

        This gives the model enough state to determine what
        has already happened without exposing application APIs.
        """

        assert self.page

        body_text = (
            await self.page
            .locator("body")
            .inner_text()
        )[:6000]

        # -------------------------------------------------
        # INPUTS
        # -------------------------------------------------

        inputs = []

        input_locator = self.page.locator(
            "input, textarea, select"
        )

        input_count = await input_locator.count()

        for index in range(input_count):

            element = input_locator.nth(index)

            try:
                tag_name = await element.evaluate(
                    "(el) => el.tagName.toLowerCase()"
                )

                element_id = (
                    await element.get_attribute("id")
                )

                name = (
                    await element.get_attribute("name")
                )

                input_type = (
                    await element.get_attribute("type")
                )

                placeholder = (
                    await element.get_attribute(
                        "placeholder"
                    )
                )

                aria_label = (
                    await element.get_attribute(
                        "aria-label"
                    )
                )

                # -----------------------------------------
                # Current value
                # -----------------------------------------

                if tag_name == "select":

                    value = await element.input_value()

                else:

                    value = await element.input_value()

                # -----------------------------------------
                # Try to determine associated label.
                # -----------------------------------------

                label = None

                if element_id:

                    matching_label = (
                        self.page.locator(
                            f'label[for="{element_id}"]'
                        )
                    )

                    if await matching_label.count() > 0:

                        label = (
                            await matching_label
                            .first
                            .inner_text()
                        ).strip()

                # Fall back to aria-label if necessary.
                if not label and aria_label:
                    label = aria_label

                inputs.append({
                    "tag": tag_name,
                    "type": input_type,
                    "label": label,
                    "name": name,
                    "id": element_id,
                    "placeholder": placeholder,
                    "value": value,
                })

            except Exception:

                # Observation should be best-effort.
                # One unusual element should not prevent
                # discovery from seeing the rest of the UI.
                continue

        # -------------------------------------------------
        # BUTTONS
        # -------------------------------------------------

        buttons = []

        button_locator = self.page.locator(
            'button, input[type="button"], '
            'input[type="submit"]'
        )

        button_count = await button_locator.count()

        for index in range(button_count):

            element = button_locator.nth(index)

            try:

                tag_name = await element.evaluate(
                    "(el) => el.tagName.toLowerCase()"
                )

                if tag_name == "input":

                    button_name = (
                        await element.get_attribute("value")
                        or ""
                    )

                else:

                    button_name = (
                        await element.inner_text()
                    ).strip()

                buttons.append({
                    "role": "button",
                    "name": button_name,
                })

            except Exception:
                continue

        # -------------------------------------------------
        # LINKS
        # -------------------------------------------------

        links = []

        link_locator = self.page.locator("a")

        link_count = await link_locator.count()

        for index in range(link_count):

            element = link_locator.nth(index)

            try:

                link_text = (
                    await element.inner_text()
                ).strip()

                href = (
                    await element.get_attribute("href")
                )

                if link_text:

                    links.append({
                        "role": "link",
                        "name": link_text,
                        "href": href,
                    })

            except Exception:
                continue

        # -------------------------------------------------
        # ELEMENTS WITH IDs
        # -------------------------------------------------
        #
        # This is especially useful for extraction.
        #
        # Example:
        #
        # <span id="savings_balance">$4,280.31</span>
        #
        # becomes:
        #
        # {
        #   "css": "#savings_balance",
        #   "text": "$4,280.31"
        # }
        #
        # The LLM can therefore discover a stable extraction
        # target without inventing a CSS selector.
        # -------------------------------------------------

        identified_elements = []

        id_locator = self.page.locator("[id]")

        id_count = await id_locator.count()

        for index in range(id_count):

            element = id_locator.nth(index)

            try:

                element_id = (
                    await element.get_attribute("id")
                )

                if not element_id:
                    continue

                tag_name = await element.evaluate(
                    "(el) => el.tagName.toLowerCase()"
                )

                # Inputs are already represented above.
                if tag_name in {
                    "input",
                    "textarea",
                    "select",
                }:
                    continue

                text = (
                    await element.inner_text()
                ).strip()

                if not text:
                    continue

                identified_elements.append({
                    "css": f"#{element_id}",
                    "text": text[:1000],
                })

            except Exception:
                continue

        # -------------------------------------------------
        # COMPLETE OBSERVATION
        # -------------------------------------------------

        return {
            "url": self.page.url,
            "title": await self.page.title(),
            "text": body_text,
            "inputs": inputs,
            "buttons": buttons,
            "links": links,
            "identified_elements": identified_elements,
        }

    # =====================================================
    # LOCATOR RESOLUTION
    # =====================================================

    def _locator(
        self,
        target: Target,
    ):
        """
        Resolve a target using semantic selectors first.

        Priority:

        1. accessibility role + name
        2. associated label
        3. visible text
        4. CSS selector fallback
        """

        assert self.page

        # -------------------------------------------------
        # Preferred:
        # accessibility role + accessible name
        # -------------------------------------------------

        if target.role and target.name:

            return self.page.get_by_role(
                target.role,
                name=target.name,
            )

        # -------------------------------------------------
        # Second:
        # associated form label
        # -------------------------------------------------

        if target.label:

            return self.page.get_by_label(
                target.label
            )

        # -------------------------------------------------
        # Third:
        # visible text
        # -------------------------------------------------

        if target.text:

            return self.page.get_by_text(
                target.text,
                exact=False,
            )

        # -------------------------------------------------
        # Final fallback:
        # CSS selector
        # -------------------------------------------------

        if target.css:

            return self.page.locator(
                target.css
            )

        raise ValueError(
            "No usable locator in target: "
            f"{target.model_dump()}"
        )

    # =====================================================
    # UI ACTIONS
    # =====================================================

    async def click(
        self,
        target: Target,
    ) -> None:

        await self._locator(
            target
        ).click()

    async def fill(
        self,
        target: Target,
        value: str,
    ) -> None:

        await self._locator(
            target
        ).fill(value)

    async def read_text(
        self,
        target: Target,
    ) -> str:

        text = await self._locator(
            target
        ).inner_text()

        return text.strip()

    async def wait(
        self,
        seconds: float,
    ) -> None:

        await asyncio.sleep(seconds)

    # =====================================================
    # EVIDENCE
    # =====================================================

    async def screenshot(
        self,
        path: str | Path,
    ) -> None:

        assert self.page

        path = Path(path)

        path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        await self.page.screenshot(
            path=str(path),
            full_page=True,
        )

    # =====================================================
    # STATE CHECKS
    # =====================================================

    async def has_text(
        self,
        text: str,
    ) -> bool:

        assert self.page

        count = await self.page.get_by_text(
            text,
            exact=False,
        ).count()

        return count > 0

    async def body_text(self) -> str:
        """
        Return all visible body text from the current page.
        """

        assert self.page

        return await self.page.locator(
            "body"
        ).inner_text()