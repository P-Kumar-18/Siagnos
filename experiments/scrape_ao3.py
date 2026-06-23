from bs4 import BeautifulSoup
from math import ceil
from random import uniform
from csv import DictWriter, reader
import requests
import time
import os


# Keep one session so AO3 sees a consistent browser-like client and we reuse cookies.
SESSION = requests.Session()
SESSION.headers.update(
    {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Sec-Ch-Ua": '"Google Chrome";v="131", "Chromium";v="131", "Not_A Brand";v="24"',
        "Sec-Ch-Ua-Mobile": "?0",
        "Sec-Ch-Ua-Platform": '"Windows"'
    }
)   

def fetch(url):
    # Use a persistent session to fetch the URL, retrying on connection errors or timeouts.
    while True:
        try:
            return SESSION.get(url)
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout):
            print(f"Network error. Retrying in 5 minutes.\n\n")
            sleep(300)
            print(f"Resuming\n")


def sleep(time_=None):
    # Default pause is randomized to reduce the chance of being rate-limited.
    if time_ is None:
        time.sleep(uniform(5.5, 8.5))
    else:
        time.sleep(time_)


def get_path():
    # Resolve the project root from this script so data files land in a stable place.
    script_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.dirname(script_dir)


def save_url(url: str) -> None:
    # Persist every discovered work URL so the scrape can be resumed later.
    parent_dir = get_path()
    file_path = os.path.join(parent_dir, "data", "url_list.txt")

    os.makedirs(os.path.dirname(file_path), exist_ok=True)

    with open(file_path, "a", encoding="utf-8") as file:
        file.write(f"{url}\n")


def get_url(url, works, is_resumed=False) -> list[str]:
    # AO3 shows about 20 works per page, so we walk each result page and extract work links.
    works = int(works)
    pages = ceil(works/20)
    page_no = 1
    url_list = []
    iteration = 0
    
    base_url = url.split('?')[0]
    
    if is_resumed:
        parent_dir = get_path()
        file_path_url = os.path.join(parent_dir, "data", "url_list.txt")
        
        with open(file_path_url, "r", encoding="utf-8") as file:            
            url_list = [line.strip() for line in file.readlines()]
            
            story_count = len(url_list)
            
        page_no = ceil(story_count/20) + 1
        print(f"Resuming from page: {page_no}\n")

    while page_no != pages + 1:
        iteration += 1
        current_url = f"{base_url}?page={page_no}"
        
        print(f"Current URL: {current_url}\n")
        
        response = fetch(current_url)

        soup = BeautifulSoup(response.text, "html.parser")
        
        # Only capture work links; skip user profile links and anything AO3 did not render yet.
        a_tags = soup.select("h4.heading a:not([rel])")
                
        if len(a_tags) == 0:
            print(f"URL Page did not load, pausing for a bit.\n")
            sleep(15.23)
            continue
        
        for a_tag in a_tags:
            if a_tag:
                if a_tag["href"][:7] == "/users/":
                    continue
                
                # Convert AO3-relative hrefs into full URLs before saving them.
                scraped_url = f"https://archiveofourown.org{a_tag.get('href')}"
                url_list.append(scraped_url)
                save_url(url=scraped_url)

        print(f"Fetched URLs from Page: {page_no}\nIteration: {iteration}\n")
        
        page_no += 1
        sleep()
        
    iteration = 0
    return url_list


