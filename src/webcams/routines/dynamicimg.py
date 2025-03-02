# routines/dynamicimg.py

import requests
from bs4 import BeautifulSoup
import re
import os
from urllib.parse import urljoin
from datetime import datetime


def download_dynamicimg(
    url, image_id, img_format, src_pattern=None, element_class=None, element_id=None
):
    """
    Download a image from a dynamic source.
    """

    if not url:
        print("No URL provided.")
        return None

    if not image_id:
        print("No image_id provided.")
        return None

    # Make the HTTP request
    try:
        response = requests.get(url, timeout=15)
        response.raise_for_status()
    except Exception as e:
        print(f"Request for {url} failed: {e}")
        return None

    # Parse the HTML
    soup = BeautifulSoup(response.content, "html.parser")

    # Collect all <img> tags
    if element_class:
        img_tags = soup.find_all("img", class_=element_class)
        print(f"Found {len(img_tags)} images with class {element_class}.")
    elif element_id:
        img_tags = soup.find_all("img", id=element_id)
        print(f"Found {len(img_tags)} images with id {element_id}.")
    else:
        img_tags = soup.find_all("img")

    # Ensure we only process tags matching the pattern
    for img in img_tags:
        img_src = img.get("src")
        if img_src:
            # Convert to full URL for pattern matching
            full_img_url = urljoin(url, img_src)

            # Match src with the pattern and ensure it ends with the specified format
            if src_pattern and not re.search(src_pattern, full_img_url):
                continue
            if not full_img_url.lower().endswith(f".{img_format}"):
                continue

            print(f"Found matching image URL: {full_img_url}")

            try:
                # Download the image
                img_data = requests.get(full_img_url, timeout=15).content
            except Exception as err:
                print(f"Downloading image {full_img_url} failed: {err}")
                return None

            # Save the image
            output_folder = "img"
            os.makedirs(output_folder, exist_ok=True)

            timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            filename = f"{image_id}_{timestamp}.{img_format}"
            filepath = os.path.join(output_folder, filename)

            with open(filepath, "wb") as f:
                f.write(img_data)
                print(f"Image saved as {filepath}")

            return filepath

    print(f"No image found on page {url} matching the given parameters.")
    return None
