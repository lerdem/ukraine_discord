import requests
import json
import time
import os
import traceback
import random

from datetime import datetime, timedelta
from colorama import Fore, Style
from bs4 import BeautifulSoup, element
from utils import sqlite


db = sqlite.Database()
db.create_tables()  # Attempt to create table(s) if not exists already.


def traceback_maker(err):
    """ Make a traceback from the error """
    _traceback = ''.join(traceback.format_tb(err.__traceback__))
    error = ('{1}{0}: {2}').format(type(err).__name__, _traceback, err)
    return error


class Feed:
    def __init__(self, html_data):
        self.html = html_data
        self.info = html_data.find("div", {"class": "title"}).text
        self.id = html_data.attrs.get("data-id", None)
        self.extra = html_data.attrs.get("data-link", None)

    @property
    def video(self):
        """ Returns the video url if available """
        main_video = self.html.attrs.get("data-twitpic", None)
        if main_video and "video" in main_video:
            return main_video

        find_video = self.html.find("blockquote", {"class": "twitter-video"})
        if not find_video:
            return None
        return find_video.find("a").attrs.get("href", None)

    @property
    def image(self):
        """ Get the image of the feed """
        find_img = self.html.find("div", {"class": "img"})
        if not find_img:
            return None
        try:
            return find_img.find("img").attrs.get("src", None)
        except AttributeError:
            return None


class Article:
    def __init__(self, feed: Feed, html_data):
        self.html = html_data
        self.feed = feed

        self.image = feed.image
        self.info = feed.info
        self.id = feed.id
        self.extra = feed.extra
        self.video = feed.video

    @property
    def category_colour(self):
        """ If the article is friendly or bad/warning """
        classes = self.feed.html.attrs.get("class", "None")  # Get the classes of the feed, use "None" string so it doesn't crash
        if "cat1" in classes:
            return (  # Not good news
                0xe74c3c, "https://cdn.discordapp.com/emojis/691373958498484274.png"
            )
        elif "cat2" in classes:
            return (  # Better news lol
                0xf1c40f, "https://cdn.discordapp.com/emojis/691373958087442486.png"
            )
        return (  # Default colour, just in case I guess...?
            0xecf0f1, "https://cdn.discordapp.com/emojis/944915017340440586.png"
        )

    @property
    def source(self):
        """ Get the source of the article """
        html = self.html.find("a", {"class": "source-link"})
        if not html:
            return None
        return html.attrs.get("href", None)


def read_json(key: str = None, default=None):
    """ Read the config.json file, also define default key for keys """
    with open("./config.json", "r") as f:
        data = json.load(f)
    if key:
        return data.get(key, default)
    return data


def write_json(**kwargs):
    """ Use the config.json to write to the file """
    data = read_json()
    for key, value in kwargs.items():
        data[key] = value
    with open("./config.json", "w") as f:
        json.dump(data, f, indent=2)


def debug_html(content: str):
    debug = read_json("debug", False)
    if debug:
        if not os.path.exists("./debug"):
            os.mkdir("./debug")
        with open(f"./debug/debug_{int(time.time())}.html", "w", encoding="utf8") as f:
            html = BeautifulSoup(content, "html.parser")
            f.write(html.prettify())


