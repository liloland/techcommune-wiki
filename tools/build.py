#!/usr/bin/env python3
"""Build the TechCommune wiki: content/*.md -> static HTML pages (standard library only).

  python3 tools/build.py --site ~/modern --out build        build the site into ./build
  python3 tools/build.py --check                            only check every page (this is what the pull-request check runs)
  python3 tools/build.py --site ~/modern --out build --release   also refuse placeholder settings (use before publishing)

--site is a copy of the main TechCommune site: its style.css, search.js, search.css and icons are copied so the wiki
folder is self-contained (the site's Content-Security-Policy only allows files from the same origin).
"""
import argparse
import datetime
import json
import os
import re
import shutil
import sys
import tomllib
import urllib.parse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mdlite import MarkdownError, Renderer, SLUG_RE, esc, plain_text   # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ALLOWED_KEYS = {'title', 'category', 'summary', 'date', 'updated', 'author', 'tested_on', 'tags'}
REQUIRED_KEYS = ('title', 'category', 'summary', 'date')
LIMITS = {'title': 80, 'summary': 200, 'author': 60, 'tested_on': 100}
MAX_BODY = 40000
RESERVED_SLUGS = {'index', 'search', 'style', 'wiki', '404'}
SECRET_PATTERNS = [
    (re.compile(r'-----BEGIN [A-Z ]*PRIVATE KEY-----'), 'looks like a private key'),
    (re.compile(r'\bAKIA[0-9A-Z]{16}\b'), 'looks like an AWS access key'),
    (re.compile(r'(?i)\b(password|passwd|secret|api[_-]?key|token)\s*[:=]\s*[\'"]?(?!<|\$|\{|your|changeme|example|xxx|\*)[^\s\'"]{8,}'),
     'looks like a real password or token (use a placeholder such as <password>)'),
]
NAV = [('index.html', 'Home'), ('command-line.html', 'Command Line Tips'), ('cloud-tutorials.html', 'Cloud Tutorials'),
       ('ai.html', 'AI'), ('shell-scripts.html', 'Shell Scripting'), ('sysadmin.html', 'Sysadmin'), ('devops.html', 'DevOps'),
       None,
       ('security.html', 'Security'), ('hardening.html', 'Hardening'), ('tools.html', 'Tools'),
       ('strange-stuff.html', 'Strange Stuff'), ('WIKI', 'Wiki'), ('search.html', 'Search'),
       ('about.html', 'About Me'), ('contact.html', 'Contact')]
NEW_PAGE_TEMPLATE = """---
title: A short, clear title
category: fixes
summary: One sentence that says what this page helps with.
date: {today}
author: Your name or nickname (optional)
tested_on: Ubuntu 24.04, for example (optional)
tags: disk, cleanup
---

## The problem

What you saw, with the exact error message if there was one.

## What worked

```bash
the-command --you-ran
```

## Why it works

A sentence or two.
"""


class Problem:
    def __init__(self, path, line, message, error=True):
        self.path, self.line, self.message, self.error = path, line, message, error

    def __str__(self):
        loc = '%s:%s' % (self.path, self.line) if self.line else self.path
        return '%s: %s: %s' % (loc, 'error' if self.error else 'warning', self.message)


class Page:
    pass


def load_config(root=ROOT):
    with open(os.path.join(root, 'wiki.toml'), 'rb') as f:
        cfg = tomllib.load(f)
    cfg.setdefault('site_url', '/')
    if not cfg['site_url'].endswith('/'):
        cfg['site_url'] += '/'
    cfg['repo_url'] = cfg['repo_url'].rstrip('/')
    return cfg


