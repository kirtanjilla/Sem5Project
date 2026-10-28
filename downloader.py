import os
import json
import urllib.request

ASSETS_DIR = "assets"
os.makedirs(ASSETS_DIR, exist_ok=True)

BIBLE_SOURCES = {
    "KJV": {
        "name": "King James Version (English)",
        "lang": "en",
        "filename": "en_kjv.json",
        "url": "https://raw.githubusercontent.com/thiagobodruk/bible/master/json/en_kjv.json"
    },
    "VUL": {
        "name": "Clementine Latin Vulgate (Latin)",
        "lang": "la",
        "filename": "la_clementine.json",
        "url": "https://raw.githubusercontent.com/thiagobodruk/bible/master/json/la_clementine.json"
    },
    "WLC": {
        "name": "Westminster Leningrad Codex (Hebrew)",
        "lang": "he",
        "filename": "he_wlc.json",
        "url": "https://raw.githubusercontent.com/thiagobodruk/bible/master/json/he_wlc.json"
    }
}

def get_json_filepath(code):
    if code in BIBLE_SOURCES:
        return os.path.join(ASSETS_DIR, BIBLE_SOURCES[code]["filename"])
    return None

def download_translation(code, progress_callback):
    """Downloads the translation JSON file if not already present in assets/"""
    if code not in BIBLE_SOURCES:
        return None
    
    filepath = get_json_filepath(code)
    if os.path.exists(filepath):
        progress_callback(f"Loading {BIBLE_SOURCES[code]['name']} from assets...")
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)

    progress_callback(f"Downloading {BIBLE_SOURCES[code]['name']} into assets folder...")
    try:
        url = BIBLE_SOURCES[code]["url"]
        req = urllib.request.urlopen(url)
        data = json.loads(req.read().decode('utf-8'))
        
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            
        progress_callback(f"Successfully downloaded and saved to {filepath}")
        return data
    except Exception as e:
        progress_callback(f"Download failed: {e}")
        return None
