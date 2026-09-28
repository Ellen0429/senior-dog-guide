#!/usr/bin/env python3
"""Regenerate every internal-link-discovery surface of the site from the
actual articles/ directory, so that publishing a new article requires
touching only articles/<slug>/index.html by hand (plus, once, assigning
it a category below) -- this script does the rest.

Usage (run from anywhere; always operates on the repo this file lives in):

    python3 scripts/generate_site.py [--check]

Without --check, it rewrites every generated surface in place (no other
content is touched). With --check, it only reports whether anything is
out of date and exits non-zero if so (for pre-commit / CI use -- see
README.md's publish workflow section for how this is meant to be run
today, since this repo has no CI wired up yet).

STEP 12C extended this script (previously: sitemap.xml + index.html's
article list only) with a full internal-link-discovery layer, so that
Googlebot can find every article through several independent, ordinary
HTML <a href> paths -- not just sitemap.xml and not just a manual
Search Console "index request" -- and so this keeps working with zero
extra Owner effort as the article count grows into the hundreds:

  - Category pages (/category/<key>/): one per CATEGORIES entry below,
    listing every article assigned to it (ARTICLE_CATEGORIES below).
  - index.html's "テーマ一覧" cards now link to these category pages
    (instead of one representative article each).
  - An HTML sitemap (/articles/): every published article, grouped by
    category, as plain links -- a discovery path independent of
    sitemap.xml and of index.html's own (currently full, later
    latest-N) article list.
  - A "関連記事" (related articles) block appended near the end of
    every article: up to 3 links, same category first (excluding the
    article itself), falling back to the next category in CATEGORIES'
    own declared order (cyclically) only if the same category doesn't
    have enough members yet. Fully deterministic given
    ARTICLE_CATEGORIES + the existing article order -- no Owner choice
    needed per article beyond its one category assignment.
  - A breadcrumb (ホーム > カテゴリ > 記事) on every article and every
    category page, as plain HTML <a href> (never JavaScript), plus an
    equivalent BreadcrumbList JSON-LD block as pure supplementary
    metadata -- the HTML breadcrumb is what actually has to exist;
    JSON-LD never substitutes for it.

Design constraints (existing, unchanged):
  - New article directories under articles/ are picked up automatically
    -- no manifest file to hand-edit for the article's own existence.
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
    (hero text, the Search Console google-site-verification meta tag,
    etc.) is left untouched.
  - robots.txt and the <?xml ...?>/<urlset> wrapper of sitemap.xml are
    never rewritten beyond what is described above.
  - Existing article/category URLs and slugs are never renamed by this
    script.

New design constraint (STEP 12C):
  - Every generated block (category cards, breadcrumb, related
    articles, JSON-LD) lives between its own AUTO-GENERATED marker
    pair, exactly like the pre-existing ARTICLES marker in index.html.
    If a file doesn't have a given marker pair yet (true for all 12
    articles and index.html as of STEP 12C's own first run), this
    script inserts it once at a fixed, well-known anchor point already
    present in every article/category page's shared template (the
    ``<article class="article-body"><div class="container">`` open,
    the ``</div></article></main>`` close, and ``</head>``) -- so this
    migration is itself automatic and repeatable, not a one-off hand
    edit that the next 100 articles would have to somehow already know
    about.
  - A newly discovered article slug MUST already have an entry in
    ARTICLE_CATEGORIES below, or this script refuses to run at all
    (fail-closed, matching this whole project's standing rule to never
    silently guess). Assigning a category is therefore the one
    deliberate editorial decision left per new article; everything else
    in this file is fully mechanical.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import date
from html import escape
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BASE_URL = "https://senior-dog-guide.pages.dev"

SITEMAP_PATH = ROOT / "sitemap.xml"
INDEX_PATH = ROOT / "index.html"
ARTICLES_DIR = ROOT / "articles"
ARTICLES_INDEX_PATH = ARTICLES_DIR / "index.html"
CATEGORY_DIR = ROOT / "category"

MARKER_START = "<!-- AUTO-GENERATED:ARTICLES:START (managed by scripts/generate_site.py -- do not edit by hand) -->"
MARKER_END = "<!-- AUTO-GENERATED:ARTICLES:END -->"

CATEGORIES_MARKER_START = "<!-- AUTO-GENERATED:CATEGORIES:START (managed by scripts/generate_site.py -- do not edit by hand) -->"
CATEGORIES_MARKER_END = "<!-- AUTO-GENERATED:CATEGORIES:END -->"

BREADCRUMB_MARKER_START = "<!-- AUTO-GENERATED:BREADCRUMB:START (managed by scripts/generate_site.py -- do not edit by hand) -->"
BREADCRUMB_MARKER_END = "<!-- AUTO-GENERATED:BREADCRUMB:END -->"

RELATED_MARKER_START = "<!-- AUTO-GENERATED:RELATED:START (managed by scripts/generate_site.py -- do not edit by hand) -->"
RELATED_MARKER_END = "<!-- AUTO-GENERATED:RELATED:END -->"

JSONLD_MARKER_START = "<!-- AUTO-GENERATED:JSONLD:START (managed by scripts/generate_site.py -- do not edit by hand) -->"
JSONLD_MARKER_END = "<!-- AUTO-GENERATED:JSONLD:END -->"

# Anchors used only to INSERT a marker pair for the first time (existing
# files from before STEP 12C, or a hand-authored new article that
# doesn't have the markers yet). Every article page built from this
# site's own template contains each of these substrings exactly once.
ARTICLE_BODY_OPEN_ANCHOR = '<article class="article-body">\n    <div class="container">\n'
ARTICLE_BODY_CLOSE_ANCHOR = '\n    </div>\n  </article>\n</main>'
HEAD_CLOSE_ANCHOR = "</head>"
CATEGORY_LIST_OPEN_ANCHOR = '<ul class="category-list">\n'
CATEGORY_LIST_CLOSE_ANCHOR = '      </ul>'

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

# --- Category metadata (STEP 12C) ---------------------------------------
#
# Deterministic, hand-maintained metadata -- deliberately a plain dict,
# not a database or a YAML file, since a handful of categories for up to
# a few hundred articles doesn't need more than that. CATEGORIES' own
# declared order is used both as the display order (homepage cards,
# /articles/) and as the fallback search order for related-article
# selection below, so reordering this dict has real (but harmless)
# effects on both.
CATEGORIES: dict[str, dict[str, str]] = {
    "mobility-support": {
        "name": "歩行・お出かけサポート",
        "description": "足腰の踏ん張りが弱くなったり、段差や外出時の歩行に不安を感じやすいシニア犬のための考え方を紹介します。",
    },
    "sleep-comfort": {
        "name": "寝床・室温対策",
        "description": "快適な寝床や、暑さ・寒さへの対応など、シニア犬が過ごしやすい環境づくりのための考え方を紹介します。",
    },
    "feeding-support": {
        "name": "食事・給水補助",
        "description": "食事や水を飲む姿勢がつらそうなシニア犬のための、器選びなどの考え方を紹介します。",
    },
    "daily-grooming": {
        "name": "日常ケア・グルーミング",
        "description": "ブラッシングや歯みがきなど、日々のお手入れをやさしく行うための考え方を紹介します。",
    },
    "toilet-care": {
        "name": "トイレ・排泄ケア",
        "description": "お漏らしや排泄ケアにまつわる日常の困りごとに寄り添う考え方を紹介します。",
    },
    "safety-monitoring": {
        "name": "見守り・安全対策",
        "description": "留守番中や夜間など、シニア犬の様子を見守るための考え方を紹介します。",
    },
}

# Every discovered article slug must appear here exactly once. A newly
# added article without an entry makes this script refuse to run (see
# main()) rather than silently omitting it from category pages, the
# HTML sitemap, and related-article blocks.
ARTICLE_CATEGORIES: dict[str, str] = {
    "slip-prevention": "mobility-support",
    "step-care": "mobility-support",
    "care-harness": "mobility-support",
    "care-bed": "sleep-comfort",
    "pet-heater": "sleep-comfort",
    "cooling-mat": "sleep-comfort",
    "dish-stand": "feeding-support",
    "pet-brush": "daily-grooming",
    "dental-care": "daily-grooming",
    "body-wipes": "daily-grooming",
    "waterproof-sheet": "toilet-care",
    "dog-diaper": "toilet-care",
    "pet-camera": "safety-monitoring",
    "nail-clipper": "daily-grooming",
    "drive-box": "mobility-support",
    "retractable-leash": "mobility-support",
}

MAX_RELATED_ARTICLES = 3


def _git(args: list[str]) -> str:
    result = subprocess.run(
        ["git", *args], cwd=ROOT, capture_output=True, text=True, check=False
    )
    return result.stdout.strip()


def compute_lastmod(relative_path: str, *, changing_this_run: bool = False) -> str:
    """Real, evidence-based <lastmod>: today if the file is new, is
    currently modified/staged on disk already, OR this very invocation
    is about to rewrite it (``changing_this_run`` -- see main(), which
    computes every other generated file's new content BEFORE calling
    render_sitemap(), specifically so this function can know that; the
    file's own on-disk git status wouldn't reflect a rewrite this same
    process hasn't performed yet). Otherwise, the date of the last
    commit that actually touched it."""
    if changing_this_run:
        return date.today().isoformat()
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


def require_all_categorized(discovered: list[str]) -> None:
    missing = sorted(s for s in discovered if s not in ARTICLE_CATEGORIES)
    if missing:
        raise SystemExit(
            "error: the following article(s) have no ARTICLE_CATEGORIES entry "
            f"in {Path(__file__).name} -- add one (an existing CATEGORIES key) "
            f"before regenerating: {', '.join(missing)}"
        )


def category_members(final_order: list[str]) -> dict[str, list[str]]:
    members: dict[str, list[str]] = {key: [] for key in CATEGORIES}
    for slug in final_order:
        members[ARTICLE_CATEGORIES[slug]].append(slug)
    return members


def compute_related_slugs(slug: str, final_order: list[str], members: dict[str, list[str]]) -> list[str]:
    """Deterministic related-article selection (STEP 12C): same category
    first (site-wide order, self excluded), then -- only if that category
    doesn't have enough other members yet -- the next categories in
    CATEGORIES' own declared order, cyclically starting right after this
    article's own category. Never more than MAX_RELATED_ARTICLES, never
    the article itself, never a duplicate."""
    own_category = ARTICLE_CATEGORIES[slug]
    result = [s for s in members[own_category] if s != slug][:MAX_RELATED_ARTICLES]
    if len(result) >= MAX_RELATED_ARTICLES:
        return result

    category_keys = list(CATEGORIES)
    start = category_keys.index(own_category)
    fallback_order = category_keys[start + 1:] + category_keys[:start]
    for key in fallback_order:
        if len(result) >= MAX_RELATED_ARTICLES:
            break
        for candidate in members[key]:
            if len(result) >= MAX_RELATED_ARTICLES:
                break
            if candidate != slug and candidate not in result:
                result.append(candidate)
    return result


def build_breadcrumb(items: list[tuple[str, str]]) -> tuple[str, str]:
    """items: [(name, absolute-site path), ...] from ホーム to the current
    page (current page included, with its own real path -- it is still
    rendered as plain non-link text in the HTML breadcrumb, per normal
    breadcrumb convention, but DOES get a real "item" URL in the
    JSON-LD, which describes the full path including the current page).
    Returns (html_nav, jsonld_script)."""
    parts = []
    for i, (name, _path) in enumerate(items):
        is_last = i == len(items) - 1
        if is_last:
            parts.append(f'<span aria-current="page">{escape(name)}</span>')
        else:
            parts.append(f'<a href="{items[i][1]}">{escape(name)}</a>')
    html_nav = (
        '<nav class="breadcrumbs" aria-label="breadcrumb">\n'
        + "  " + ' <span class="breadcrumb-sep">›</span> '.join(parts) + "\n"
        + "</nav>"
    )

    list_items = []
    for i, (name, path) in enumerate(items, start=1):
        list_items.append(
            "    {\n"
            '      "@type": "ListItem",\n'
            f"      \"position\": {i},\n"
            f"      \"name\": {json.dumps(name, ensure_ascii=False)},\n"
            f'      "item": "{BASE_URL}{path}"\n'
            "    }"
        )
    jsonld = (
        '<script type="application/ld+json">\n'
        "{\n"
        '  "@context": "https://schema.org",\n'
        '  "@type": "BreadcrumbList",\n'
        '  "itemListElement": [\n'
        + ",\n".join(list_items) + "\n"
        "  ]\n"
        "}\n"
        "</script>"
    )
    return html_nav, jsonld


def render_related_block(related_slugs: list[str]) -> str:
    if not related_slugs:
        # No other articles exist yet (e.g. the very first article on a
        # brand-new site) -- omit the section entirely rather than
        # render an empty, useless one.
        return ""
    lines = [
        '<section class="related-articles" aria-labelledby="related-heading">',
        '  <h2 id="related-heading">関連記事</h2>',
        '  <ul class="article-list">',
    ]
    for slug in related_slugs:
        title = extract_title(ARTICLES_DIR / slug / "index.html")
        lines.append("    <li>")
        lines.append(f'      <a href="/articles/{slug}/">{escape(title)}</a>')
        lines.append("    </li>")
    lines.append("  </ul>")
    lines.append("</section>")
    return "\n".join(lines)


def _ensure_block(
    text: str, start_marker: str, end_marker: str, content: str,
    *, insert_after: str | None = None, insert_before: str | None = None,
) -> str:
    """Idempotently set the content of a marker-delimited block, inserting
    the marker pair for the first time at a fixed anchor if it doesn't
    exist yet in this file. `content` may be empty (renders just the
    marker pair with nothing between them, e.g. when there are no related
    articles to show yet)."""
    inner = f"{start_marker}\n{content}\n{end_marker}" if content else f"{start_marker}\n{end_marker}"
    if start_marker in text and end_marker in text:
        start = text.index(start_marker)
        end = text.index(end_marker) + len(end_marker)
        return text[:start] + inner + text[end:]
    if insert_after is not None:
        idx = text.index(insert_after)
        pos = idx + len(insert_after)
        return text[:pos] + inner + "\n" + text[pos:]
    if insert_before is not None:
        idx = text.index(insert_before)
        return text[:idx] + "\n" + inner + text[idx:]
    raise AssertionError(f"_ensure_block: anchor not found for {start_marker!r}")


def render_index_html(index_text: str, final_order: list[str]) -> str:
    lines = [MARKER_START]
    for slug in final_order:
        title = extract_title(ARTICLES_DIR / slug / "index.html")
        lines.append("        <li>")
        lines.append(f'          <a href="/articles/{slug}/">{escape(title)}</a>')
        lines.append("        </li>")
    lines.append("        " + MARKER_END)
    new_block = "\n".join(lines)

    start = index_text.index(MARKER_START)
    end = index_text.index(MARKER_END) + len(MARKER_END)
    text = index_text[:start] + new_block + index_text[end:]

    category_lines = []
    for key, meta in CATEGORIES.items():
        category_lines.append('        <li class="category-card">')
        category_lines.append(f'          <h3><a href="/category/{key}/">{escape(meta["name"])}</a></h3>')
        category_lines.append(f'          <p>{escape(meta["description"])}</p>')
        category_lines.append("        </li>")
    category_content = "\n".join(category_lines)
    inner = f"{CATEGORIES_MARKER_START}\n{category_content}\n{CATEGORIES_MARKER_END}"
    if CATEGORIES_MARKER_START in text and CATEGORIES_MARKER_END in text:
        start = text.index(CATEGORIES_MARKER_START)
        end = text.index(CATEGORIES_MARKER_END) + len(CATEGORIES_MARKER_END)
        text = text[:start] + inner + text[end:]
    else:
        # First-time migration (STEP 12C): the pre-existing category-list
        # <li> entries (one hand-picked representative article per
        # category, never wrapped in a marker) are fully replaced by the
        # generated category cards -- not merely prefixed -- so no
        # duplicate cards appear.
        open_idx = text.index(CATEGORY_LIST_OPEN_ANCHOR) + len(CATEGORY_LIST_OPEN_ANCHOR)
        close_idx = text.index(CATEGORY_LIST_CLOSE_ANCHOR, open_idx)
        text = text[:open_idx] + inner + "\n" + text[close_idx:]
    return text


def render_article_page(article_path: Path, slug: str, final_order: list[str], members: dict[str, list[str]]) -> str:
    text = article_path.read_text(encoding="utf-8")
    title = extract_title(article_path)
    category_key = ARTICLE_CATEGORIES[slug]
    category_name = CATEGORIES[category_key]["name"]
    article_path_site = f"/articles/{slug}/"

    breadcrumb_html, breadcrumb_jsonld = build_breadcrumb([
        ("ホーム", "/"),
        (category_name, f"/category/{category_key}/"),
        (title, article_path_site),
    ])
    text = _ensure_block(
        text, BREADCRUMB_MARKER_START, BREADCRUMB_MARKER_END, breadcrumb_html,
        insert_after=ARTICLE_BODY_OPEN_ANCHOR,
    )
    text = _ensure_block(
        text, JSONLD_MARKER_START, JSONLD_MARKER_END, breadcrumb_jsonld,
        insert_before=HEAD_CLOSE_ANCHOR,
    )

    related_slugs = compute_related_slugs(slug, final_order, members)
    related_html = render_related_block(related_slugs)
    text = _ensure_block(
        text, RELATED_MARKER_START, RELATED_MARKER_END, related_html,
        insert_before=ARTICLE_BODY_CLOSE_ANCHOR,
    )
    return text


def render_category_page(category_key: str, final_order: list[str], members: dict[str, list[str]]) -> str:
    meta = CATEGORIES[category_key]
    name = meta["name"]
    description = meta["description"]
    path = f"/category/{category_key}/"
    breadcrumb_html, breadcrumb_jsonld = build_breadcrumb([
        ("ホーム", "/"),
        (name, path),
    ])

    article_items = []
    for slug in members[category_key]:
        title = extract_title(ARTICLES_DIR / slug / "index.html")
        article_items.append(f'        <li><a href="/articles/{slug}/">{escape(title)}</a></li>')
    articles_html = "\n".join(article_items) if article_items else "        <li>この分類の記事は準備中です。</li>"

    return f"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{escape(name)} | シニア犬のくらし手帖</title>
<meta name="description" content="{escape(description)}">
<meta property="og:type" content="website">
<meta property="og:title" content="{escape(name)} | シニア犬のくらし手帖">
<meta property="og:url" content="{BASE_URL}{path}">
<link rel="canonical" href="{BASE_URL}{path}">
<link rel="stylesheet" href="/assets/css/style.css">
{breadcrumb_jsonld}
</head>
<body>
<header class="site-header">
  <div class="container">
    <a class="site-title" href="/">シニア犬のくらし手帖</a>
    <nav class="site-nav" aria-label="サイト内メニュー">
      <a href="/">ホーム</a>
      <a href="/articles/">記事一覧</a>
      <a href="/about/">運営者情報</a>
    </nav>
  </div>
</header>

<main>
  <article class="article-body">
    <div class="container">
{breadcrumb_html}
      <h1>{escape(name)}</h1>
      <p class="article-lead">{escape(description)}</p>
      <ul class="article-list">
{articles_html}
      </ul>
    </div>
  </article>
</main>

<footer class="site-footer">
  <div class="container">
    <p class="ad-notice">本サイトはアフィリエイトプログラム(楽天アフィリエイト等)を利用する場合があります。詳しくは<a href="/disclosure/">広告・アフィリエイトについて</a>をご確認ください。</p>
    <nav class="footer-nav" aria-label="フッターメニュー">
      <a href="/about/">運営者情報</a>
      <a href="/privacy/">プライバシーポリシー</a>
      <a href="/disclosure/">広告・アフィリエイトについて</a>
    </nav>
    <p class="copyright">&copy; 2026 シニア犬のくらし手帖</p>
  </div>
</footer>
</body>
</html>
"""


def render_articles_index_page(final_order: list[str], members: dict[str, list[str]]) -> str:
    path = "/articles/"
    breadcrumb_html, breadcrumb_jsonld = build_breadcrumb([
        ("ホーム", "/"),
        ("記事一覧", path),
    ])

    sections = []
    for key, meta in CATEGORIES.items():
        slugs = members[key]
        if not slugs:
            continue
        items = []
        for slug in slugs:
            title = extract_title(ARTICLES_DIR / slug / "index.html")
            items.append(f'          <li><a href="/articles/{slug}/">{escape(title)}</a></li>')
        sections.append(
            f'      <section aria-labelledby="cat-{key}">\n'
            f'        <h2 id="cat-{key}"><a href="/category/{key}/">{escape(meta["name"])}</a></h2>\n'
            "        <ul class=\"article-list\">\n" + "\n".join(items) + "\n        </ul>\n"
            "      </section>"
        )
    sections_html = "\n".join(sections)

    return f"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>記事一覧 | シニア犬のくらし手帖</title>
<meta name="description" content="「シニア犬のくらし手帖」で公開しているすべての記事を、テーマ別にまとめた一覧です。">
<meta property="og:type" content="website">
<meta property="og:title" content="記事一覧 | シニア犬のくらし手帖">
<meta property="og:url" content="{BASE_URL}{path}">
<link rel="canonical" href="{BASE_URL}{path}">
<link rel="stylesheet" href="/assets/css/style.css">
{breadcrumb_jsonld}
</head>
<body>
<header class="site-header">
  <div class="container">
    <a class="site-title" href="/">シニア犬のくらし手帖</a>
    <nav class="site-nav" aria-label="サイト内メニュー">
      <a href="/">ホーム</a>
      <a href="/articles/">記事一覧</a>
      <a href="/about/">運営者情報</a>
    </nav>
  </div>
</header>

<main>
  <article class="article-body">
    <div class="container">
{breadcrumb_html}
      <h1>記事一覧</h1>
      <p class="article-lead">これまでに公開したすべての記事を、テーマ別にまとめています。</p>
{sections_html}
    </div>
  </article>
</main>

<footer class="site-footer">
  <div class="container">
    <p class="ad-notice">本サイトはアフィリエイトプログラム(楽天アフィリエイト等)を利用する場合があります。詳しくは<a href="/disclosure/">広告・アフィリエイトについて</a>をご確認ください。</p>
    <nav class="footer-nav" aria-label="フッターメニュー">
      <a href="/about/">運営者情報</a>
      <a href="/privacy/">プライバシーポリシー</a>
      <a href="/disclosure/">広告・アフィリエイトについて</a>
    </nav>
    <p class="copyright">&copy; 2026 シニア犬のくらし手帖</p>
  </div>
</footer>
</body>
</html>
"""


def render_sitemap(final_order: list[str], changed_relative_paths: frozenset[str] = frozenset()) -> str:
    """`changed_relative_paths`: relative paths of every OTHER generated
    file that this same script invocation is about to (re)write -- see
    main(), which computes these before calling this function, precisely
    so a page that is changing in this very run gets today's <lastmod>
    even though its on-disk git status doesn't show that yet (nothing
    has actually been written yet at this point in main())."""
    entries: list[tuple[str, str]] = list(STATIC_PAGES)
    for slug in final_order:
        entries.append((f"/articles/{slug}/", f"articles/{slug}/index.html"))
    entries.append(("/articles/", "articles/index.html"))
    for key in CATEGORIES:
        entries.append((f"/category/{key}/", f"category/{key}/index.html"))
    entries.extend(STATIC_PAGES_AFTER_ARTICLES)

    locs = [BASE_URL + path for path, _ in entries]
    if len(locs) != len(set(locs)):
        raise AssertionError("duplicate <loc> entries would be generated -- refusing to write sitemap.xml")

    lines = ['<?xml version="1.0" encoding="UTF-8"?>', '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for path, relative_file in entries:
        lastmod = compute_lastmod(relative_file, changing_this_run=relative_file in changed_relative_paths)
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
    require_all_categorized(discovered)
    final_order, new_slugs = build_final_order(known_order, discovered)
    members = category_members(final_order)

    # Every generated file EXCEPT sitemap.xml itself is computed first,
    # so render_sitemap() can be told which of them are about to be
    # (re)written by THIS run -- see compute_lastmod()'s own docstring
    # for why that can't be inferred from git status alone at this point.
    outputs: dict[Path, str] = {}

    new_index_text = render_index_html(index_text, final_order)
    if "google-site-verification" not in new_index_text:
        raise AssertionError("regeneration would have dropped the google-site-verification meta tag -- aborting")
    outputs[INDEX_PATH] = new_index_text

    for slug in final_order:
        article_path = ARTICLES_DIR / slug / "index.html"
        outputs[article_path] = render_article_page(article_path, slug, final_order, members)

    for key in CATEGORIES:
        outputs[CATEGORY_DIR / key / "index.html"] = render_category_page(key, final_order, members)

    outputs[ARTICLES_INDEX_PATH] = render_articles_index_page(final_order, members)

    changed_relative_paths = frozenset(
        str(path.relative_to(ROOT))
        for path, new_text in outputs.items()
        if (path.read_text(encoding="utf-8") if path.exists() else None) != new_text
    )
    outputs[SITEMAP_PATH] = render_sitemap(final_order, changed_relative_paths)

    changed: list[Path] = []
    for path, new_text in outputs.items():
        old_text = path.read_text(encoding="utf-8") if path.exists() else None
        if old_text != new_text:
            changed.append(path)

    if args.check:
        if changed:
            print("out of date:")
            for path in changed:
                print(f"  {path.relative_to(ROOT)} would change")
            return 1
        print("up to date")
        return 0

    if new_slugs:
        print(f"newly discovered articles: {', '.join(new_slugs)}")
    for path in changed:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(outputs[path], encoding="utf-8")
        print(f"updated {path.relative_to(ROOT)}")
    if not changed:
        print("all generated files already up to date")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
