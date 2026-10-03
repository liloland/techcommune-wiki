"""A deliberately small Markdown renderer for the TechCommune wiki.

Safety rules (they are the point of this file):
  * Every piece of text is HTML-escaped. Raw HTML in a page is shown as text, never run.
  * Links are checked against an allow-list: https:// , site:<path> , [[page-slug]] , wiki:search and wiki:index only.
  * Images are not supported.
Anything not understood is an error that names the line, so a contributor sees the problem in the pull request.
"""
import html
import re


class MarkdownError(Exception):
    def __init__(self, message, line=None):
        super().__init__(message)
        self.message = message
        self.line = line


SLUG_RE = re.compile(r'^[a-z0-9]+(?:-[a-z0-9]+)*$')
LANG_RE = re.compile(r'^[a-z0-9+#-]{0,20}$')
SITE_PATH_RE = re.compile(r'^[A-Za-z0-9_./-]+(?:#[A-Za-z0-9_-]+)?$')
HTTPS_RE = re.compile(r'^https://[A-Za-z0-9.-]+(?::\d+)?(?:[/?#][^\s<>"\']*)?$')
LINK_RE = re.compile(r'\[\[([^\]\n]+)\]\]|\[([^\]\n]+)\]\(([^)\s]*)\)')
CODE_SPAN_RE = re.compile(r'(`+)(.+?)\1')
BOLD_RE = re.compile(r'\*\*(?=\S)(.+?)(?<=\S)\*\*')
ITALIC_RE = re.compile(r'(?<![*\w])\*(?=[^\s*])(.+?)(?<=[^\s*])\*(?![*\w])')
HTML_TAGISH_RE = re.compile(r'<[A-Za-z/!?]')


def esc(s):
    return html.escape(s, quote=True)


def heading_id(text):
    s = re.sub(r'[^a-z0-9]+', '-', text.lower()).strip('-')
    return s or 'section'


