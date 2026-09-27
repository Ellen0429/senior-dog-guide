#!/usr/bin/env python3
"""Unit tests for generate_site.py, run against a throwaway copy of a
minimal fake site tree (never against the real repo's files).

STEP 12C note: the copied script still carries its own real, hardcoded
CATEGORIES / ARTICLE_CATEGORIES dicts (this project deliberately keeps
that metadata as a plain dict in the script itself, not an
externally-injectable config -- see generate_site.py's own docstring).
So this fixture's fake articles are given REAL slugs that already have
a category assigned in the real script (e.g. "care-bed", "pet-heater",
"dish-stand") rather than synthetic ones like the old "alpha"/"beta" --
their <title> text is still fake/synthetic, only the slug (used purely
as a categorization lookup key) is real.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import urlparse

REAL_SCRIPT = Path(__file__).resolve().parent / "generate_site.py"
BASE_URL = "https://senior-dog-guide.pages.dev"

INDEX_TEMPLATE = """<!DOCTYPE html>
<html lang="ja">
<head>
<meta name="google-site-verification" content="dummy" />
<title>Fake Site</title>
</head>
<body>
<header class="site-header">
  <div class="container">
    <nav class="site-nav" aria-label="サイト内メニュー">
      <a href="/">ホーム</a>
      <a href="/about/">運営者情報</a>
    </nav>
  </div>
</header>
<main>
  <section class="categories">
    <div class="container">
      <ul class="category-list">
        <li class="category-card"><h3>Dummy category</h3></li>
      </ul>
    </div>
  </section>
  <section class="articles">
    <ul class="article-list">
        <!-- AUTO-GENERATED:ARTICLES:START (managed by scripts/generate_site.py -- do not edit by hand) -->
        <li>
          <a href="/articles/care-bed/">Alpha Title</a>
        </li>
        <!-- AUTO-GENERATED:ARTICLES:END -->
    </ul>
  </section>
</main>
<footer class="site-footer">
  <div class="container"></div>
</footer>
</body>
</html>
"""

SITEMAP_TEMPLATE = """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url>
    <loc>https://example.pages.dev/</loc>
  </url>
  <url>
    <loc>https://example.pages.dev/articles/care-bed/</loc>
  </url>
  <url>
    <loc>https://example.pages.dev/about/</loc>
  </url>
</urlset>
"""


def article_html(title: str, slug: str = "care-bed") -> str:
    """A minimal but structurally faithful stand-in for this site's real
    per-article template -- specifically, it contains the exact anchor
    substrings generate_site.py looks for when migrating a file that
    doesn't have the AUTO-GENERATED:BREADCRUMB / :RELATED / :JSONLD
    markers yet (every real article in this repo has this same shape),
    AND a real per-slug canonical tag (every real article has one; it is
    hand-authored, not generated_site.py-managed, but its presence and
    correctness is exactly what test_canonical_matches_own_url_on_every_
    generated_page checks)."""
    return f"""<!DOCTYPE html>
<html lang="ja">
<head>
<title>{title} | Fake Site</title>
<link rel="canonical" href="{BASE_URL}/articles/{slug}/">
</head>
<body>
<main>
  <article class="article-body">
    <div class="container">
      <h1>{title}</h1>
      <p>Fake body text.</p>
      <section id="note">
        <h2>Note</h2>
        <p>Fake note.</p>
      </section>
    </div>
  </article>
