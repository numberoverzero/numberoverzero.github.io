#!/usr/bin/env python
# -*- coding: utf-8 -*- #


AUTHOR = "numberoverzero"
SITENAME = "numberoverzero"
SITEURL = ""

DELETE_OUTPUT_DIRECTORY = True
OUTPUT_RETENTION = ["static", "static/style.css"]
STATIC_PATHS = ["extra"]
EXTRA_PATH_METADATA = {
    "extra/CNAME": {"path": "CNAME"},
    "extra/favicon.ico": {"path": "favicon.ico"},
}
THEME = "./theme"
PATH = "content"

TIMEZONE = "US/Pacific"

DEFAULT_LANG = "en"
DEFAULT_DATE_FORMAT = "%Y-%m-%d"

# Feed generation is usually not desired when developing
FEED_ALL_ATOM = None
CATEGORY_FEED_ATOM = None
TRANSLATION_FEED_ATOM = None
AUTHOR_FEED_ATOM = None
AUTHOR_FEED_RSS = None

# Blogroll
LINKS = (('Pelican', 'http://getpelican.com/'),
         ('Python.org', 'http://python.org/'),
         ('Jinja2', 'http://jinja.pocoo.org/'),
         ('You can modify those links in your config file', '#'),)

# Social widget
SOCIAL = (('You can add links in your config file', '#'),
          ('Another social link', '#'),)

DEFAULT_PAGINATION = False

PYGMENTS_RST_OPTIONS = {
    "linenos": "table",
}

# Uncomment following line if you want document-relative URLs when developing
#RELATIVE_URLS = True


# TESTING
PLUGINS = ["grits_plugin"]


# Disable categories, authors, archives
DIRECT_TEMPLATES = ["index", "archives"]
AUTHOR_SAVE_AS = ""
CATEGORY_SAVE_AS = ""
