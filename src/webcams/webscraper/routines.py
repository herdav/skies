# src/webscraper/routines.py
"""Functions for downloading images and screenshots from various sources."""

import os
import re
import time
from datetime import datetime
from urllib.parse import urljoin, urlparse
from contextlib import contextmanager

import requests
import urllib3
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.action_chains import ActionChains

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": ("image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8"),
}


def _safe_get(url: str, *, timeout: int = 10, _retry: bool = False) -> requests.Response:
    """
    Perform a GET request.
    - First attempt validates TLS certificates (verify=True).
    - If an SSLCertVerificationError occurs, retry exactly once with verify=False.
    - Any other exception, or a second SSL failure, is raised to the caller.
    """
    try:
        return requests.get(url, headers=DEFAULT_HEADERS, timeout=timeout, verify=not _retry)
    except requests.exceptions.SSLError:
        if not _retry:
            host = urlparse(url).hostname or "<unknown host>"
            print(f"[warn] TLS validation failed for {host}; retrying without verification …")
            return _safe_get(url, timeout=timeout, _retry=True)
        raise


def fetch_html(url: str, timeout: int = 10) -> str:
    """Return the HTML body of *url* as text (SSL-tolerant)."""
    resp = _safe_get(url, timeout=timeout)
    resp.raise_for_status()
    return resp.text


def fetch_bytes(url: str, timeout: int = 10) -> bytes:
    """Return raw byte content of *url* (SSL-tolerant)."""
    resp = _safe_get(url, timeout=timeout)
    resp.raise_for_status()
    return resp.content


@contextmanager
def chrome_driver(add_args=None):
    """Context manager for creating and quitting a Chrome WebDriver."""
    options = webdriver.ChromeOptions()
    if add_args:
        for arg in add_args:
            options.add_argument(arg)
    driver = webdriver.Chrome(options=options)
    try:
        yield driver
    finally:
        driver.quit()