</main>
</body>
</html>
"""


def make_fake_site(root: Path) -> None:
    (root / "articles" / "care-bed").mkdir(parents=True)
    (root / "articles" / "care-bed" / "index.html").write_text(
        article_html("Alpha Title"), encoding="utf-8"
    )
    (root / "about").mkdir(parents=True)
    (root / "about" / "index.html").write_text("<title>About</title>", encoding="utf-8")
    (root / "privacy").mkdir(parents=True)
    (root / "privacy" / "index.html").write_text("<title>Privacy</title>", encoding="utf-8")
    (root / "disclosure").mkdir(parents=True)
    (root / "disclosure" / "index.html").write_text("<title>Disclosure</title>", encoding="utf-8")
    (root / "index.html").write_text(INDEX_TEMPLATE, encoding="utf-8")
    (root / "sitemap.xml").write_text(SITEMAP_TEMPLATE, encoding="utf-8")

    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=root, check=True)
    subprocess.run(["git", "add", "-A"], cwd=root, check=True)
    subprocess.run(
        ["git", "commit", "-q", "-m", "initial", "--date=2026-01-01T00:00:00"],
        cwd=root,
        check=True,
        env={"GIT_AUTHOR_DATE": "2026-01-01T00:00:00", "GIT_COMMITTER_DATE": "2026-01-01T00:00:00", "PATH": "/usr/bin:/bin"},
    )


def add_article(root: Path, slug: str, title: str) -> None:
    (root / "articles" / slug).mkdir(parents=True)
    (root / "articles" / slug / "index.html").write_text(article_html(title, slug), encoding="utf-8")


def run_script(root: Path, *extra_args: str) -> subprocess.CompletedProcess:
    script_copy = root / "scripts" / "generate_site.py"
    script_copy.parent.mkdir(exist_ok=True)
    shutil.copy(REAL_SCRIPT, script_copy)
    return subprocess.run(
        [sys.executable, str(script_copy), *extra_args],
        cwd=root,
        capture_output=True,
        text=True,
    )


def commit_all(root: Path, message: str = "regen") -> None:
    subprocess.run(["git", "add", "-A"], cwd=root, check=True)
    subprocess.run(["git", "commit", "-q", "-m", message], cwd=root, check=True)


# --- Static-site-wide crawl helpers (used by the mechanical-crawl tests) --

def all_html_files(root: Path) -> list[Path]:
    return [
        p for p in root.rglob("index.html")
        if ".git" not in p.parts and "scripts" not in p.parts
    ]


def site_path_for(root: Path, html_file: Path) -> str:
    rel = html_file.relative_to(root)
    if rel == Path("index.html"):
        return "/"
    return "/" + str(rel.parent) + "/"


def internal_links_in(html_text: str) -> list[str]:
    return [
        href for href in re.findall(r'href="([^"]*)"', html_text)
        if href.startswith("/") and not href.startswith("//")
        and not href.startswith("/go?")  # affiliate redirect, deliberately nofollow/out of scope
        and not href.startswith("/assets/")
    ]


class GenerateSiteTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        make_fake_site(self.root)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    # --- Pre-existing behaviour (unchanged by STEP 12C) -------------------

    def test_check_reports_up_to_date_once_a_regeneration_is_committed(self) -> None:
        run_script(self.root)
        commit_all(self.root)
        result = run_script(self.root, "--check")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("up to date", result.stdout)

    def test_unchanged_pages_keep_their_original_lastmod_not_today(self) -> None:
        # about/privacy/disclosure are never touched by generate_site.py
        # at all (real generate_site.py doesn't manage them beyond
        # listing their URL in STATIC_PAGES_AFTER_ARTICLES) -- these, and
        # only these, in this fixture must keep the original fixture
        # commit's date and never get bumped to "today" for no reason.
        # (index.html and articles/care-bed/index.html, by contrast,
        # genuinely gain new content on this first migration run --
        # AUTO-GENERATED:CATEGORIES / :BREADCRUMB / :RELATED / :JSONLD --
        # so today's date on THEIR entries is correct, not a bug; see
        # test_running_again_after_committing_makes_no_further_changes
        # for the check that a run with nothing left to migrate is a
        # true no-op.)
        run_script(self.root)
        commit_all(self.root)
        run_script(self.root)
        sitemap = (self.root / "sitemap.xml").read_text(encoding="utf-8")
        for path in ("/about/", "/privacy/", "/disclosure/"):
            block = sitemap.split(f"<loc>{BASE_URL}{path}</loc>")[1].split("</url>")[0]
            self.assertIn("<lastmod>2026-01-01</lastmod>", block, f"{path} lastmod unexpectedly bumped")

    def test_new_article_is_discovered_and_added_to_both_files(self) -> None:
        # "pet-heater" is a real slug already categorized (sleep-comfort,
        # same as care-bed) in the real script -- see module docstring.
        add_article(self.root, "pet-heater", "Beta Title")
        result = run_script(self.root)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("pet-heater", result.stdout)

        index_html = (self.root / "index.html").read_text(encoding="utf-8")
        self.assertIn('<a href="/articles/pet-heater/">Beta Title</a>', index_html)
        # Existing entry and everything outside the marker block untouched.
        self.assertIn('<a href="/articles/care-bed/">Alpha Title</a>', index_html)
        self.assertIn("google-site-verification", index_html)

        sitemap = (self.root / "sitemap.xml").read_text(encoding="utf-8")
        self.assertIn("<loc>https://senior-dog-guide.pages.dev/articles/pet-heater/</loc>", sitemap)
        # New, uncommitted file -> today's date, not the fixed fixture date.
        beta_block = sitemap.split("articles/pet-heater/</loc>")[1].split("</url>")[0]
        self.assertNotIn("<lastmod>2026-01-01</lastmod>", beta_block)

    def test_no_duplicate_locs_ever_generated(self) -> None:
        add_article(self.root, "pet-heater", "Beta Title")
        run_script(self.root)
        sitemap = (self.root / "sitemap.xml").read_text(encoding="utf-8")
        locs = [line.strip() for line in sitemap.splitlines() if "<loc>" in line]
        self.assertEqual(len(locs), len(set(locs)))

    def test_existing_urls_are_not_removed_when_nothing_changes(self) -> None:
        run_script(self.root)
        sitemap = (self.root / "sitemap.xml").read_text(encoding="utf-8")
        for expected in ("/", "/articles/care-bed/", "/about/", "/privacy/", "/disclosure/"):
            self.assertIn(f"<loc>https://senior-dog-guide.pages.dev{expected}</loc>", sitemap)

    def test_running_again_after_committing_makes_no_further_changes(self) -> None:
        run_script(self.root)
        commit_all(self.root)
        sitemap_first = (self.root / "sitemap.xml").read_text(encoding="utf-8")
        index_first = (self.root / "index.html").read_text(encoding="utf-8")

        run_script(self.root)
        sitemap_second = (self.root / "sitemap.xml").read_text(encoding="utf-8")
        index_second = (self.root / "index.html").read_text(encoding="utf-8")
        self.assertEqual(sitemap_first, sitemap_second)
        self.assertEqual(index_first, index_second)

    def test_refuses_to_run_if_google_site_verification_meta_missing(self) -> None:
        index_html = (self.root / "index.html").read_text(encoding="utf-8")
        stripped = index_html.replace(
            '<meta name="google-site-verification" content="dummy" />', ""
        )
        (self.root / "index.html").write_text(stripped, encoding="utf-8")
        result = run_script(self.root)
        self.assertNotEqual(result.returncode, 0)

    # --- STEP 12C: category pages / related articles / breadcrumbs / -----
    # --- HTML sitemap / fail-closed categorization --------------------

    def test_refuses_to_run_if_a_new_article_has_no_category_assigned(self) -> None:
        # A slug with no entry at all in the real script's
        # ARTICLE_CATEGORIES dict must stop the run, not silently omit
        # the article from category pages / related articles / the HTML
        # sitemap.
        add_article(self.root, "totally-unclassified-slug", "Nope")
        result = run_script(self.root)
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("totally-unclassified-slug", result.stdout + result.stderr)

    def test_category_page_is_generated_and_lists_its_member_article(self) -> None:
        run_script(self.root)
        category_page = self.root / "category" / "sleep-comfort" / "index.html"
        self.assertTrue(category_page.exists())
        text = category_page.read_text(encoding="utf-8")
        self.assertIn('<a href="/articles/care-bed/">Alpha Title</a>', text)
        self.assertIn('<link rel="canonical" href="https://senior-dog-guide.pages.dev/category/sleep-comfort/">', text)

    def test_article_is_reachable_from_its_category_page(self) -> None:
        run_script(self.root)
        category_page = (self.root / "category" / "sleep-comfort" / "index.html").read_text(encoding="utf-8")
        self.assertIn('href="/articles/care-bed/"', category_page)

    def test_homepage_category_card_links_to_category_page_not_one_article(self) -> None:
        run_script(self.root)
        index_html = (self.root / "index.html").read_text(encoding="utf-8")
        self.assertIn('href="/category/sleep-comfort/"', index_html)
        # The old hand-picked single-representative-article pattern must
        # be gone after migration, not merely appended-to.
        self.assertNotIn("Dummy category", index_html)

    def test_html_sitemap_page_is_generated_and_lists_every_article(self) -> None:
        add_article(self.root, "pet-heater", "Beta Title")
        run_script(self.root)
        html_sitemap = (self.root / "articles" / "index.html").read_text(encoding="utf-8")
        self.assertIn('href="/articles/care-bed/"', html_sitemap)
        self.assertIn('href="/articles/pet-heater/"', html_sitemap)

    def test_html_sitemap_is_listed_in_xml_sitemap(self) -> None:
        run_script(self.root)
        sitemap = (self.root / "sitemap.xml").read_text(encoding="utf-8")
        self.assertIn("<loc>https://senior-dog-guide.pages.dev/articles/</loc>", sitemap)

    def test_related_articles_block_appears_and_excludes_self(self) -> None:
        add_article(self.root, "pet-heater", "Beta Title")  # same category: sleep-comfort
        run_script(self.root)
        care_bed = (self.root / "articles" / "care-bed" / "index.html").read_text(encoding="utf-8")
        self.assertIn('href="/articles/pet-heater/"', care_bed)
        self.assertNotIn('href="/articles/care-bed/"', care_bed.split("AUTO-GENERATED:RELATED:START")[1])

    def test_related_articles_falls_back_to_another_category_when_short(self) -> None:
        # care-bed's own category (sleep-comfort) has no other member in
        # this fixture at all -- the related block must still be
        # populated, from some other category, rather than left empty.
        add_article(self.root, "dish-stand", "Gamma Title")  # different category: feeding-support
        run_script(self.root)
        care_bed = (self.root / "articles" / "care-bed" / "index.html").read_text(encoding="utf-8")
        related_block = care_bed.split("AUTO-GENERATED:RELATED:START")[1].split("AUTO-GENERATED:RELATED:END")[0]
        self.assertIn('href="/articles/dish-stand/"', related_block)

    def test_breadcrumb_html_and_jsonld_present_on_article(self) -> None:
        run_script(self.root)
        care_bed = (self.root / "articles" / "care-bed" / "index.html").read_text(encoding="utf-8")
        self.assertIn('<nav class="breadcrumbs" aria-label="breadcrumb">', care_bed)
        self.assertIn('href="/"', care_bed.split("AUTO-GENERATED:BREADCRUMB:START")[1].split("AUTO-GENERATED:BREADCRUMB:END")[0])
        self.assertIn('"@type": "BreadcrumbList"', care_bed)

    def test_breadcrumb_jsonld_is_valid_json(self) -> None:
        import json as json_module
        run_script(self.root)
        care_bed = (self.root / "articles" / "care-bed" / "index.html").read_text(encoding="utf-8")
        block = care_bed.split('<script type="application/ld+json">')[1].split("</script>")[0]
        parsed = json_module.loads(block)
        self.assertEqual(parsed["@type"], "BreadcrumbList")
        self.assertEqual(parsed["itemListElement"][-1]["item"], "https://senior-dog-guide.pages.dev/articles/care-bed/")

    def test_category_breadcrumb_present(self) -> None:
        run_script(self.root)
        category_page = (self.root / "category" / "sleep-comfort" / "index.html").read_text(encoding="utf-8")
        self.assertIn('<nav class="breadcrumbs"', category_page)

    def test_rerunning_after_migration_does_not_duplicate_generated_blocks(self) -> None:
        # First run inserts the marker pairs (no markers existed yet in
        # the fixture, matching the real repo's pre-STEP-12C state);
        # second run must edit between them, not insert a second copy.
        run_script(self.root)
        commit_all(self.root)
        run_script(self.root)
        care_bed = (self.root / "articles" / "care-bed" / "index.html").read_text(encoding="utf-8")
        for marker in (
            "AUTO-GENERATED:BREADCRUMB:START", "AUTO-GENERATED:RELATED:START",
            "AUTO-GENERATED:JSONLD:START",
        ):
            self.assertEqual(care_bed.count(marker), 1, f"{marker} appears {care_bed.count(marker)} times")
        index_html = (self.root / "index.html").read_text(encoding="utf-8")
        self.assertEqual(index_html.count("AUTO-GENERATED:CATEGORIES:START"), 1)

    def test_check_detects_missing_regeneration_after_new_article_added(self) -> None:
        run_script(self.root)
        commit_all(self.root)
        add_article(self.root, "pet-heater", "Beta Title")
        result = run_script(self.root, "--check")
        self.assertEqual(result.returncode, 1)
        self.assertIn("out of date", result.stdout)

    # --- Mechanical whole-site crawl (orphan / dedup / canonical) ---------

    def test_no_orphan_pages_after_generation(self) -> None:
        """Every generated page must be reachable, by internal <a href>,
        starting from index.html -- exactly the same check the real
        production site was audited with in STEP 12B."""
        add_article(self.root, "pet-heater", "Beta Title")
        add_article(self.root, "dish-stand", "Gamma Title")
        run_script(self.root)

        all_pages = {site_path_for(self.root, p) for p in all_html_files(self.root)}
        reachable = {"/"}
        frontier = ["/"]
        path_to_file = {site_path_for(self.root, p): p for p in all_html_files(self.root)}
        while frontier:
            current = frontier.pop()
            html = path_to_file[current].read_text(encoding="utf-8")
            for href in internal_links_in(html):
                path = urlparse(href).path
                if not path.endswith("/"):
                    continue  # not one of this site's own page URLs
                if path not in reachable and path in all_pages:
                    reachable.add(path)
                    frontier.append(path)

        orphans = all_pages - reachable
        self.assertEqual(orphans, set(), f"orphan pages found: {orphans}")

    def test_all_internal_hrefs_resolve_to_an_existing_generated_page(self) -> None:
        add_article(self.root, "pet-heater", "Beta Title")
        run_script(self.root)
        all_pages = {site_path_for(self.root, p) for p in all_html_files(self.root)}
        for html_file in all_html_files(self.root):
            html = html_file.read_text(encoding="utf-8")
            for href in internal_links_in(html):
                path = urlparse(href).path
                if not path.endswith("/"):
                    continue
                self.assertIn(
                    path, all_pages,
                    f"{html_file.relative_to(self.root)} links to missing page {path}",
                )

    def test_canonical_matches_own_url_on_every_generated_page(self) -> None:
        add_article(self.root, "pet-heater", "Beta Title")
        run_script(self.root)
        for html_file in all_html_files(self.root):
            if html_file == self.root / "index.html":
                continue  # fixture's own index.html keeps its hand-authored <head>
            if html_file.parent.name in ("about", "privacy", "disclosure"):
                continue  # fixture stubs for these have no canonical at all
            text = html_file.read_text(encoding="utf-8")
            match = re.search(r'<link rel="canonical" href="([^"]+)">', text)
            self.assertIsNotNone(match, f"no canonical on {html_file.relative_to(self.root)}")
            own_path = site_path_for(self.root, html_file)
            self.assertEqual(match.group(1), BASE_URL + own_path)

    def test_generated_sitemap_xml_is_well_formed_and_matches_generated_pages(self) -> None:
        add_article(self.root, "pet-heater", "Beta Title")
        run_script(self.root)
        sitemap_text = (self.root / "sitemap.xml").read_text(encoding="utf-8")
        tree = ET.fromstring(sitemap_text)  # raises if not well-formed
        ns = {"s": "http://www.sitemaps.org/schemas/sitemap/0.9"}
        sitemap_paths = {
            urlparse(u.find("s:loc", ns).text).path for u in tree.findall("s:url", ns)
        }
        self.assertIn("/articles/care-bed/", sitemap_paths)
        self.assertIn("/articles/pet-heater/", sitemap_paths)
        self.assertIn("/articles/", sitemap_paths)
        self.assertIn("/category/sleep-comfort/", sitemap_paths)


if __name__ == "__main__":
    unittest.main()
