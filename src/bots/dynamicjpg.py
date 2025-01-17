# routines/dynamicjpg.py

import requests
from bs4 import BeautifulSoup
import re
import os
from urllib.parse import urljoin
from datetime import datetime

def download_dynamicjpg(url, element_id=None, element_class=None, src_pattern=None, image_id=None):
    response = requests.get(url)
    if response.status_code != 200:
        print(f"Seite {url} nicht verfügbar.")
        return None
    
    soup = BeautifulSoup(response.content, 'html.parser')
    
    # Suche nach einem Bild mit der angegebenen ID oder Klasse
    if element_id:
        img_tag = soup.find('img', id=element_id)
    elif element_class:
        img_tag = soup.find('img', class_=element_class)
    else:
        img_tag = None
    
    # Wenn kein spezifisches Bild gefunden wurde, suche alle img-Tags
    if not img_tag:
        img_tags = soup.find_all('img')
    else:
        img_tags = [img_tag]
    
    # Überprüfe jedes Bild, ob es mit dem Muster übereinstimmt
    for img in img_tags:
        img_src = img.get('src')
        if img_src and re.search(src_pattern.replace('[...]', '.*'), img_src):
            # Vervollständige relative URLs
            img_url = urljoin(url, img_src)
            print(f"Bild gefunden: {img_url}")
            
            # Bild herunterladen und speichern
            img_data = requests.get(img_url).content
            output_folder = 'img'
            os.makedirs(output_folder, exist_ok=True)
            
            timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            filename = f"{image_id}_{timestamp}.jpg"
            filepath = os.path.join(output_folder, filename)
            
            with open(filepath, 'wb') as f:
                f.write(img_data)
                print(f"Bild gespeichert als {filepath}")
            
            return filepath
    
    print(f"Kein Bild auf der Seite {url} gefunden.")
    return None
