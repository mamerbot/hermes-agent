"""Tests for skills/research/llm-wiki/scripts/lint_wiki.py"""

import pytest
from pathlib import Path


SCRIPT_PATH = (
    Path(__file__).resolve().parents[2]
    / "skills"
    / "research"
    / "llm-wiki"
    / "scripts"
    / "lint_wiki.py"
)


def load_module():
    import importlib.util
    spec = importlib.util.spec_from_file_location("lint_wiki", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    import sys
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def wiki_root(tmp_path):
    """Create a minimal valid wiki."""
    wiki = tmp_path / "wiki"
    raw = tmp_path / "raw"
    wiki.mkdir()
    raw.mkdir()
    return tmp_path


@pytest.fixture
def valid_wiki(wiki_root):
    """A minimal but valid wiki with frontmatter and cross-links."""
    (wiki_root / "index.md").write_text(
        "# Wiki Index\n\n| Category | Slug | Title | Created | Sources | Summary |\n"
        "| summary | test-page | Test Page | 2026-04-11 | 1 | A test |\n"
    )
    (wiki_root / "log.md").write_text(
        "# Wiki Log\n\n## [2026-04-11] ingest | Test Page\n"
    )
    p = wiki_root / "wiki" / "summary" / "test-page.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        "---\ntitle: Test Page\ncreated: 2026-04-11\ntags: [test]\nsources: []\n---\n\n# Test Page\n\n## Summary\nA test.\n\n## Connections\n- [[another-page]]\n"
    )
    return wiki_root


class TestBrokenLinks:
    def test_detects_broken_wikilink(self, wiki_root):
        mod = load_module()
        (wiki_root / "wiki" / "summary").mkdir(parents=True)
        (wiki_root / "wiki" / "summary" / "page-a.md").write_text(
            "---\ntitle: Page A\ncreated: 2026-04-11\n---\n# Page A\n[[nonexistent-page]]\n"
        )
        issues = mod.check_broken_links(wiki_root)
        assert any("nonexistent-page" in i for i in issues)

    def test_no_false_positives_for_valid_links(self, valid_wiki):
        mod = load_module()
        # add a second page that the first links to
        p = valid_wiki / "wiki" / "summary" / "another-page.md"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(
            "---\ntitle: Another Page\ncreated: 2026-04-11\n---\n# Another Page\n"
        )
        issues = mod.check_broken_links(valid_wiki)
        assert issues == []


class TestOrphans:
    def test_detects_page_with_no_inbound_links(self, wiki_root):
        mod = load_module()
        (wiki_root / "wiki" / "entities").mkdir(parents=True)
        (wiki_root / "wiki" / "entities" / "lone-entity.md").write_text(
            "---\ntitle: Lone Entity\ncreated: 2026-04-11\n---\n# Lone Entity\n"
        )
        issues = mod.check_orphans(wiki_root)
        assert any("lone-entity" in i for i in issues)

    def test_index_pages_not_orphans(self, wiki_root):
        mod = load_module()
        (wiki_root / "index.md").write_text("# Index\n")
        issues = mod.check_orphans(wiki_root)
        assert not any("index" in i for i in issues)


class TestFrontmatter:
    def test_detects_missing_frontmatter_start(self, wiki_root):
        mod = load_module()
        (wiki_root / "wiki" / "summary").mkdir(parents=True)
        (wiki_root / "wiki" / "summary" / "no-fm.md").write_text(
            "# No Frontmatter\n\nContent."
        )
        issues = mod.check_frontmatter(wiki_root)
        assert any("no-fm" in i for i in issues)

    def test_detects_missing_required_field(self, wiki_root):
        mod = load_module()
        (wiki_root / "wiki" / "summary").mkdir(parents=True)
        (wiki_root / "wiki" / "summary" / "missing-title.md").write_text(
            "---\ncreated: 2026-04-11\n---\n# Missing Title\n"
        )
        issues = mod.check_frontmatter(wiki_root)
        assert any("missing-title" in i and "title" in i for i in issues)


class TestIndex:
    def test_detects_page_not_in_index(self, wiki_root):
        mod = load_module()
        (wiki_root / "wiki" / "summary").mkdir(parents=True)
        (wiki_root / "wiki" / "summary" / "orphan-summary.md").write_text(
            "---\ntitle: Orphan\ncreated: 2026-04-11\n---\n# Orphan\n"
        )
        (wiki_root / "index.md").write_text("# Wiki Index\n| Category | Slug | Title | Created | Sources | Summary |\n")
        issues = mod.check_index(wiki_root)
        assert any("orphan-summary" in i for i in issues)

    def test_missing_index_file(self, wiki_root):
        mod = load_module()
        issues = mod.check_index(wiki_root)
        assert any("index.md does not exist" in i for i in issues)


class TestLog:
    def test_detects_log_reference_to_missing_page(self, wiki_root):
        mod = load_module()
        (wiki_root / "log.md").write_text(
            "# Wiki Log\n\n## [2026-04-11] ingest | Missing\n[[nonexistent-page]]\n"
        )
        issues = mod.check_log(wiki_root)
        assert any("nonexistent-page" in i for i in issues)


class TestIntegration:
    def test_healthy_wiki_reports_no_issues(self, valid_wiki):
        mod = load_module()
        # add a second page that the first links to, and update index
        p = valid_wiki / "wiki" / "summary" / "another-page.md"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("---\ntitle: Another Page\ncreated: 2026-04-11\n---\n# Another Page\n")

        # update index to include the new page
        idx = valid_wiki / "index.md"
        idx.write_text(
            "# Wiki Index\n\n"
            "| Category | Slug | Title | Created | Sources | Summary |\n"
            "| summary | test-page | Test Page | 2026-04-11 | 1 | A test |\n"
            "| summary | another-page | Another Page | 2026-04-11 | 0 | Links to test-page |\n"
        )

        has_issues = False
        for _, fn in [
            ("Broken wikilinks", mod.check_broken_links),
            ("Orphan pages", mod.check_orphans),
            ("Frontmatter issues", mod.check_frontmatter),
            ("Missing from index", mod.check_index),
        ]:
            if fn(valid_wiki):
                has_issues = True
                break

        assert not has_issues, "Healthy wiki should report no issues"
