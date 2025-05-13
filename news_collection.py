"""
A RSS monitor to aggregate news articles
Logic: fetch → parse → de-duplicate → scrape → log
"""

import feedparser               # Parses RSS feeds
import logging                  # For structured logging
import json                     # To store seen links
import os                       # To check file existence
from newspaper import Article   # For article scraping
from langdetect import detect   # For language detection
import requests                 # For translation API
from dateutil import parser as date_parser  # filtering by date
from datetime import datetime, timedelta, timezone
import time                     # For delay

# Constants
# Threshold - last 18 hours
# eg. timedelta(days=1, hours=5)
TIME_THRESHOLD = datetime.now(timezone.utc) - timedelta(hours=18)
# List of RSS feeds
FEED_SOURCES = {
    "https://feedx.net/rss/rfi.xml": "RFI",
    "https://www.rfi.fr/asie-pacifique/rss": "Radio France Internationale",
    "https://moxie.foxnews.com/google-publisher/latest.xml": "FoxNews Latest",
    "https://moxie.foxnews.com/google-publisher/world.xml": "FoxNews World",
    "https://asia.nikkei.com/rss/feed/nar?_gl=1*b1iseh*_gcl_aw*R0NMLjE3NDYyOTEzMzguQ2owS0NRandfZGJBQmhDNUFSSXNBQWgyWi1RWGVLUS03YWQzejhLWndKQ2tVS2g5Z0dIM2d2QWl2aHZZYlF2OGdoekpoa0dWaWxpZWhlMGFBZ3FrRUFMd193Y0I.*_gcl_au*NDc5MTk1MzAzLjE3NDUyMjIxNjk.*_ga*MTcyODI3Nzc3OS4xNzQ1MjIyMTY2*_ga_5H36ZEETNT*MTc0NjI5MTMxNy4yLjEuMTc0NjI5MTQ0Ni40MC4wLjgxNTE1NTkxNw..": "Nikkei",
    "https://www.channelnewsasia.com/api/v1/rss-outbound-feed?_format=xml&category=6511": "ChannelNewsAsia",
    "https://rss.app/feeds/NqjwpuDjNm59Zo8e.xml": "",
    "https://feeds.feedburner.com/rsscna/intworld": "TaiwanCentralNewsAgency-world",
    "https://feeds.feedburner.com/rsscna/mainland": "TaiwanCentralNewsAgency-china"
}

# "https://allafrica.com/tools/headlines/rdf/latest/headlines.rdf"

SEEN_FILE = "seen_articles.json"    # to store seen article links
TARGET_LANG = "en"             # Target language for translation

# --- Translation Function ---
def translate_title(text, target_lang="en"):
    """
    Translates the article title using the LibreTranslate public API.
    Falls back to original title if translation fails.
    Text in English or Chinese won't be translated.
    """
    lang = detect(text)
    if lang in ["en", "zh"]:
        return text
    url = "https://libretranslate.de/translate"
    payload = {
        "q": text,
        "source": "auto",
        "target": target_lang,
        "format": "text"
    }

    try:
        response = requests.post(url, data=payload, timeout=10)
        translated = response.json().get("translatedText")
        return translated if translated else text
    except Exception as e:
        logging.warning(f"Translation failed: {e}")
        return text

# --- Logging Setup ---
# Messages with a severity level of INFO or higher
# (like WARNING, ERROR, CRITICAL) will be processed.
# Messages with a lower severity level (like DEBUG) will be ignored.
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",  # s: format as a string
    handlers=[logging.FileHandler("rss_monitoring.log"),  # send log messages to file "rss_monitor.log".
              logging.StreamHandler()]  # sent log messages to the stdout stream (the screen)
)

# --- Load Previously Seen Links ---
# loading processed article links into memory
if os.path.exists(SEEN_FILE):  # check if the file exists
    with open(SEEN_FILE, 'r') as f:
        seen_links = set(json.load(f))  # Read the set of seen URLs from the file
else:
    seen_links = set()  # Initialize an empty set if the file doesn't exist

def save_seen():
    with open(SEEN_FILE, "w") as f:     # This creates the file if it doesn't exist
        json.dump(list(seen_links), f)  # Write the updated set of URLs to the file

# --- Filtering by Date ---
def is_recent(entry):
    pub_date_str = entry.get("published")
    if not pub_date_str:
        return False
    try:
        pub_date = date_parser.parse(pub_date_str)
        return pub_date > TIME_THRESHOLD        # greater means later
    except Exception as e:
        logging.info(f"Date parse failed: {e}")
        return False


# --- Main Feed Parsing Function ---
start_time = time.time()
def fetch_and_process():
    count_sum = 0
    for feed_url, metadata in FEED_SOURCES.items():
        logging.info(f"Fetching feed: {feed_url}\n>>")  # Log the current feed URL
        feed = feedparser.parse(feed_url)  # Parse the RSS feed -> returns a dictionary-like object.

        count = 0

        for entry in feed.entries:
            if not is_recent(entry):
                continue    # skip old stories
            link = entry.get("link")  # Extract the link of the article
            if link in seen_links:
                continue    # Skip to the next article if this one has been processed already.
            title = entry.get("title", "No title")   # Extract the title, defaulting to "No Title" if not found.
            date = entry.get("published")

            title_en = translate_title(title, "en")
            story = {
                "title": title_en,
                "published": date,
                "source": metadata,
                "link": link
            }

            print(f"{story['source']} {story['title']} - Published: {date}")
            print(f"{story['link']}")

            seen_links.add(link)    # Add the article's link to the seen_links set
            count += 1
            count_sum += 1
            # Scrap full article text
            try:
                article = Article(link)   # Create an Article object from the link
                article.download()  # save the article's HTML content in memory (not on disk)
                article.parse()     # extracts the body text, title, and metadata
                print(f"{article.text[:150]}")
            except Exception as e:
                logging.error(f"Failed to scrape: {link} ({e})")

        logging.info(f"{count} new articles processed.\n")

        save_seen()     # Update the seen_link file.
        # pause the script for 1 second between feed fetches,
        # in case some feeds share infrastructure.
        time.sleep(1)  # avoid being blocked by the server,

    end_time = time.time()
    elapsed = end_time - start_time
    print("------------------------------------------")
    print(f"{count_sum} articles processed. {elapsed:.2f} seconds consumed.")

if __name__ == "__main__":
    fetch_and_process()