def webhook(html_content: Article):
    """ Send webhook to Discord """
    utc_timestamp = datetime.utcnow()
    ukraine_timestamp = utc_timestamp + timedelta(hours=2)
    timestamp_string = "%d/%m/%Y %H:%M | %I:%M %p"

    now_unix = int(time.time())
    discord_timestamps = f"<t:{now_unix}:d> <t:{now_unix}:t>"

    cat_colour, cat_img = html_content.category_colour

    embed = {
        "author": {
            "name": "New update about Ukraine",
            # please don't remove this <3
            "url": "https://github.com/AlexFlipnote/ukraine_discord",
        },
        "color": cat_colour, "thumbnail": {"url": cat_img},
        "fields": [{
            "name": "Timezones",
            "value": "\n".join([
                f"🇬🇧 {utc_timestamp.strftime(timestamp_string)}",
                f"🇺🇦 {ukraine_timestamp.strftime(timestamp_string)}",
                f"🌍 {discord_timestamps}"
            ]),
            "inline": False
        }]
    }

    if html_content.source:
        embed["description"] = f"[ℹ️ Source of the news]({html_content.source})\n{html_content.info}"
    else:
        embed["description"] = f"ℹ️ Unable to find source...\n{html_content.info}"

    if html_content.image and read_json("embed_image", True):
        embed["image"] = {"url": html_content.image}
    if html_content.video:
        embed["description"] += f"\n\n> Warning: Can be graphical, view at own risk\n[Twitter video]({html_content.video})"

    return requests.post(
        read_json("webhook_url", None),
        headers={"Content-Type": "application/json"},
        data=json.dumps({"content": None, "embeds": [embed]}),
    )


def pretty_print(symbol: str, text: str):
    """ Use colorama to print text in pretty colours """
    data = {
        "+": Fore.GREEN, "-": Fore.RED,
        "!": Fore.YELLOW, "?": Fore.CYAN,
    }

    colour = data.get(symbol, Fore.WHITE)
    print(f"{colour}[{symbol}]{Style.RESET_ALL} {text}")


def fetch(url: str):
    """ Simply fetch any URL given, and convert from bytes to string """
    r = requests.get(
        url, headers={
            "User-Agent": read_json("user_agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64)")
        }
    )
    text = r.content.decode("utf-8")
    debug_html(text)
    return text


def _check_cloudflare(html: BeautifulSoup) -> None:
    _possible_errors = ['denied', 'Cloudflare']
    title = html.find('title')
    has_cloudflare_issues = False
    if title is not None:
        for _possible_error in _possible_errors:
            if _possible_error.lower() in title.text.lower():
                has_cloudflare_issues = True
                break

    if has_cloudflare_issues:
        pretty_print("!", "Failed because of Cloudflare protection!")
        raise ValueError(title.text)


def main():
    while True:
        try:
            # Random wait time to not be too obvious
            # Since we are scraping the website, lol
            check_in_rand = random.randint(45, 75)

            pretty_print("?", f"{datetime.now()} - Checking for new articles")
            pretty_print("+", "Fetching all articles and parsing HTML...")

            r = fetch("https://liveuamap.com/")
            html = BeautifulSoup(r, "html.parser")
            _check_cloudflare(html)

            try:
                feeder = html.find("div", {"id": "feedler"})
                latest_news_sorted = sorted(
                    [g for g in feeder if isinstance(g, element.Tag)],
                    key=lambda g: g.attrs.get("data-time", 0), reverse=True
                )
            except TypeError:
                # For some weird reason, this website loves to crash with HTTP 5XX
                # So we just try again because the website encourages us to, really.
                pretty_print("!", "Failed to get feeder, probably 500 error, trying again...")
                time.sleep(5)
                continue

            posted_something = False
            for entry in range(read_json("article_fetch_limit", 5)):
                news = Feed(latest_news_sorted[entry])
                data = db.fetchrow("SELECT * FROM articles WHERE post_id=?", (news.id,))

                if not data:
                    posted_something = True
                    pretty_print("+", "New article found, checking article...")
                    r_extra = fetch(news.extra)
                    extra_html = BeautifulSoup(r_extra, "html.parser")
                    article = Article(news, extra_html)

                    webhook(article)
                    db.execute(
                        "INSERT INTO articles (post_id, text, source, video, image) VALUES (?, ?, ?, ?, ?)",
                        (article.id, article.info, article.source, article.video, article.image)
                    )

                    pretty_print("!", news.info)
            if not posted_something:
                pretty_print("-", f"Found no news... waiting {check_in_rand} seconds")

        except Exception as e:
            pretty_print("!", traceback_maker(e))

        time.sleep(check_in_rand)


try:
    main()
except KeyboardInterrupt:
    pretty_print("!", "Exiting...")
