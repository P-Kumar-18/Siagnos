import cloudscraper
import os
import time
from bs4 import BeautifulSoup
from csv import DictWriter, reader
from math import ceil
from random import uniform, choice
from pathlib import Path
from datetime import timedelta


# Keep one session so AO3 sees a consistent browser-like client and we reuse cookies.
SESSION = cloudscraper.create_scraper(
    browser={
        "browser": "chrome",
        "platform": "windows",
        "mobile": False
    }
)

REQUEST_GAP_SECONDS = 6.5
JITTER_SECONDS = (0.0, 3.0)
MAX_FAILURE_STREAK = 5


def sleep_with_jitter(seconds=None):
    """Add a human-like pause that varies a bit from request to request."""
    if seconds is None:
        time.sleep(uniform(
            REQUEST_GAP_SECONDS + JITTER_SECONDS[0],
            REQUEST_GAP_SECONDS + JITTER_SECONDS[1]
        ))
    else:
        time.sleep(seconds)


def fetch(url, mode="bulk"):
    """
    Fetches the HTML content of a given URL, executing retries in case
    of transient network drops or Cloudflare protection blocks.
    """
    global SESSION
    MAX_RETRIES = 5
    backoff_base = 15 if mode == "bulk" else 5
    delay = backoff_base

    if mode == "bulk":
        sleep_retry = 60
    else:
        MAX_RETRIES = 3
        sleep_retry = 3

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            # Hit the URL immediately. 
            # Timeout lowered from 90 to 15 so hanging connections fail fast and retry.
            response = SESSION.get(url, timeout=30)

            if response.status_code == 200:
                return response

            if response.status_code == 404:
                print(f"HTTP 404 for {url}")
                return response
                
            if response.status_code == 525:
                if mode == "bulk":
                    print(f"Cloudflare 525 for {url} (attempt {attempt}/{MAX_RETRIES}). Cooldown & re-rolling session...")
                
                # Give your IP a real breathing window (e.g., 20s, 40s, 60s...)
                sleep_with_jitter(20 * attempt)
                
                # Re-roll the session fingerprint
                SESSION = cloudscraper.create_scraper()
                continue

            if response.status_code in {429, 403, 500, 502, 503, 504}:
                if mode == "bulk":
                    print(
                        f"Temporary block ({response.status_code}) for {url} "
                        f"(attempt {attempt}/{MAX_RETRIES}); backing off for {delay}s"
                    )
                sleep_with_jitter(delay)
                delay = min(delay * 2, 180)
                continue

            if mode == "bulk":
                print(f"HTTP {response.status_code} (attempt {attempt}/{MAX_RETRIES})")

            sleep_with_jitter(sleep_retry)

            if mode == "live":
                sleep_retry += 2

        except Exception as e:
            if mode == "bulk":
                print(f"Request failed (attempt {attempt}/{MAX_RETRIES}): {e}")

            sleep_with_jitter(delay)
            delay = min(delay * 2, 180)

    return None


def get_path():
    """
    Resolves the parent project root directory so that relative paths 
    for resources remain stable across different execution contexts.
    """
    script_dir = Path(__file__).parent.parent.parent / "data"
    return script_dir


def save_url(url: str) -> None:
    """
    Appends a successfully scraped page URL to a centralized list 
    to make indexing resume-friendly.
    """
    parent_dir = get_path()
    file_path = os.path.join(parent_dir, "raw", "url_list.txt")

    os.makedirs(os.path.dirname(file_path), exist_ok=True)

    with open(file_path, "a", encoding="utf-8") as file:
        file.write(f"{url}\n")