class Renderer:
    """pages: {slug: title} for [[slug]] links. site_url: prefix for site: links."""

    def __init__(self, pages, site_url='/'):
        self.pages = pages
        self.site_url = site_url
        self.warnings = []          # (line, message)
        self.links = set()          # [[slug]] targets used

    # ---- inline -------------------------------------------------------------------------------------------------
    def _format_text(self, s):
        s = esc(s)
        s = BOLD_RE.sub(r'<strong>\1</strong>', s)
        s = ITALIC_RE.sub(r'<em>\1</em>', s)
        return s

    def _link(self, m, line):
        if m.group(1) is not None:                       # [[slug]]
            slug = m.group(1).strip()
            if slug not in self.pages:
                raise MarkdownError('[[%s]] points to a page that does not exist' % slug, line)
            self.links.add(slug)
            return '<a href="%s.html">%s</a>' % (esc(slug), esc(self.pages[slug]))
        text, target = m.group(2), m.group(3)
        if HTTPS_RE.match(target):
            return '<a href="%s" rel="noopener noreferrer nofollow ugc">%s</a>' % (esc(target), esc(text))
        if target.startswith('site:'):
            path = target[5:]
            if not SITE_PATH_RE.match(path) or '..' in path or path.startswith('/'):
                raise MarkdownError('bad site: link "%s"' % target, line)
            return '<a href="%s%s">%s</a>' % (esc(self.site_url), esc(path), esc(text))
        if target in ('wiki:search', 'wiki:index'):
            return '<a href="%s.html">%s</a>' % (target[5:], esc(text))
        if re.match(r'^#[a-z0-9-]+$', target):
            return '<a href="%s">%s</a>' % (esc(target), esc(text))
        raise MarkdownError('link "%s" is not allowed: use https://..., site:path/page.html, [[page-slug]], wiki:search or wiki:index' % target, line)

    def inline(self, text, line=None):
        out, pos = [], 0
        parts = []                                       # split on code spans first so their content is never touched
        for m in CODE_SPAN_RE.finditer(text):
            parts.append(('t', text[pos:m.start()]))
            parts.append(('c', m.group(2).strip()))
            pos = m.end()
        parts.append(('t', text[pos:]))
        for kind, chunk in parts:
            if kind == 'c':
                out.append('<code>%s</code>' % esc(chunk))
                continue
            if '![' in chunk:
                raise MarkdownError('images are not supported', line)
            if HTML_TAGISH_RE.search(chunk):
                self.warnings.append((line, 'text that looks like an HTML tag will be shown as plain text; put it in `backticks`'))
            # Links become placeholders first, so **bold** and *italic* can wrap a link; they are put back after formatting.
            chunk = chunk.replace('\x00', '')
            links = []

            def stash(m):
                links.append(self._link(m, line))
                return '\x00%d\x00' % (len(links) - 1)

            chunk = LINK_RE.sub(stash, chunk)
            formatted = self._format_text(chunk)
            out.append(re.sub('\x00(\\d+)\x00', lambda m: links[int(m.group(1))], formatted))
        return ''.join(out)

    # ---- blocks -------------------------------------------------------------------------------------------------
    def render(self, body, first_line=1):
        lines = body.split('\n')
        html_out, i, n = [], 0, len(lines)
        used_ids = {}
        para = []

        def lineno(k):
            return first_line + k

        def flush():
            if para:
                html_out.append('<p>%s</p>' % self.inline(' '.join(s.strip() for s in para), lineno(i - 1)))
                para.clear()

        while i < n:
            line = lines[i]
            stripped = line.strip()
            if stripped.startswith('```'):                                  # fenced code
                flush()
                lang = stripped[3:].strip()
                if not LANG_RE.match(lang):
                    raise MarkdownError('bad code fence language "%s"' % lang, lineno(i))
                start, buf = i, []
                i += 1
                while i < n and lines[i].strip() != '```':
                    buf.append(lines[i])
                    i += 1
                if i >= n:
                    raise MarkdownError('code block opened here is never closed with ```', lineno(start))
                html_out.append('<pre>%s</pre>' % esc('\n'.join(buf)))
                i += 1
                continue
            if not stripped:
                flush()
                i += 1
                continue
            m = re.match(r'^(#{1,6})\s+(.*\S)\s*$', line)
            if m:                                                           # headings
                flush()
                level = len(m.group(1))
                if level == 1:
                    raise MarkdownError('use ## for headings: the page title is already the main heading', lineno(i))
                if level > 3:
                    raise MarkdownError('only ## and ### headings are supported', lineno(i))
                hid = heading_id(m.group(2))
                used_ids[hid] = used_ids.get(hid, 0) + 1
                if used_ids[hid] > 1:
                    hid = '%s-%d' % (hid, used_ids[hid])
                html_out.append('<h%d id="%s">%s</h%d>' % (level, hid, self.inline(m.group(2), lineno(i)), level))
                i += 1
                continue
            if re.match(r'^(-{3,}|\*{3,})\s*$', stripped):                  # rule
                flush()
                html_out.append('<hr>')
                i += 1
                continue
            if stripped.startswith('>'):                                    # quote
                flush()
                buf, start = [], i
                while i < n and lines[i].strip().startswith('>'):
                    buf.append(lines[i].strip()[1:].strip())
                    i += 1
                html_out.append('<blockquote><p>%s</p></blockquote>' % self.inline(' '.join(buf), lineno(start)))
                continue
            if re.match(r'^\s*([-*]|\d+\.)\s+\S', line):                    # lists (one level)
                flush()
                ordered = bool(re.match(r'^\s*\d+\.', line))
                items, start = [], i
                while i < n and re.match(r'^([-*]|\d+\.)\s+\S', lines[i]):
                    if bool(re.match(r'^\d+\.', lines[i])) != ordered:
                        break
                    item = re.sub(r'^([-*]|\d+\.)\s+', '', lines[i])
                    i += 1
                    while i < n and re.match(r'^\s{2,}\S', lines[i]) and not re.match(r'^\s*([-*]|\d+\.)\s+\S', lines[i]):
                        item += ' ' + lines[i].strip()
                        i += 1
                    items.append(item)
                if i < n and re.match(r'^\s+([-*]|\d+\.)\s+\S', lines[i]):
                    raise MarkdownError('nested lists are not supported: keep lists to one level', lineno(i))
                tag = 'ol' if ordered else 'ul'
                html_out.append('<%s>%s</%s>' % (tag, ''.join('<li>%s</li>' % self.inline(it, lineno(start)) for it in items), tag))
                continue
            if stripped.startswith('|') and i + 1 < n and re.match(r'^\s*\|?[\s:|-]+\|[\s:|-]*$', lines[i + 1]) and '-' in lines[i + 1]:
                flush()                                                     # table
                head = [c.strip() for c in stripped.strip('|').split('|')]
                i += 2
                rows = []
                while i < n and lines[i].strip().startswith('|'):
                    cells = [c.strip() for c in lines[i].strip().strip('|').split('|')]
                    if len(cells) != len(head):
                        raise MarkdownError('table row has %d cells but the header has %d' % (len(cells), len(head)), lineno(i))
                    rows.append(cells)
                    i += 1
                th = ''.join('<th>%s</th>' % self.inline(c, lineno(i)) for c in head)
                tr = ''.join('<tr>%s</tr>' % ''.join('<td>%s</td>' % self.inline(c, lineno(i)) for c in r) for r in rows)
                html_out.append('<div class="wiki-table"><table><tr>%s</tr>%s</table></div>' % (th, tr))
                continue
            para.append(line)
            i += 1
        flush()
        return '\n'.join(html_out)


def plain_text(body):
    """Text for the search index: code kept, markup characters dropped."""
    t = re.sub(r'^```.*$', '', body, flags=re.M)
    t = re.sub(r'\[\[([^\]]+)\]\]', r'\1', t)
    t = re.sub(r'\[([^\]]+)\]\([^)]*\)', r'\1', t)
    t = re.sub(r'^#{1,6}\s+', '', t, flags=re.M)
    t = re.sub(r'[*`>|]', '', t)
    return re.sub(r'\n{3,}', '\n\n', t).strip()