def parse_front_matter(text, rel, problems):
    """Return (meta dict, body, line number of first body line) or None."""
    lines = text.split('\n')
    if not lines or lines[0].strip() != '---':
        problems.append(Problem(rel, 1, 'the page must start with a line containing only ---, then title:, category:, summary: and date:'))
        return None
    meta, end = {}, None
    for idx in range(1, len(lines)):
        ln = lines[idx]
        if ln.strip() == '---':
            end = idx
            break
        if not ln.strip():
            continue
        m = re.match(r'^([a-z_]+):\s*(.*?)\s*$', ln)
        if not m:
            problems.append(Problem(rel, idx + 1, 'front matter lines look like  key: value'))
            continue
        key, val = m.groups()
        if key not in ALLOWED_KEYS:
            problems.append(Problem(rel, idx + 1, 'unknown front matter key "%s" (allowed: %s)' % (key, ', '.join(sorted(ALLOWED_KEYS)))))
        elif key in meta:
            problems.append(Problem(rel, idx + 1, 'front matter key "%s" appears twice' % key))
        else:
            meta[key] = val
    if end is None:
        problems.append(Problem(rel, 1, 'front matter is never closed: add a line with only --- after it'))
        return None
    return meta, '\n'.join(lines[end + 1:]), end + 2


def check_meta(meta, rel, cats, problems):
    ok = True
    for k in REQUIRED_KEYS:
        if not meta.get(k):
            problems.append(Problem(rel, None, 'missing required front matter: %s' % k))
            ok = False
    for k, mx in LIMITS.items():
        if len(meta.get(k, '')) > mx:
            problems.append(Problem(rel, None, '%s is longer than %d characters' % (k, mx)))
            ok = False
    if meta.get('category') and meta['category'] not in cats:
        problems.append(Problem(rel, None, 'category "%s" is not one of: %s' % (meta['category'], ', '.join(cats))))
        ok = False
    for k in ('date', 'updated'):
        if meta.get(k):
            try:
                datetime.date.fromisoformat(meta[k])
            except ValueError:
                problems.append(Problem(rel, None, '%s must look like 2026-10-31' % k))
                ok = False
    tags = [t.strip() for t in meta.get('tags', '').split(',') if t.strip()]
    if len(tags) > 6 or any(not re.match(r'^[a-z0-9][a-z0-9-]{0,23}$', t) for t in tags):
        problems.append(Problem(rel, None, 'tags: up to 6, lowercase letters, numbers and hyphens, separated by commas'))
        ok = False
    meta['_tags'] = tags
    return ok


def load_pages(root, cfg, problems):
    cats = [c['slug'] for c in cfg['categories']]
    pages = {}
    cdir = os.path.join(root, 'content')
    for name in sorted(os.listdir(cdir)):
        if name.startswith(('_', '.')) or not name.endswith('.md'):
            continue
        rel = 'content/' + name
        slug = name[:-3]
        if not SLUG_RE.match(slug) or slug in RESERVED_SLUGS or slug.startswith('category-'):
            problems.append(Problem(rel, None, 'file name must be lowercase letters, numbers and hyphens (like disk-full.md) and not a reserved name'))
            continue
        with open(os.path.join(cdir, name), encoding='utf-8') as f:
            text = f.read().replace('\r\n', '\n')
        parsed = parse_front_matter(text, rel, problems)
        if not parsed:
            continue
        meta, body, first = parsed
        check_meta(meta, rel, cats, problems)          # keep going on bad settings so the page text is checked too
        if len(body) > MAX_BODY:
            problems.append(Problem(rel, None, 'page is longer than %d characters: split it into two pages' % MAX_BODY))
            continue
        if not body.strip():
            problems.append(Problem(rel, None, 'the page has no text after the front matter'))
            continue
        for idx, ln in enumerate(body.split('\n')):
            for rx, why in SECRET_PATTERNS:
                if rx.search(ln):
                    problems.append(Problem(rel, first + idx, why))
        p = Page()
        p.slug, p.rel, p.meta, p.body, p.first = slug, rel, meta, body, first
        p.title, p.category = meta.get('title', slug), meta.get('category', '')
        pages[slug] = p
    return pages


