#!/usr/bin/env python3
"""
llm-wiki lint — health check for a Karpathy-style LLM wiki.

Checks:
1. Broken wikilinks (pages referencing non-existent slugs)
2. Orphan pages (no inbound links from other pages)
3. Pages missing required frontmatter
4. Stale index entries (pages that exist but aren't in index)
5. Log entries with no corresponding wiki pages

Usage:
    python lint_wiki.py /path/to/wiki/root
"""

import sys
import re
import os
from pathlib import Path
from collections import defaultdict


def get_slug_from_path(path: Path) -> str:
    rel = path.relative_to(path.parent.parent)  # wiki/category/slug.md -> slug
    return rel.stem


def get_all_slugs(wiki_root: Path) -> set:
    slugs = set()
    wiki_dir = wiki_root / "wiki"
    if not wiki_dir.exists():
        return slugs
    for md in wiki_dir.rglob("*.md"):
        slugs.add(md.stem)
    return slugs


def get_all_wikilinks(wiki_root: Path) -> list:
    """Return list of (page_slug, linked_slug) tuples."""
    wiki_dir = wiki_root / "wiki"
    links = []
    if not wiki_dir.exists():
        return links
    for md in wiki_dir.rglob("*.md"):
        slug = md.stem
        content = md.read_text()
        for match in re.finditer(r'\[\[([^\]]+)\]\]', content):
            linked = match.group(1).strip()
            # strip category prefix if present: [[entities/transformers]] -> transformers
            if '/' in linked:
                linked = linked.split('/')[-1]
            links.append((slug, linked))
    return links


def get_inbound_links(wiki_root: Path) -> dict:
    """Map each slug -> set of pages that link to it."""
    inbound = defaultdict(set)
    for _, linked in get_all_wikilinks(wiki_root):
        inbound[linked].add(_)
    return inbound


def check_frontmatter(wiki_root: Path) -> list:
    """Pages missing required frontmatter fields."""
    wiki_dir = wiki_root / "wiki"
    issues = []
    required = ['title', 'created']
    if not wiki_dir.exists():
        return issues
    for md in wiki_dir.rglob("*.md"):
        content = md.read_text()
        if not content.startswith('---'):
            issues.append(f"  {md.relative_to(wiki_root)}: missing frontmatter start")
            continue
        # find end of frontmatter
        end = content.find('---', 3)
        if end == -1:
            issues.append(f"  {md.relative_to(wiki_root)}: missing frontmatter end")
            continue
        front = content[3:end]
        for field in required:
            if not re.search(rf'^{field}:', front, re.MULTILINE):
                issues.append(f"  {md.relative_to(wiki_root)}: missing '{field}' in frontmatter")
    return issues


def check_broken_links(wiki_root: Path) -> list:
    """Wikilinks pointing to non-existent pages."""
    all_slugs = get_all_slugs(wiki_root)
    issues = []
    for page_slug, linked_slug in get_all_wikilinks(wiki_root):
        if linked_slug not in all_slugs:
            issues.append(f"  [[{linked_slug}]] in {page_slug}: page does not exist")
    return issues


def check_orphans(wiki_root: Path) -> list:
    """Pages with no inbound wikilinks and not referenced in index."""
    inbound = get_inbound_links(wiki_root)
    all_slugs = get_all_slugs(wiki_root)
    # pages listed in index are entry points, not orphans
    index_path = wiki_root / "index.md"
    index_slugs = set()
    HEADER_LABELS = {'Category', 'Slug', 'Title', 'Created', 'Sources', 'Summary', ''}
    if index_path.exists():
        for line in index_path.read_text().split('\n'):
            cells = [c.strip() for c in line.split('|')]
            if len(cells) >= 3 and cells[2] not in HEADER_LABELS:
                index_slugs.add(cells[2])
    orphans = [
        s for s in all_slugs
        if s not in inbound and s not in index_slugs and not s.startswith('index')
    ]
    return [f"  {s}: no inbound links" for s in sorted(orphans)]


def check_index(wiki_root: Path) -> list:
    """Pages not listed in index.md."""
    index_path = wiki_root / "index.md"
    if not index_path.exists():
        return ["  index.md does not exist"]
    all_slugs = get_all_slugs(wiki_root)
    index_content = index_path.read_text()
    # Parse table: split by '|' and take the Slug column (index 2)
    indexed = set()
    HEADER_LABELS = {'Category', 'Slug', 'Title', 'Created', 'Sources', 'Summary', ''}
    for line in index_content.split('\n'):
        cells = [c.strip() for c in line.split('|')]
        # cells[0]='', cells[1]=Category, cells[2]=Slug
        if len(cells) >= 3 and cells[2] not in HEADER_LABELS:
            indexed.add(cells[2])
    missing = all_slugs - indexed
    return [f"  {s}: not in index.md" for s in sorted(missing)]


def check_log(wiki_root: Path) -> list:
    """Log entries not matching any page."""
    log_path = wiki_root / "log.md"
    if not log_path.exists():
        return []
    all_slugs = get_all_slugs(wiki_root)
    log_content = log_path.read_text()
    issues = []
    for match in re.finditer(r'\[\[([^\]]+)\]\]', log_content):
        slug = match.group(1).strip()
        if '/' in slug:
            slug = slug.split('/')[-1]
        if slug not in all_slugs:
            issues.append(f"  log references missing page: [[{slug}]]")
    return issues


def main():
    if len(sys.argv) < 2:
        wiki_root = Path(os.environ.get('WIKI_ROOT', '~/llm-wiki')).expanduser()
    else:
        wiki_root = Path(sys.argv[1]).expanduser()

    if not wiki_root.exists():
        print(f"Error: wiki root not found: {wiki_root}")
        sys.exit(1)

    all_checks = [
        ("Broken wikilinks", check_broken_links),
        ("Orphan pages", check_orphans),
        ("Frontmatter issues", check_frontmatter),
        ("Missing from index", check_index),
        ("Log reference issues", check_log),
    ]

    has_issues = False
    for name, fn in all_checks:
        issues = fn(wiki_root)
        if issues:
            has_issues = True
            print(f"\n[{name}]")
            for issue in issues:
                print(issue)

    if not has_issues:
        print("✓ Wiki is healthy")
    else:
        print("\n✗ Issues found")

    # Summary stats
    all_slugs = get_all_slugs(wiki_root)
    print(f"\nWiki stats: {len(all_slugs)} pages")
    wiki_dir = wiki_root / "wiki"
    if wiki_dir.exists():
        categories = list({p.parent.name for p in wiki_dir.rglob("*.md") if p.parent != wiki_dir})
        print(f"Categories: {', '.join(sorted(categories))}")
    log_path = wiki_root / "log.md"
    if log_path.exists():
        log_entries = len(re.findall(r'^## \[', log_path.read_text(), re.MULTILINE))
        print(f"Log entries: {log_entries}")


if __name__ == '__main__':
    main()
