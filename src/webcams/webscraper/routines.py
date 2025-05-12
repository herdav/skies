# src/webscraper/routines.py
"""Functions for downloading images from various sources."""

import os
import re
import time
from datetime import datetime
from urllib.parse import urljoin
from contextlib import contextmanager

import requests
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.action_chains import ActionChains

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
}


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
    """
    Save a screenshot from the WebDriver to the specified folder.
    Returns the filepath of the saved screenshot.
    """
    os.makedirs(output_folder, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    filename = f"{image_id}_{timestamp}.{ext}"
    filepath = os.path.join(output_folder, filename)
    driver.save_screenshot(filepath)
    print("boom")
    return filepath


def fetch_bytes(url, headers=None, timeout=10, verify=False):
    """Fetch raw bytes from a URL using HTTP GET."""
    resp = requests.get(url, headers=headers or DEFAULT_HEADERS, timeout=timeout, verify=verify)
    resp.raise_for_status()
    return resp.content


def save_bytes(data, image_id, ext, output_folder="img"):
    """Save raw bytes (e.g. image content) to a file and return its path."""
    os.makedirs(output_folder, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    filename = f"{image_id}_{timestamp}.{ext}"
    filepath = os.path.join(output_folder, filename)
    with open(filepath, "wb") as f:
        f.write(data)
    return filepath


class SeleniumDownloader:
    """Class for downloading images via Selenium-based flows."""

    @staticmethod
    def download_fatl(url, image_id, output_folder="img"):
        """Download a screenshot from the fatl webcam."""
        with chrome_driver() as driver:
            driver.get(url)
            wait = WebDriverWait(driver, 10)
            # Decline cookie banner
            try:
                btn = wait.until(
                    EC.element_to_be_clickable((By.ID, "CybotCookiebotDialogBodyButtonDecline"))
                )
                btn.click()
            except Exception:
                pass
            # Close popup if present
            try:
                btn = wait.until(
                    EC.element_to_be_clickable((By.CSS_SELECTOR, "a.fancybox-item.fancybox-close"))
                )
                btn.click()
            except Exception:
                pass
            # Click play button
            btn = wait.until(
                EC.element_to_be_clickable(
                    (By.CSS_SELECTOR, "img.webcamPlayButton.showWebcamAtLarge")
                )
            )
            btn.click()
            # Switch to iframe
            iframe = wait.until(EC.presence_of_element_located((By.ID, "idIframe")))
            driver.switch_to.frame(iframe)
            # Hover over video to reveal fullscreen control
            video = wait.until(EC.presence_of_element_located((By.ID, "fer_video")))
            ActionChains(driver).move_to_element(video).perform()
            # Click fullscreen button
            fs_btn = wait.until(
                EC.element_to_be_clickable(
                    (By.CSS_SELECTOR, "div#fullscreen-button.fullscreentoggleiframe")
                )
            )
            fs_btn.click()
            # Wait for video to load
            time.sleep(4)
            # Remove unwanted elements
            for sel in ["#video_logo", ".marquee-container", ".mainNavBTM", "#wetterWidget"]:
                driver.execute_script(
                    f"var el = document.querySelector('{sel}'); if (el) el.remove();"
                )
            return save_screenshot(driver, image_id, output_folder)

    @staticmethod
    def download_onkt(url, image_id, output_folder="img", preview_id="preview6"):
        """Download a screenshot from the onkt webcam."""
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
            # Set video to fullscreen via JS
            try:
                wait.until(EC.presence_of_element_located((By.ID, "my_video_1_html5_api")))
                driver.execute_script("""
                    var vid = document.getElementById('my_video_1_html5_api');
                    if (vid.requestFullscreen) vid.requestFullscreen();
                    else if (vid.mozRequestFullScreen) vid.mozRequestFullScreen();
                    else if (vid.webkitRequestFullscreen) vid.webkitRequestFullscreen();
                    else if (vid.msRequestFullscreen) vid.msRequestFullscreen();
                """)
            except Exception:
                pass
            time.sleep(5)
            return save_screenshot(driver, image_id, output_folder)

    @staticmethod
    def download_rdpa(url, image_id, output_folder="img"):
        """Download a screenshot from the rdpa webcam."""
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
        """Download a screenshot from the rtsp webcam."""
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
        """Download a screenshot from the snpa webcam."""
        args = ["--disable-gpu", "--no-sandbox"]
        with chrome_driver(add_args=args) as driver:
            driver.get(url)
            wait = WebDriverWait(driver, 30)
            wait.until(EC.presence_of_element_located((By.ID, "video")))
            # Inject fullscreen button
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
        """Download a screenshot from the ufnt webcam."""
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
        """Download a screenshot from the usap webcam."""
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
        """Download a screenshot from the wndy webcam."""
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
        """Download a screenshot from the ytbe webcam."""
        args = ["--disable-gpu", "--disable-software-rasterizer"]
        with chrome_driver(add_args=args) as browser:
            browser.get(video_url)
            actions = ActionChains(browser)
            if "/embed/" in video_url:
                actions.move_by_offset(
                    browser.get_window_size()["width"] // 2,
                    browser.get_window_size()["height"] // 2,
                ).click().perform()
                time.sleep(1)
                actions.send_keys(" ").perform()
                time.sleep(1)
                actions.send_keys("f").perform()
                time.sleep(5)
            else:
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
    """Class for downloading images via HTTP requests."""

    @staticmethod
    def download_stat(url, image_id, output_folder="img"):
        """Download a static image from a URL and save it locally."""
        try:
            data = fetch_bytes(url, verify=False)
            ext = url.rsplit(".", 1)[-1]
            return save_bytes(data, image_id, ext, output_folder)
        except Exception as e:
            print(f"Error downloading static image: {e}")
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
        """Download an image from a dynamic webpage based on filters."""
        if not url or not image_id:
            return None
        try:
            resp = requests.get(url, timeout=15)
            resp.raise_for_status()
        except Exception as e:
            print(f"Request failed: {e}")
            return None
        soup = BeautifulSoup(resp.content, "html.parser")
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
            except Exception as e:
                print(f"Download failed: {e}")
                return None
            return save_bytes(data, image_id, img_format, output_folder)
        return None