def render_pages(pages, cfg, problems):
    titles = {s: p.title for s, p in pages.items()}
    for p in pages.values():
        r = Renderer(titles, cfg['site_url'])
        try:
            p.html = r.render(p.body, p.first)
        except MarkdownError as e:
            problems.append(Problem(p.rel, e.line, e.message))
            p.html = None
            continue
        for ln, msg in r.warnings:
            problems.append(Problem(p.rel, ln, msg, error=False))
        p.text = plain_text(p.body)


# ---- HTML -------------------------------------------------------------------------------------------------------------
def head(cfg, title, extra_css=()):
    css = ''.join('\n    <link rel="stylesheet" href="%s">' % c for c in ('style.css', 'wiki.css') + tuple(extra_css))
    return f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta name="color-scheme" content="dark light">
    <link rel="icon" href="favicon.svg" type="image/svg+xml">
    <link rel="icon" href="favicon.ico" sizes="any">
    <link rel="apple-touch-icon" href="apple-touch-icon.png">
    <title>{esc(title)}</title>{css}
</head>
<body>
    <div class="container">
'''


def nav(cfg, active):
    out = ['        <div class="tabs">']
    for item in NAV:
        if item is None:
            out.append('            <span class="tabs-break"></span>')
            continue
        href, label = item
        if href == 'WIKI':
            href = 'index.html'
        else:
            href = cfg['site_url'] + href
        cls = 'tab active' if active == label else 'tab'
        out.append(f'            <a class="{cls}" href="{esc(href)}">{esc(label)}</a>')
    out.append('        </div>')
    return '\n'.join(out) + '\n'


def terminal(cmd):
    return f'''        <div class="terminal-header">
            <div class="prompt">techcommune@linux:~$ </div>
            <span>{esc(cmd)}</span>
            <span class="cursor"></span>
        </div>
'''


def footer(cfg, quip):
    return f'''
        <hr>
        <p class="wiki-license">Content on this wiki is shared under <a href="{esc(cfg['license_url'])}" rel="noopener noreferrer">{esc(cfg['license_name'])}</a>.
        Run commands from community pages with care: read them first, and try them somewhere safe.</p>
        <p class="site-footer">
            &copy; 2026 TechCommune. All rights reserved.<br>
            <span class="quip">"{esc(quip)}"</span>
        </p>
    </div>
</body>
</html>
'''


def page_html(cfg, p, cat_title):
    m = p.meta
    bits = [f'<span class="badge">{esc(cat_title)}</span>', f'Added {esc(m["date"])}']
    if m.get('updated'):
        bits.append(f'Updated {esc(m["updated"])}')
    if m.get('author'):
        bits.append(f'By {esc(m["author"])}')
    if m.get('tested_on'):
        bits.append(f'Tested on: {esc(m["tested_on"])}')
    edit = f'{cfg["repo_url"]}/edit/{cfg["repo_branch"]}/content/{p.slug}.md'
    new = new_page_url(cfg)
    tags = ''.join(f'<span class="badge">{esc(t)}</span>' for t in m['_tags'])
    return (head(cfg, f'{cfg["title"]} - {p.title}') + nav(cfg, 'Wiki') + terminal(f'cat wiki/{p.slug}.md') + f'''
        <h1>{esc(p.title)}</h1>
        <p class="wiki-meta">{' &middot; '.join(bits)}</p>
        <p class="wiki-summary">{esc(m['summary'])}</p>

        <div class="wiki-body">
{p.html}
        </div>
''' + (f'        <p class="wiki-tags">{tags}</p>\n' if tags else '') + f'''
        <div class="wiki-actions">
            <a class="wiki-btn" href="{esc(edit)}" rel="noopener noreferrer">&#9998; Improve this page</a>
            <a class="wiki-btn" href="{esc(new)}" rel="noopener noreferrer">&#10010; Add a new page</a>
            <a class="wiki-btn" href="index.html">&larr; Back to the wiki</a>
        </div>
