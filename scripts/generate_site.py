#!/usr/bin/env python3
"""Regenerate sitemap.xml and index.html's article list from the actual
articles/ directory, so that publishing a new article requires touching
only articles/<slug>/index.html by hand -- this script does the rest.

Usage (run from anywhere; always operates on the repo this file lives in):

    python3 scripts/generate_site.py [--check]

Without --check, it rewrites sitemap.xml and the marked article-list
block inside index.html in place (no other content in either file is
touched). With --check, it only reports whether the files are already
up to date and exits non-zero if not (for pre-commit / CI use).

Design constraints (see project instructions this script was built to
satisfy):
  - New article directories under articles/ are picked up automatically
    -- no manifest file to hand-edit.
  - <lastmod> for each URL is derived from real git history (the last
    commit that actually touched that file), or today's date only for a
    file that is new/uncommitted/modified right now. Untouched pages
    never get bumped to "today" for no reason.
  - Existing <url> entries are never removed just because this script
    doesn't know about them; only entries for articles/ directories that
    still exist on disk are written, in their previously established
    order, with newly discovered articles appended after them.
  - index.html's article list is edited only between the
    AUTO-GENERATED:ARTICLES markers; everything else in the file
    (category cards, hero text, footer, the Search Console
    google-site-verification meta tag, etc.) is left untouched.
  - robots.txt and the <?xml ...?>/<urlset> wrapper of sitemap.xml are
    never rewritten beyond what is described above.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BASE_URL = "https://senior-dog-guide.pages.dev"

SITEMAP_PATH = ROOT / "sitemap.xml"
INDEX_PATH = ROOT / "index.html"
ARTICLES_DIR = ROOT / "articles"

MARKER_START = "<!-- AUTO-GENERATED:ARTICLES:START (managed by scripts/generate_site.py -- do not edit by hand) -->"
MARKER_END = "<!-- AUTO-GENERATED:ARTICLES:END -->"

# Fixed, small set of non-article pages. New top-level static pages (rare,
# unlike articles) are added here by hand when they are created.
STATIC_PAGES: list[tuple[str, str]] = [
    ("/", "index.html"),
]
STATIC_PAGES_AFTER_ARTICLES: list[tuple[str, str]] = [
    ("/about/", "about/index.html"),
    ("/privacy/", "privacy/index.html"),
    ("/disclosure/", "disclosure/index.html"),
]

TITLE_RE = re.compile(r"<title>(.*?)</title>", re.DOTALL)
ARTICLE_LI_HREF_RE = re.compile(r'href="/articles/([a-z0-9-]+)/"')


def _git(args: list[str]) -> str:
    result = subprocess.run(
        ["git", *args], cwd=ROOT, capture_output=True, text=True, check=False
    )
    return result.stdout.strip()


def compute_lastmod(relative_path: str) -> str:
    """Real, evidence-based <lastmod>: today only if the file is new or
    currently modified/staged; otherwise the date of the last commit that
    actually touched it."""
    dirty = _git(["status", "--porcelain", "--", relative_path])
    if dirty:
        return date.today().isoformat()
    commit_date = _git(["log", "-1", "--format=%ad", "--date=short", "--", relative_path])
    return commit_date or date.today().isoformat()


def extract_title(article_index: Path) -> str:
    text = article_index.read_text(encoding="utf-8")
    match = TITLE_RE.search(text)
    if not match:
        raise ValueError(f"no <title> tag found in {article_index}")
    full_title = match.group(1).strip()
    # Titles are authored as "<article title> | <site name>"; the site
    # name suffix is not part of the link text used elsewhere on the site.
    return full_title.split(" | ")[0].strip()


def discover_article_slugs() -> list[str]:
    return sorted(p.parent.name for p in ARTICLES_DIR.glob("*/index.html"))


def known_article_order_from_index_html(index_text: str) -> list[str]:
    start = index_text.index(MARKER_START)
    end = index_text.index(MARKER_END)
    block = index_text[start:end]
    seen: list[str] = []
    for slug in ARTICLE_LI_HREF_RE.findall(block):
        if slug not in seen:
            seen.append(slug)
    return seen


def build_final_order(known_order: list[str], discovered: list[str]) -> tuple[list[str], list[str]]:
    discovered_set = set(discovered)
    # Keep previously known articles that still exist, in their existing order.
    kept = [slug for slug in known_order if slug in discovered_set]
    # Newly discovered articles not yet listed anywhere, appended in a
    # stable (alphabetical) order.
    new_slugs = sorted(s for s in discovered if s not in kept)
    return kept + new_slugs, new_slugs


def render_index_html(index_text: str, final_order: list[str]) -> str:
    lines = [MARKER_START]
    for slug in final_order:
        title = extract_title(ARTICLES_DIR / slug / "index.html")
        lines.append("        <li>")
        lines.append(f'          <a href="/articles/{slug}/">{title}</a>')
        lines.append("        </li>")
    lines.append("        " + MARKER_END)
    new_block = "\n".join(lines)

    start = index_text.index(MARKER_START)
    end = index_text.index(MARKER_END) + len(MARKER_END)
    return index_text[:start] + new_block + index_text[end:]


def render_sitemap(final_order: list[str]) -> str:
    entries: list[tuple[str, str]] = list(STATIC_PAGES)
    for slug in final_order:
        entries.append((f"/articles/{slug}/", f"articles/{slug}/index.html"))
    entries.extend(STATIC_PAGES_AFTER_ARTICLES)

    locs = [BASE_URL + path for path, _ in entries]
    if len(locs) != len(set(locs)):
        raise AssertionError("duplicate <loc> entries would be generated -- refusing to write sitemap.xml")

    lines = ['<?xml version="1.0" encoding="UTF-8"?>', '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for path, relative_file in entries:
        lastmod = compute_lastmod(relative_file)
        lines.append("  <url>")
        lines.append(f"    <loc>{BASE_URL}{path}</loc>")
        lines.append(f"    <lastmod>{lastmod}</lastmod>")
        lines.append("  </url>")
    lines.append("</urlset>")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="report only, exit 1 if regeneration would change files")
    args = parser.parse_args()

    index_text = INDEX_PATH.read_text(encoding="utf-8")
    if MARKER_START not in index_text or MARKER_END not in index_text:
        print(f"error: markers not found in {INDEX_PATH}", file=sys.stderr)
        return 2
    if "google-site-verification" not in index_text:
        print(f"error: google-site-verification meta tag missing from {INDEX_PATH} -- refusing to proceed", file=sys.stderr)
        return 2

    known_order = known_article_order_from_index_html(index_text)
    discovered = discover_article_slugs()
    final_order, new_slugs = build_final_order(known_order, discovered)

    new_index_text = render_index_html(index_text, final_order)
    new_sitemap_text = render_sitemap(final_order)

    if "google-site-verification" not in new_index_text:
        raise AssertionError("regeneration would have dropped the google-site-verification meta tag -- aborting")

    old_sitemap_text = SITEMAP_PATH.read_text(encoding="utf-8") if SITEMAP_PATH.exists() else ""
    index_changed = new_index_text != index_text
    sitemap_changed = new_sitemap_text != old_sitemap_text

    if args.check:
        if index_changed or sitemap_changed:
            print("out of date:")
            if index_changed:
                print(f"  {INDEX_PATH.relative_to(ROOT)} would change")
            if sitemap_changed:
                print(f"  {SITEMAP_PATH.relative_to(ROOT)} would change")
            return 1
        print("up to date")
        return 0

    if new_slugs:
        print(f"newly discovered articles: {', '.join(new_slugs)}")
    if index_changed:
        INDEX_PATH.write_text(new_index_text, encoding="utf-8")
        print(f"updated {INDEX_PATH.relative_to(ROOT)}")
    else:
        print(f"{INDEX_PATH.relative_to(ROOT)} already up to date")
    if sitemap_changed:
        SITEMAP_PATH.write_text(new_sitemap_text, encoding="utf-8")
        print(f"updated {SITEMAP_PATH.relative_to(ROOT)}")
    else:
        print(f"{SITEMAP_PATH.relative_to(ROOT)} already up to date")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
