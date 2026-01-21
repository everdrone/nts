import functools
import glob
from typing import Callable, TypeVar

import magic
from playwright.sync_api import BrowserContext, Page, sync_playwright


def find_file(glob_pattern, mime):
    return [
        p
        for p in glob.glob(glob_pattern)
        if magic.from_file(p, mime=True).split("/")[0] in mime
    ]


T = TypeVar("T")


class PlaywrightContext:
    def __init__(self, headless: bool = False, slow_mo: int = 150):
        self.headless = headless
        self.slow_mo = slow_mo

    def __call__(self, func: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> T:
            with sync_playwright() as p:
                browser = p.chromium.launch(
                    headless=self.headless, slow_mo=self.slow_mo
                )
                context = browser.new_context()
                # context = get_authenticated_context(browser)
                # page = context.new_page()
                # Pass context/page as first argument after self (if method) or as first argument
                result = func(context, *args, **kwargs)
                browser.close()
                return result

        return wrapper


def goto_retry(page: Page, url, max_retries=3, **kwargs):
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
