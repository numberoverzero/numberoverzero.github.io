#!/usr/bin/env python
# -*- coding: utf-8 -*- #


AUTHOR = "numberoverzero"
SITENAME = "numberoverzero"
SITEURL = "http://localhost:8000"

ARCHIVES_SAVE_AS = "posts/index.html"
ARTICLE_URL = "posts/{date:%Y}/{date:%m}/{date:%d}/{slug}"
ARTICLE_SAVE_AS = "posts/{date:%Y}/{date:%m}/{date:%d}/{slug}.html"
YEAR_ARCHIVE_SAVE_AS = "posts/{date:%Y}/index.html"

DELETE_OUTPUT_DIRECTORY = True
OUTPUT_RETENTION = ["static"]
STATIC_PATHS = ["extra", "theme/templates/static"]
EXTRA_PATH_METADATA = {
    "theme/templates/static/style.min.css": {"path": "static/style.css"},
    "extra/CNAME": {"path": "CNAME"},
    "extra/_prefetchManifest.json": {"path": "_prefetchManifest.json"},
    "extra/favicon.ico": {"path": "favicon.ico"},
}
THEME = "./theme"
PATH = "content"

TIMEZONE = "US/Pacific"

DEFAULT_LANG = "en"
DEFAULT_DATE_FORMAT = "%Y-%m-%d"

FEED_ALL_ATOM = None
CATEGORY_FEED_ATOM = None
TRANSLATION_FEED_ATOM = None
AUTHOR_FEED_ATOM = None
AUTHOR_FEED_RSS = None

DEFAULT_PAGINATION = False

PYGMENTS_RST_OPTIONS = {
    "linenos": "table",
}

# Uncomment following line if you want document-relative URLs when developing
#RELATIVE_URLS = True


PLUGINS = ["grits_plugin"]


# Disable categories, authors, archives
DIRECT_TEMPLATES = ["index", "archives"]
AUTHOR_SAVE_AS = ""
CATEGORY_SAVE_AS = ""