def save_screenshot(driver, image_id, output_folder="img", ext="png"):
    """Save a WebDriver screenshot to *output_folder* and return its path."""
    os.makedirs(output_folder, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    filename = f"{image_id}_{timestamp}.{ext}"
    filepath = os.path.join(output_folder, filename)
    driver.save_screenshot(filepath)
    return filepath


def save_bytes(data, image_id, ext, output_folder="img"):
    """Write *data* to disk and return the file path."""
    os.makedirs(output_folder, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    filename = f"{image_id}_{timestamp}.{ext}"
    filepath = os.path.join(output_folder, filename)
    with open(filepath, "wb") as fh:
        fh.write(data)
    return filepath


class SeleniumDownloader:
    """Download images or screenshots using Selenium flows."""

    @staticmethod
    def download_fatl(url, image_id, output_folder="img"):
        """Screenshot of the 'fatl' webcam."""
        with chrome_driver() as driver:
            driver.get(url)
            wait = WebDriverWait(driver, 10)

            # Dismiss cookie banner
            try:
                btn = wait.until(
                    EC.element_to_be_clickable((By.ID, "CybotCookiebotDialogBodyButtonDecline"))
                )
                btn.click()
            except Exception:
                pass

            # Close potential popup
            try:
                btn = wait.until(
                    EC.element_to_be_clickable((By.CSS_SELECTOR, "a.fancybox-item.fancybox-close"))
                )
                btn.click()
            except Exception:
                pass

            # Play video and switch to iframe
            btn = wait.until(
                EC.element_to_be_clickable(
                    (By.CSS_SELECTOR, "img.webcamPlayButton.showWebcamAtLarge")
                )
            )
            btn.click()
            iframe = wait.until(EC.presence_of_element_located((By.ID, "idIframe")))
            driver.switch_to.frame(iframe)

            # Hover over video to reveal full-screen control
            video = wait.until(EC.presence_of_element_located((By.ID, "fer_video")))
            ActionChains(driver).move_to_element(video).perform()

            # Full-screen
            fs_btn = wait.until(
                EC.element_to_be_clickable(
                    (By.CSS_SELECTOR, "div#fullscreen-button.fullscreentoggleiframe")
                )
            )
            fs_btn.click()
            time.sleep(4)

            # Remove overlays
            for sel in ["#video_logo", ".marquee-container", ".mainNavBTM", "#wetterWidget"]:
                driver.execute_script(
                    f"var el = document.querySelector('{sel}'); if (el) el.remove();"
                )

            return save_screenshot(driver, image_id, output_folder)

    @staticmethod
    def download_onkt(url, image_id, output_folder="img", preview_id="preview6"):
        """Screenshot of the 'onkt' webcam."""
        args = ["--disable-gpu", "--no-sandbox"]
        with chrome_driver(add_args=args) as driver:
            driver.get(url)
            wait = WebDriverWait(driver, 30)

            # Handle ad modal if displayed
            try:
                ad = driver.find_element(By.ID, "ad_modal")
                style = (ad.get_attribute("style") or "").replace(" ", "").lower()
                if "display:block" in style:
                    driver.find_element(By.ID, "img_ad").click()
            except Exception:
                pass

            # Click preview button
            try:
                btn = wait.until(EC.element_to_be_clickable((By.ID, preview_id)))
                btn.click()
            except Exception:
                pass

            # Force full-screen via JS
            try:
                wait.until(EC.presence_of_element_located((By.ID, "my_video_1_html5_api")))
                driver.execute_script(
                    """
                    var vid=document.getElementById('my_video_1_html5_api');
                    if(vid.requestFullscreen){vid.requestFullscreen();}
                    else if(vid.mozRequestFullScreen){vid.mozRequestFullScreen();}
                    else if(vid.webkitRequestFullscreen){vid.webkitRequestFullscreen();}
                    else if(vid.msRequestFullscreen){vid.msRequestFullscreen();}
                    """
                )
            except Exception:
                pass

            time.sleep(5)
            return save_screenshot(driver, image_id, output_folder)

    @staticmethod
    def download_rdpa(url, image_id, output_folder="img"):
        """Screenshot of the 'rdpa' webcam."""
        args = ["--headless", "--disable-gpu", "--no-sandbox"]
        with chrome_driver(add_args=args) as driver:
            driver.get(url)
            wait = WebDriverWait(driver, 15)
            wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "div.image-gallery-swipe")))
            img_el = wait.until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "img.image-gallery-image"))
            )
            img_url = img_el.get_attribute("src")
        data = fetch_bytes(img_url, timeout=10)
        return save_bytes(data, image_id, "jpg", output_folder)

    @staticmethod
    def download_rtsp(url, image_id, output_folder="img"):
        """Screenshot of the 'rtsp' webcam."""
        with chrome_driver() as driver:
            driver.get(url)
            wait = WebDriverWait(driver, 20)
            driver.execute_script(
                "document.querySelector('.control_wrapper').style.display='block';"
            )
            wait.until(EC.element_to_be_clickable((By.CLASS_NAME, "zoom"))).click()
            wait.until(EC.element_to_be_clickable((By.CLASS_NAME, "button_play_big"))).click()
            wait.until(EC.invisibility_of_element_located((By.CLASS_NAME, "preload")))
            elems = driver.find_elements(By.CLASS_NAME, "name_video")
            if elems:
                driver.execute_script("arguments[0].style.display='none';", elems[0])
            time.sleep(1)
            return save_screenshot(driver, image_id, output_folder)

    @staticmethod
    def download_snpa(url, image_id, output_folder="img"):
        """Screenshot of the 'snpa' webcam."""
        args = ["--disable-gpu", "--no-sandbox"]
        with chrome_driver(add_args=args) as driver:
            driver.get(url)
            wait = WebDriverWait(driver, 30)
            wait.until(EC.presence_of_element_located((By.ID, "video")))

            # Inject full-screen button
            inject = (
                "const btn=document.createElement('button');"
                "btn.id='fullscreenBtn';btn.innerText='Go Fullscreen';"
                "btn.onclick=function(){var d=document.getElementById('video');"
                "if(d.requestFullscreen) d.requestFullscreen();};"
                "document.body.appendChild(btn);"
            )
            driver.execute_script(inject)
            time.sleep(2)
            wait.until(EC.element_to_be_clickable((By.ID, "fullscreenBtn"))).click()
            time.sleep(5)
            return save_screenshot(driver, image_id, output_folder)

    @staticmethod
    def download_ufnt(url, image_id, output_folder="img"):
        """Screenshot of the 'ufnt' webcam."""
        with chrome_driver() as driver:
            driver.get(url)
            wait = WebDriverWait(driver, 30)
            iframe = wait.until(EC.presence_of_element_located((By.TAG_NAME, "iframe")))
            driver.switch_to.frame(iframe)
            wait.until(
                EC.element_to_be_clickable(
                    (By.CSS_SELECTOR, 'button[data-fullscreen][aria-label="fullscreen"]')
                )
            ).click()
            time.sleep(3)
            return save_screenshot(driver, image_id, output_folder)

    @staticmethod
    def download_usap(
        url,
        image_id,
        *,
        element_id="img-boreSite",
        tab_id="c-tab-11",
        wait_time=2,
        output_folder="img",
    ):
        """Screenshot of the 'usap' webcam."""
        args = ["--headless", "--disable-gpu", "--no-sandbox"]
        with chrome_driver(add_args=args) as driver:
            driver.get(url)
            WebDriverWait(driver, 5).until(
                EC.presence_of_all_elements_located((By.TAG_NAME, "body"))
            )
            time.sleep(wait_time)
            WebDriverWait(driver, 5).until(EC.element_to_be_clickable((By.ID, tab_id))).click()
            time.sleep(wait_time)
            img = driver.find_element(By.ID, element_id)
            img_url = urljoin(url, img.get_attribute("src"))
        data = fetch_bytes(img_url, timeout=15)
        return save_bytes(data, image_id, "jpg", output_folder)

    @staticmethod
    def download_wndy(url, image_id, output_folder="img"):
        """Screenshot of the 'wndy' webcam."""
        args = ["--disable-gpu", "--no-sandbox", "---enable-unsafe-swiftshader"]
        with chrome_driver(add_args=args) as driver:
            driver.get(url)
            wait = WebDriverWait(driver, 30)
            wait.until(EC.element_to_be_clickable((By.CLASS_NAME, "fullscreen-button"))).click()
            time.sleep(5)
            bg = wait.until(EC.presence_of_element_located((By.CLASS_NAME, "image")))
            style = bg.get_attribute("style")
            start = style.find("url(") + 4
            end = style.find(")", start)
            img_url = urljoin(driver.current_url, style[start:end].strip("\"'"))
        data = fetch_bytes(img_url, timeout=10)
        return save_bytes(data, image_id, "jpg", output_folder)

    @staticmethod
    def download_ytbe(video_url, image_id, output_folder="img"):
        """Screenshot of the 'ytbe' (YouTube) webcam."""
        args = ["--disable-gpu", "--disable-software-rasterizer"]
        with chrome_driver(add_args=args) as browser:
            browser.get(video_url)
            actions = ActionChains(browser)

            # Embedded videos need a click before key presses work
            if "/embed/" in video_url:
                actions.move_by_offset(
                    browser.get_window_size()["width"] // 2,
                    browser.get_window_size()["height"] // 2,
                ).click().perform()
                time.sleep(1)
                actions.send_keys(" ").perform()
                time.sleep(1)
                actions.send_keys("f").perform()  # full-screen
                time.sleep(5)
            else:
                # Dismiss YouTube cookie dialog if present
                try:
                    WebDriverWait(browser, 5).until(
                        EC.presence_of_element_located((By.ID, "dialog"))
                    )
                    btn = WebDriverWait(browser, 5).until(
                        EC.element_to_be_clickable(
                            (By.XPATH, "//button[.//span[text()='Reject all']]")
                        )
                    )
                    btn.click()
                    time.sleep(1)
                except Exception:
                    pass
                actions.send_keys("f").perform()
                time.sleep(3)

            return save_screenshot(browser, image_id, output_folder)