def get_url(url, works=20, is_resumed=False, mode="bulk") -> list[str]:
    """
    Iterates through index listing pages, fetching and mining work-specific hrefs 
    while bypassing systemic user/tag listings.
    """
    works = int(works)
    pages = ceil(works / 20)
    page_no = 1
    iteration = 1
    url_list = []
    MAX_RETRIES = 10
    
    if mode == "bulk":
        sleep_retry = 45
        sleep_error = 60
    else:
        MAX_RETRIES = 2
        sleep_retry = 5
        sleep_error = 5      
    
    base_url = url.split('?')[0]

    if is_resumed:
        parent_dir = get_path()
        file_path_url = os.path.join(parent_dir, "raw", "url_list.txt")
        
        with open(file_path_url, "r", encoding="utf-8") as file:            
            url_list = [line.strip() for line in file.readlines()]
            story_count = len(url_list)
            
        page_no = ceil(story_count / 20) + 1
        print(f"Resuming from page: {page_no}\n")

    while page_no != pages + 1:
        current_url = f"{base_url}?page={page_no}" if mode == "bulk" else url
        
        while MAX_RETRIES >= iteration:
            response = fetch(current_url, mode=mode)

            if response is None:
                if mode == "bulk":
                    print(f"Failed to fetch page {page_no}, pausing for a bit.")
                
                sleep_with_jitter(sleep_error)
                
                if mode == "live":
                    sleep_retry += 2
                    sleep_error += 2
                
                iteration += 1
                continue

            soup = BeautifulSoup(response.text, "html.parser")
            a_tags = soup.select("h4.heading a:not([rel])")
                    
            if len(a_tags) == 0:
                if mode == "bulk":
                    print("URL Page did not load, pausing for a bit.")
                
                sleep_with_jitter(sleep_retry)
                
                if mode == "live":
                    sleep_retry += 2
                    sleep_error += 2
                
                iteration += 1
                continue
            
            for a_tag in a_tags:
                if a_tag:
                    href = a_tag.get("href", "")
                    
                    # Clean up: Uses .startswith() tuple matching for cleaner verification
                    if href.startswith(("/users/", "/groups/", "/tags/")):
                        continue
                    
                    scraped_url = f"https://archiveofourown.org{href}?view_adult=true"
                    url_list.append(scraped_url)
                    
                    if mode == "bulk":
                        save_url(url=scraped_url)

            print(f"Fetched URLs from Page: {page_no}\nIteration: {iteration}\n")
            iteration = 1
            page_no += 1
            
            if mode == "bulk":
                sleep_with_jitter()

            break
        
        if MAX_RETRIES <= iteration:
            if mode == "bulk":
                print(f"Failed to fetch page {page_no} after {MAX_RETRIES} attempts, skipping.")
            
            page_no += 1
            iteration = 1
            continue

    return url_list
        

def extract(url: str, story: int | None = None, mode="bulk") -> tuple[dict | None, int]:
    """
    Extracts explicit metadata metrics, statistics, and text tags 
    from an individual work listing on AO3.
    """
    MAX_RETRIES = 10
    iteration = 1

    if mode == "bulk":
        sleep_fetch = 60
        sleep_title = 45
    else:
        MAX_RETRIES = 2
        sleep_fetch = 5
        sleep_title = 5
        
        if "?view_adult=true" not in url:
            url += "?view_adult=true"

    while iteration <= MAX_RETRIES:
        response = fetch(url, mode=mode)

        if response is None:
            if mode == "bulk":
                print("Failed to fetch fanfiction, pausing for a bit.")
            
            iteration = MAX_RETRIES + 1
            sleep_with_jitter(sleep_fetch)
            
            if mode == "live":
                sleep_title += 2
                sleep_fetch += 2
            
            continue

        if response.status_code == 404:
            if mode == "bulk":
                print("Fanfiction not found, skipping.")
            
            iteration = MAX_RETRIES + 1
            continue

        soup = BeautifulSoup(response.text, "html.parser")
        title_element = soup.select_one("h2.title")
        title = title_element.text.strip() if title_element else None
        
        if title is None:
            if mode == "bulk":
                print("Fanfiction did not load, pausing for a bit.")
            
            iteration += 1
            sleep_with_jitter(sleep_title)
            
            if mode == "live":
                sleep_title += 2
                sleep_fetch += 2
            
            continue
        else:
            break
            
    if iteration > MAX_RETRIES:
        if story is not None:
            print(f"Failed to load fanfiction after {MAX_RETRIES} attempts, skipping.")
            response_text = response.text if response else ""

            save_failed_url(
                url=url,
                story=story,
                response=response_text
            )
        
        return None, iteration
    
    # Author
    author_element = soup.select_one("h3.byline a")
    author = author_element["href"] if author_element else None

    # Summary
    summary_element = soup.select_one("div.summary blockquote.userstuff")
    summary = summary_element.text.strip() if summary_element else None

    # Words
    words_element = soup.select_one("dd.words")
    words = words_element.text.strip() if words_element else None

    # Chapters
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

    # List Tags & Classifications
    warning = [tag.text.strip() for tag in soup.select("dd.warning ul li a")]
    category = [tag.text.strip() for tag in soup.select("dd.category ul a")]
    fandom = [tag.text.strip() for tag in soup.select("dd.fandom ul li a")]
    relationship = [tag.text.strip() for tag in soup.select("dd.relationship ul li a")]
    character = [tag.text.strip() for tag in soup.select("dd.character ul li a")]
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
        "freeform": freeform,
        "url": url
    }, iteration


