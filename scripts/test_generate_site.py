#!/usr/bin/env python3
"""Unit tests for generate_site.py, run against a throwaway copy of a
minimal fake site tree (never against the real repo's files)."""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REAL_SCRIPT = Path(__file__).resolve().parent / "generate_site.py"

INDEX_TEMPLATE = """<!DOCTYPE html>
<html lang="ja">
<head>
<meta name="google-site-verification" content="dummy" />
<title>Fake Site</title>
</head>
<body>
  <section class="categories">
    <ul class="category-list">
      <li class="category-card"><h3>Dummy category</h3></li>
    </ul>
  </section>
  <section class="articles">
    <ul class="article-list">
        <!-- AUTO-GENERATED:ARTICLES:START (managed by scripts/generate_site.py -- do not edit by hand) -->
        <li>
          <a href="/articles/alpha/">Alpha Title</a>
        </li>
        <!-- AUTO-GENERATED:ARTICLES:END -->
    </ul>
  </section>
</body>
</html>
"""

SITEMAP_TEMPLATE = """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url>
    <loc>https://example.pages.dev/</loc>
  </url>
  <url>
    <loc>https://example.pages.dev/articles/alpha/</loc>
  </url>
  <url>
    <loc>https://example.pages.dev/about/</loc>
  </url>
</urlset>
"""


def make_fake_site(root: Path) -> None:
    (root / "articles" / "alpha").mkdir(parents=True)
    (root / "articles" / "alpha" / "index.html").write_text(
        "<title>Alpha Title | Fake Site</title>", encoding="utf-8"
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


class GenerateSiteTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        make_fake_site(self.root)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_check_reports_up_to_date_once_a_regeneration_is_committed(self) -> None:
        # Real workflow: run once, commit the result, then --check (e.g. in
        # CI) should see nothing further to do.
        run_script(self.root)
        subprocess.run(["git", "add", "-A"], cwd=self.root, check=True)
        subprocess.run(["git", "commit", "-q", "-m", "regen"], cwd=self.root, check=True)
        result = run_script(self.root, "--check")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("up to date", result.stdout)

    def test_unchanged_pages_keep_their_original_lastmod_not_today(self) -> None:
        run_script(self.root)
        sitemap = (self.root / "sitemap.xml").read_text(encoding="utf-8")
        self.assertIn("<lastmod>2026-01-01</lastmod>", sitemap)
        self.assertNotIn("<lastmod>2026-09-", sitemap)  # would indicate a "today" bump

    def test_new_article_is_discovered_and_added_to_both_files(self) -> None:
        (self.root / "articles" / "beta").mkdir(parents=True)
        (self.root / "articles" / "beta" / "index.html").write_text(
            "<title>Beta Title | Fake Site</title>", encoding="utf-8"
        )
        result = run_script(self.root)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("beta", result.stdout)

        index_html = (self.root / "index.html").read_text(encoding="utf-8")
        self.assertIn('<a href="/articles/beta/">Beta Title</a>', index_html)
        # Existing entry and everything outside the marker block untouched.
        self.assertIn('<a href="/articles/alpha/">Alpha Title</a>', index_html)
        self.assertIn("Dummy category", index_html)
        self.assertIn("google-site-verification", index_html)

        sitemap = (self.root / "sitemap.xml").read_text(encoding="utf-8")
        self.assertIn("<loc>https://senior-dog-guide.pages.dev/articles/beta/</loc>", sitemap)
        # New, uncommitted file -> today's date, not the fixed fixture date.
        beta_block = sitemap.split("articles/beta/</loc>")[1].split("</url>")[0]
        self.assertNotIn("<lastmod>2026-01-01</lastmod>", beta_block)

    def test_no_duplicate_locs_ever_generated(self) -> None:
        run_script(self.root)
        sitemap = (self.root / "sitemap.xml").read_text(encoding="utf-8")
        locs = [line.strip() for line in sitemap.splitlines() if "<loc>" in line]
        self.assertEqual(len(locs), len(set(locs)))

    def test_existing_urls_are_not_removed_when_nothing_changes(self) -> None:
        run_script(self.root)
        sitemap = (self.root / "sitemap.xml").read_text(encoding="utf-8")
        for expected in ("/", "/articles/alpha/", "/about/", "/privacy/", "/disclosure/"):
            self.assertIn(f"<loc>https://senior-dog-guide.pages.dev{expected}</loc>", sitemap)

    def test_running_again_after_committing_makes_no_further_changes(self) -> None:
        # Once a regeneration is committed (the real workflow), re-running
        # with no new articles must be a true no-op -- this is what
        # protects unrelated pages from being bumped to "today" on every
        # publish.
        run_script(self.root)
        subprocess.run(["git", "add", "-A"], cwd=self.root, check=True)
        subprocess.run(["git", "commit", "-q", "-m", "regen"], cwd=self.root, check=True)
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


if __name__ == "__main__":
    unittest.main()