''' + footer(cfg, 'A wiki is just documentation with commit access.'))


def new_page_url(cfg):
    value = NEW_PAGE_TEMPLATE.format(today='YYYY-MM-DD')
    q = urllib.parse.urlencode({'filename': 'your-page-name.md', 'value': value}, quote_via=urllib.parse.quote)
    return f'{cfg["repo_url"]}/new/{cfg["repo_branch"]}/content?{q}'


def list_html(pages, with_summary=True):
    if not pages:
        return '        <p class="docs-note">No pages here yet. <a href="how-to-contribute.html">Be the first to add one.</a></p>\n'
    items = []
    for p in pages:
        s = f' <span class="wiki-sum">&mdash; {esc(p.meta["summary"])}</span>' if with_summary else ''
        items.append(f'            <li><a href="{esc(p.slug)}.html">{esc(p.title)}</a>{s}</li>')
    return '        <ul class="wiki-list">\n' + '\n'.join(items) + '\n        </ul>\n'


def index_html(cfg, pages):
    by_cat = {c['slug']: [] for c in cfg['categories']}
    for p in pages.values():
        by_cat[p.category].append(p)
    for lst in by_cat.values():
        lst.sort(key=lambda p: p.title.lower())
    recent = sorted((p for p in pages.values() if p.category != 'about'), key=lambda p: (p.meta['date'], p.title), reverse=True)[:5]
    out = head(cfg, cfg['title']) + nav(cfg, 'Wiki') + terminal('ls -lt wiki/ | head') + f'''
        <h1>📖 {esc(cfg['title'])}</h1>
        <p class="center">{esc(cfg['tagline'])}</p>

        <div class="wiki-actions center">
            <a class="wiki-btn" href="how-to-contribute.html">&#10010; How to add a page</a>
            <a class="wiki-btn" href="search.html">&#128269; Search the wiki</a>
        </div>
'''
    if recent:
        out += '\n        <h2>Latest pages</h2>\n' + list_html(recent)
    for c in cfg['categories']:
        out += f'\n        <h2><a class="wiki-cat" href="category-{esc(c["slug"])}.html">{esc(c["title"])}</a></h2>\n        <p class="docs-note">{esc(c["blurb"])}</p>\n'
        out += list_html(by_cat[c['slug']])
    return out + footer(cfg, 'The nice thing about a community wiki is that other people also forgot the flag.')


def category_html(cfg, c, pages):
    lst = sorted((p for p in pages.values() if p.category == c['slug']), key=lambda p: p.title.lower())
    return (head(cfg, f'{cfg["title"]} - {c["title"]}') + nav(cfg, 'Wiki') + terminal(f'ls wiki/{c["slug"]}/') + f'''
        <h1>{esc(c['title'])}</h1>
        <p class="center">{esc(c['blurb'])}</p>
''' + list_html(lst) + '''
        <p class="wiki-actions"><a class="wiki-btn" href="index.html">&larr; Back to the wiki</a></p>
''' + footer(cfg, 'ls: cannot access the answer: Permission denied'))


def search_html(cfg):
    return (head(cfg, f'{cfg["title"]} - Search', ('search.css',)) + nav(cfg, 'Wiki') + terminal('grep -ri "your search" wiki/') + '''
        <h1>🔍 Search the wiki</h1>
        <p class="center">This searches the wiki only. <a href="''' + esc(cfg['site_url']) + '''search.html">Search the whole site</a> instead.</p>

        <form class="search-box" id="search-form">
            <input type="search" id="q" placeholder="Try: disk full, rsync, cron ..." autocomplete="off" autofocus aria-label="Search the wiki">
            <button type="button" id="clear-btn">Clear</button>
        </form>
        <div class="search-filters" id="filters"></div>
        <div id="search-status"></div>
        <div id="results"></div>

        <div class="search-help" id="help">
            <h2>Search Tips</h2>
            <ul>
                <li>Type several words to find pages that contain <strong>all</strong> of them</li>
                <li>Use quotes for an exact phrase: <code>"no space left"</code></li>
                <li>Press <code>/</code> anywhere on this page to jump to the search box</li>
            </ul>
        </div>
