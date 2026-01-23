import glob
import os
import time
from typing import NamedTuple
from urllib import request as urllib_request

import magic
import requests
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


def get_image(image_url: str):
    image_type = ""
    image = None
    if image_url:
        image = urllib_request.urlopen(image_url)
        image_type = image.info().get_content_type()  ## image/{format}
        # image_type = f"{osp.splitext(image_url)[-1]}"
        image = image.read()
        print(f"got {image_type} from {image_url}")
        return image, image_type.split("/")[-1]
    else:
        print("no image_url found")
        return None, ""


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
        self.browser: Browser
        self.context: BrowserContext
        self.page: Page

    def __enter__(self):
        self._pw = sync_playwright().start()
        self.browser = self._pw.chromium.launch(
            headless=self.headless,
            slow_mo=self.slow_mo,
        )
        self.context = self.get_authenticated_context(self.browser)
        # self.page = self.context.new_page()
        return self

    def __exit__(self):
        if self.browser:
            self.browser.close()
        self._pw.stop()

    def get_authenticated_context(self, browser: Browser):
        if os.path.exists(self.auth_filepath):
            print("Found existing auth — restoring session...")
            context = browser.new_context(
                storage_state=self.auth_filepath,
                viewport=self.viewport,
            )
        elif self.auth_login_url:
            print("No auth found — please log in.")
            context = browser.new_context()
            page = context.new_page()
            self.goto_retry(page, self.auth_login_url)
            input("Press Enter after logging in...")
            context.storage_state(path=self.auth_filepath)
            print(f"Auth saved to {self.auth_filepath}")
            context = browser.new_context(
                storage_state=self.auth_filepath,
                viewport=self.viewport,
            )
        else:
            context = browser.new_context()
        return context

    def goto_retry(self, page: Page, url: str, max_retries=3, **kwargs):
        for attempt in range(1, max_retries + 1):
            try:
                result = page.goto(url, **kwargs)
                return result
            except Exception as e:
                print(f"Attempt {attempt} failed: {e}")
                if attempt == max_retries:
                    return
                print("Retrying...")

    def find_element(self, selector: str, timeout: int = 30000):
        if not hasattr(self, "pw_ctx") or not self.page:
            raise RuntimeError("Page not initialized. Call get_sourced first.")

        element = self.page.wait_for_selector(
            selector, state="visible", timeout=timeout
        )
        return element


class RequestResult(NamedTuple):
    success: bool
    response: requests.Response = None
    error: str = None
    status_code: int = None


def safe_request(
    method: str,
    url: str,
    max_retries: int = 4,
    delay: float = 5.0,
    timeout: int = 10,
    **kwargs,
) -> RequestResult:
    """
    request wrapper

    Returns:
        RequestResult with success flag, response object, error message, and status code
    """
    if not url:
        return RequestResult(success=False)

    for attempt in range(max_retries + 1):
        try:
            response = requests.request(method.upper(), url, timeout=timeout, **kwargs)

            if response.status_code < 400:
                return RequestResult(
                    success=True, response=response, status_code=response.status_code
                )

            if response.status_code == 404:
                error_msg = f"404 Not Found: {url}"
            elif response.status_code == 403:
                error_msg = f"403 Forbidden: Access denied for {url}"
            elif response.status_code == 429:
                error_msg = f"429 Too Many Requests: Rate limited for {url}"
            else:
                error_msg = f"HTTP {response.status_code}: Request failed for {url}"

            print(f"{error_msg}, attempt {attempt + 1}/{max_retries + 1}")

            if 400 <= response.status_code < 500:
                return RequestResult(
                    success=False,
                    response=response,
                    error=error_msg,
                    status_code=response.status_code,
                )

        except requests.exceptions.Timeout:
            error_msg = f"Timeout on attempt {attempt + 1}/{max_retries + 1} for {url}"
            print(error_msg)
        except requests.exceptions.ConnectionError:
            error_msg = (
                f"Connection error on attempt {attempt + 1}/{max_retries + 1} for {url}"
            )
            print(error_msg)
        except requests.exceptions.RequestException as e:
            error_msg = (
                f"Request error on attempt {attempt + 1}/{max_retries + 1}: {str(e)}"
            )
            print(error_msg)

        if attempt < max_retries:
            time.sleep(delay)

    error_msg = f"All {max_retries + 1} attempts failed for {method.upper()} {url}"
    print(error_msg)
    return RequestResult(success=False, error=error_msg, status_code=None)


def safe_get(
    url: str,
    max_retries: int = 4,
    delay: float = 5.0,
    timeout: int = 10,
    **kwargs,
) -> RequestResult:
    return safe_request("get", url, max_retries, delay, timeout, **kwargs)
