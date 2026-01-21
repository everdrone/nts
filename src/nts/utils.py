import functools
import glob
import os
from typing import Callable, TypeVar

import magic
from playwright.sync_api import (
    Browser,
    BrowserContext,
    Page,
    ViewportSize,
    sync_playwright,
)

ROOT_PATH = os.getenv("PIXI_PROJECT_ROOT", "")
assert ROOT_PATH


def find_file(glob_pattern, mime, ext=""):
    ret = []
    for p in glob.glob(glob_pattern):
        mmime, mext = magic.from_file(p, mime=True).split("/")
        if mmime == mime and mext == ext:
            ret.append(p)
    return ret
    # return [
    #     p
    #     for p in glob.glob(glob_pattern)
    #     if magic.from_file(p, mime=True).split("/")[0] in mime
    #     and magic.from_file(p, mime=True).split("/")[1] in ext
    # ]


T = TypeVar("T")


class PlaywrightContext:
    def __init__(
        self,
        headless: bool = False,
        slow_mo: int = 150,
        auth_filepath: str = "",
        auth_login_url: str = "",
        viewport: ViewportSize = {"width": int(1918 / 2), "height": int(1029)},
    ):
        self.headless = headless
        self.slow_mo = slow_mo
        self.auth_filepath = auth_filepath
        self.auth_login_url = auth_login_url
        self.viewport = viewport

    def __call__(self, func: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> T:
            with sync_playwright() as p:
                browser = p.chromium.launch(
                    headless=self.headless,
                    slow_mo=self.slow_mo,
                )
                context = self.get_authenticated_context(browser)
                result = func(self, context, *args, **kwargs)
                browser.close()
                return result

        return wrapper

    def goto_retry(self, page: Page, url: str, max_retries=3, **kwargs):
        for attempt in range(1, max_retries + 1):
            try:
                # print(f"Attempt {attempt} for {url}")
                result = page.goto(url, **kwargs)
                # print(f"Success on attempt {attempt}")
                return result
            except Exception as e:
                print(f"Attempt {attempt} failed: {e}")
                if attempt == max_retries:
                    print("Max retries reached. Raising the last exception.")
                    return
                print("Retrying...")
        raise Exception("Navigation failed after retries")

    def get_authenticated_context(
        self,
        browser: Browser,
    ):
        if os.path.exists(self.auth_filepath):
            print("Found existing auth — restoring session...")
            context = browser.new_context(
                storage_state=self.auth_filepath,
                viewport=self.viewport,
            )
        else:
            print("No auth found — please log in.")
            context = browser.new_context()
            page = context.new_page()
            self.goto_retry(page, self.auth_login_url)
            input("Press Enter after logging in...")
            context.storage_state(
                path=self.auth_filepath,
                indexed_db=True,
            )
            print(f"Auth saved to {self.auth_filepath}")
            context = browser.new_context(
                storage_state=self.auth_filepath,
                viewport=self.viewport,
            )
        return context