''' + footer(cfg, 'Ctrl+F is just grep with a friendlier face.').replace('    </div>\n</body>', '    </div>\n\n    <script src="wiki-search-index.js"></script>\n    <script src="search.js"></script>\n</body>'))


def search_index(cfg, pages):
    cats = {c['slug']: c['title'] for c in cfg['categories']}
    entries = [{'title': p.title, 'section': cats[p.category], 'url': p.slug + '.html', 'isDoc': True,
                'text': p.title + '\n\n' + p.meta['summary'] + '\n\n' + p.text} for p in sorted(pages.values(), key=lambda p: p.slug)]
    return 'window.SEARCH_INDEX = ' + json.dumps(entries, ensure_ascii=False, indent=0) + ';\n'


def build(root, site, out, check_only=False, release=False):
    problems = []
    cfg = load_config(root)
    if release and ('OWNER' in cfg['repo_url'] or cfg['repo_url'].count('/') < 4):
        problems.append(Problem('wiki.toml', None, 'repo_url is still a placeholder: set it to the real public repository before publishing'))
    pages = load_pages(root, cfg, problems)
    render_pages(pages, cfg, problems)
    good = {s: p for s, p in pages.items() if getattr(p, 'html', None) is not None}
    errors = [p for p in problems if p.error]
    if check_only or errors:
        return problems, good
    needed = ['style.css', 'search.js', 'search.css']
    for n in needed:
        if not os.path.exists(os.path.join(site, n)):
            problems.append(Problem('--site', None, 'the site folder %s has no %s' % (site, n)))
    if any(p.error for p in problems):
        return problems, good
    if os.path.isdir(out):
        shutil.rmtree(out)
    os.makedirs(out)
    for n in needed + ['favicon.svg', 'favicon.ico', 'apple-touch-icon.png']:
        src = os.path.join(site, n)
        if os.path.exists(src):
            shutil.copy(src, os.path.join(out, n))
    shutil.copy(os.path.join(root, 'templates', 'wiki.css'), os.path.join(out, 'wiki.css'))
    cats = {c['slug']: c for c in cfg['categories']}

    def write(name, text):
        with open(os.path.join(out, name), 'w', encoding='utf-8') as f:
            f.write(text)

    for s, p in good.items():
        write(s + '.html', page_html(cfg, p, cats[p.category]['title']))
    for c in cfg['categories']:
        write('category-%s.html' % c['slug'], category_html(cfg, c, good))
    write('index.html', index_html(cfg, good))
    write('search.html', search_html(cfg))
    write('wiki-search-index.js', search_index(cfg, good))
    return problems, good


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--site', default=os.path.expanduser('~/modern'), help='copy of the main site (for style.css and friends)')
    ap.add_argument('--out', default=os.path.join(ROOT, 'build'))
    ap.add_argument('--check', action='store_true', help='check the pages only, write nothing')
    ap.add_argument('--release', action='store_true', help='also refuse placeholder settings')
    ap.add_argument('--root', default=ROOT, help=argparse.SUPPRESS)
    a = ap.parse_args(argv)
    problems, pages = build(a.root, a.site, a.out, a.check, a.release)
    for p in problems:
        print(p, file=sys.stderr)
    errs = sum(1 for p in problems if p.error)
    warns = len(problems) - errs
    if errs:
        print('%d error(s), %d warning(s): nothing was written' % (errs, warns), file=sys.stderr)
        return 1
    print('%s %d page(s)%s' % ('checked' if a.check else 'built', len(pages), (', %d warning(s)' % warns) if warns else ''))
    return 0


if __name__ == '__main__':
    sys.exit(main())