def extract(url: str) -> dict:
    iteration = 1
    while True:
        response = fetch(url)

        soup = BeautifulSoup(response.text, "html.parser")
        
        # If the title is missing, AO3 likely returned a temporary block or partial page.
        title_element = soup.select_one("h2.title")
        title = title_element.text.strip() if title_element else None
        
        if title is None:
            print(f"Fanfiction did not load, pausing for a bit.\n")
            iteration += 1
            sleep(15.6)
            continue
        else:
            break

    # The remaining fields come from AO3's metadata sidebar and tag lists.
    # Author
    author_element = soup.select_one("h3.byline a")
    author = author_element["href"] if author_element else None

    # Summary
    summary_element = soup.select_one("div.summary blockquote.userstuff")
    summary = summary_element.text.strip() if summary_element else None

    # Words
    words_element = soup.select_one("dd.words")
    words = words_element.text.strip() if words_element else None

    # Chapters (Current and Total)
    chapters_element = soup.select_one("dd.chapters")
    if chapters_element:
        current_chapters, total_chapters = chapters_element.text.strip().split("/")
        total_chapters = total_chapters if total_chapters != "?" else None
        current_chapters = current_chapters if current_chapters else None
    else:
        current_chapters, total_chapters = None, None
    
    # Kudos
    kudos_element = soup.select_one("dd.kudos")
    kudos = kudos_element.text.strip() if kudos_element else None

    # Bookmarks
    bookmarks_element = soup.select_one("dd.bookmarks a")
    bookmarks = bookmarks_element.text.strip() if bookmarks_element else None

    # Hits
    hits_element = soup.select_one("dd.hits")
    hits = hits_element.text.strip() if hits_element else None

    # Rating
    rating_element = soup.select_one("dd.rating ul li a")
    rating = rating_element.text.strip() if rating_element else None

    # Language
    language_element = soup.select_one("dd.language")
    language = language_element.text.strip() if language_element else None

    # Status
    status_element = soup.select_one("dt.status")
    status = status_element.text.strip() if status_element else None

    # Last Active Date
    last_date_element = soup.select_one("dd.status")
    last_date = last_date_element.text.strip() if last_date_element else None

    # Warnings
    warning = [tag.text.strip() for tag in soup.select("dd.warning ul li a")]

    # Categories
    category = [tag.text.strip() for tag in soup.select("dd.category ul a")]

    # Fandom
    fandom = [tag.text.strip() for tag in soup.select("dd.fandom ul li a")]

    # Relationships
    relationship = [tag.text.strip() for tag in soup.select("dd.relationship ul li a")]

    # Character
    character = [tag.text.strip() for tag in soup.select("dd.character ul li a")]

    # Additional Tags
    freeform = [tag.text.strip() for tag in soup.select("dd.freeform ul li a")]

    return {
        "title": title,
        "author": author,
        "summary": summary,
        "words": words,
        "current_chapters": current_chapters,
        "total_chapters": total_chapters,
        "kudos": kudos,
        "bookmarks": bookmarks,
        "hits": hits,
        "rating": rating,
        "language": language,
        "status": status,
        "last_date": last_date,
        "warning": warning,
        "category": category,
        "fandom": fandom,
        "relationship": relationship,
        "character": character, 
        "freeform": freeform
    }, iteration


def save(data: dict) -> None:
    # Append one row per work so the CSV can grow incrementally during long runs.
    parent_dir = get_path()
    file_path = os.path.join(parent_dir, "data", "ao3_data.csv")
    
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    file_exists = os.path.isfile(file_path)

    with open(file_path, "a", newline="", encoding="utf-8") as file:
        writer = DictWriter(file, fieldnames=list(data.keys()))

        if not file_exists:
            writer.writeheader()
        
        writer.writerow(data)


def scrape():
    story = 1
    print(f"Starting scraper.")
    is_resumed = False
    if input("Use completed saved URL list? ") == "y":
        # Resume mode reuses the saved URL list and can skip already-written CSV rows.
        parent_dir = get_path()
        file_path_url = os.path.join(parent_dir, "data", "url_list.txt")
        file_path_fic = os.path.join(parent_dir, "data", "ao3_data.csv")
        
        with open(file_path_url, "r", encoding="utf-8") as file:
            url_list = file.read().splitlines()
        
        if input("Resume scrape from last point? ") == "y":
            is_resumed = True
            rows = 0
            
            with open(file_path_fic, "r", encoding="utf-8") as file:
                reader_ = reader(file)
                
                next(reader_, None)
                
                for row in reader_:
                    rows += 1
            
            print(f"Skipping stories: {rows}")
            story = rows + 1
    else:
        url = input("Enter AO3 URL: ")
        works = int(input("Enter number of works to scrape: "))
        parent_dir = get_path()
        file_path_url = os.path.join(parent_dir, "data", "url_list.txt")
        if os.path.exists(file_path_url):
            with open(file_path_url, "r", encoding="utf-8") as file:
                line_count = sum(1 for line in file)
                
                if line_count > 0:
                    is_resumed = True
                    url_list = get_url(url=url, works=works, is_resumed=is_resumed)
                    is_resumed = False
        else:
            url_list = get_url(url=url, works=works)
    print(f"Got the URLs")

    for url in url_list:
        if is_resumed:
            # Count down until we reach the first unsaved story, then continue normal scraping.
            rows -= 1
            if rows == 0:
                is_resumed = False
            
            continue
        print(f"Extracting data from: {url}")
        data, iteration = extract(url=url)
        save(data=data)
        print(f"Story: {story}\nIteration: {iteration}\nSaved: {data['title']}\n\n")
        
        story += 1
        sleep()
    
    print("Done!")


if __name__ == "__main__":
    scrape()