class ImageDownloader:
    """Download images with plain HTTP requests."""

    @staticmethod
    def download_stat(url, image_id, output_folder="img"):
        """Download a static image and save it locally."""
        try:
            data = fetch_bytes(url, timeout=15)
            ext = url.rsplit(".", 1)[-1].split("?")[0]  # strip query string if present
            return save_bytes(data, image_id, ext, output_folder)
        except Exception as exc:
            print(f"Error downloading static image: {exc}")
            return None

    @staticmethod
    def download_dyna(
        url,
        image_id,
        img_format,
        src_pattern=None,
        element_class=None,
        element_id=None,
        output_folder="img",
    ):
        """
        Download an image from a dynamic web page.

        The first <img> tag that matches *src_pattern*, *element_class*
        or *element_id* wins.
        """
        if not url or not image_id:
            return None

        try:
            html = fetch_html(url, timeout=15)
        except Exception as exc:
            print(f"Request failed: {exc}")
            return None

        soup = BeautifulSoup(html, "html.parser")

        if element_class:
            tags = soup.find_all("img", class_=element_class)
        elif element_id:
            tags = soup.find_all("img", id=element_id)
        else:
            tags = soup.find_all("img")

        for img in tags:
            src = img.get("src")
            if not src:
                continue
            full = urljoin(url, src)

            if src_pattern and not re.search(src_pattern, full):
                continue
            if not full.lower().endswith(f".{img_format}"):
                continue

            try:
                data = fetch_bytes(full, timeout=15)
            except Exception as exc:
                print(f"Download failed: {exc}")
                return None

            return save_bytes(data, image_id, img_format, output_folder)

        return None
        
