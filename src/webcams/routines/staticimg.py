# routines/staticimg.py

import requests
from PIL import Image
from io import BytesIO
import os
from datetime import datetime


def download_staticimg(url, image_id):
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
        }
        response = requests.get(url, headers=headers, verify=False)
        if response.status_code == 200:
            img = Image.open(BytesIO(response.content))
            img_format = url.split(".")[-1]
            output_folder = "img"
            os.makedirs(output_folder, exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            filename = f"{image_id}_{timestamp}.{img_format}"
            filepath = os.path.join(output_folder, filename)
            img.save(filepath)
            print(f"Image saved as {filepath}")
            return filepath
        else:
            print(
                f"Error downloading image from {url} - Status: {response.status_code}"
            )
            return None
    except requests.exceptions.RequestException as e:
        print(f"Network error at {url}: {e}")
        return None
    except Exception as e:
        print(f"General error at {url}: {e}")
        return None