def save_failed_url(url: str, story: int, response) -> None:
    """
    Logs failed story URLs and archives their HTML response bodies 
    locally to simplify debugging blockages.
    """
    parent_dir = get_path()
    file_path_failed = os.path.join(parent_dir, "raw", "failed_url_list.txt")
    file_path_debugging = os.path.join(parent_dir, "debugging", f"debugging_{story}.html")

    os.makedirs(os.path.dirname(file_path_failed), exist_ok=True)
    os.makedirs(os.path.dirname(file_path_debugging), exist_ok=True)

    with open(file_path_failed, "a", encoding="utf-8") as file:
        file.write(f"{url}\n")

    with open(file_path_debugging, "w", encoding="utf-8") as file:
        file.write(response)


def save(data: dict) -> None:
    """
    Appends a successfully processed metadata dictionary record as a line
    in a structured master CSV file.
    """
    parent_dir = get_path()
    file_path = os.path.join(parent_dir, "raw", "ao3_data.csv")
    
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    file_exists = os.path.isfile(file_path)

    with open(file_path, "a", newline="", encoding="utf-8") as file:
        writer = DictWriter(file, fieldnames=list(data.keys()))

        if not file_exists:
            writer.writeheader()
        
        writer.writerow(data)


def scrape():
    # Track the moment the entire scraping session begins
    session_start_time = time.time()
    
    story = 1
    is_resumed = False
    failure_streak = 0
    session_scraped_count = 0

    print("Starting scraper.")

    # Check if scraping should resume from an existing URL list
    if input("Use completed saved URL list? ") == "y":
        parent_dir = get_path()
        file_path_url = os.path.join(parent_dir, "raw", "url_list.txt")

        with open(file_path_url, "r", encoding="utf-8") as file:
            url_list = file.read().splitlines()

        # Determine how many stories to skip if resuming a partial run
        if input("Resume scrape from last point? ") == "y":
            file_path_fic = os.path.join(parent_dir, "raw", "ao3_data.csv")
            file_path_failed = os.path.join(parent_dir, "raw", "failed_url_list.txt")
            is_resumed = True
            rows = 0

            with open(file_path_fic, "r", encoding="utf-8") as file:
                reader_ = reader(file)
                next(reader_, None)
                rows = sum(1 for _ in reader_)

            if os.path.exists(file_path_failed):
                with open(file_path_failed, "r", encoding="utf-8") as file:
                    rows += sum(1 for _ in file)

            print(f"Skipping stories: {rows}")
            story = rows + 1

    # Fallback to fetching URLs from scratch if not using saved list
    else:
        url = input("Enter AO3 URL: ")
        works = int(input("Enter number of works to scrape: "))
        parent_dir = get_path()
        file_path_url = os.path.join(parent_dir, "raw", "url_list.txt")

        # Handle resume logic for the URL fetching phase itself
        if os.path.exists(file_path_url):
            with open(file_path_url, "r", encoding="utf-8") as file:
                line_count = sum(1 for line in file)

                if line_count > 0:
                    is_resumed = True
                    url_list = get_url(url=url, works=works, is_resumed=is_resumed)
                    is_resumed = False
        else:
            url_list = get_url(url=url, works=works)

    print("Got the URLs")

    # Iterate through the gathered URLs and extract metadata
    for url in url_list:
        # Skip URLs that have already been processed in a previous run
        if is_resumed:
            rows -= 1
            if rows == 0:
                is_resumed = False
            continue

        # Track the start time for this specific fic
        fic_start_time = time.time()

        print(f"Extracting data from: {url}")
        data, iteration = extract(url=url, story=story)

        # Handle failed extractions and increment the safety tripwire
        if data is None:
            print(f"Skipping story: {story}\n")
            failure_streak += 1
            story += 1
            sleep_with_jitter()
            
            # Abort if Cloudflare completely blocks the scraper
            if failure_streak >= MAX_FAILURE_STREAK:
                print("Too many failures in a row; stopping for safety.")
                break
            continue

        save(data=data)
        
        session_scraped_count += 1
        
        # Calculate and format the elapsed time for the fic and the total session
        fic_time_taken = time.time() - fic_start_time
        total_time_elapsed = time.time() - session_start_time
        formatted_total = str(timedelta(seconds=int(total_time_elapsed)))

        print(
            f"Story: {story} (Scraped this session: {session_scraped_count})\n"
            f"Iteration: {iteration}\n"
            f"Saved: {data['title']}\n"
            f"Fic Time: {fic_time_taken:.2f}s | Session Time: {formatted_total}\n\n"
        )

        # Reset safety tripwire on a successful scrape
        failure_streak = 0
        story += 1
        sleep_with_jitter()

    print("Done!")


if __name__ == "__main__":
    scrape()