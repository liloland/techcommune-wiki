"""Tests for the wiki renderer and builder. Run:  python3 -m unittest discover -s tests -v   (from the wiki project folder)"""
import os
import re
import shutil
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, 'tools'))
sys.dont_write_bytecode = True
import build           # noqa: E402
from mdlite import MarkdownError, Renderer   # noqa: E402


def render(md, pages=None):
    return Renderer(pages or {'other-page': 'Other page'}).render(md)


class Escaping(unittest.TestCase):
    def test_script_tag_is_text(self):
        out = render('Hello <script>alert(1)</script> world')
        self.assertNotIn('<script', out)
        self.assertIn('&lt;script&gt;', out)

    def test_attribute_and_entity_tricks(self):
        out = render('"><img src=x onerror=alert(1)> &amp; &lt;')
        self.assertNotIn('<img', out)
        self.assertIn('&amp;amp;', out)          # an entity typed by the user stays literal text

    def test_code_block_and_span_are_escaped(self):
        out = render('```bash\necho "<b>" && cat <file>\n```\n\nUse `a<b` here')
        self.assertIn('echo &quot;&lt;b&gt;&quot; &amp;&amp; cat &lt;file&gt;', out)
        self.assertIn('<code>a&lt;b</code>', out)

    def test_markup_inside_code_is_not_formatted(self):
        self.assertIn('<code>**x**</code>', render('`**x**`'))

    def test_link_text_is_escaped(self):
        out = render('[<b>x</b>](https://example.org/a)')
        self.assertNotIn('<b>', out)


class Links(unittest.TestCase):
    def test_https_link_gets_safe_rel(self):
        out = render('[docs](https://example.org/a?b=1&c=2)')
        self.assertIn('href="https://example.org/a?b=1&amp;c=2"', out)
        self.assertIn('rel="noopener noreferrer nofollow ugc"', out)

    def test_bad_schemes_are_errors(self):
        for target in ('javascript:alert(1)', 'JaVaScRiPt:alert(1)', 'data:text/html,hi', 'http://example.org',
                       'mailto:a@b.c', '//example.org', '/dashboard/', 'other-page.html', 'https://x"onmouseover="y'):
            with self.assertRaises(MarkdownError, msg=target):
                render('[x](%s)' % target)

    def test_targets_with_spaces_are_not_links_at_all(self):
        for t in ('https://a b', 'site:a b'):
            out = render('[x](%s)' % t)
            self.assertNotIn('<a ', out, t)

    def test_images_are_errors(self):
        with self.assertRaises(MarkdownError):
            render('![alt](https://example.org/a.png)')

    def test_wiki_and_site_links(self):
        out = render('See [[other-page]] and [rsync](site:docs/sysadmin/rsync.html).')
        self.assertIn('<a href="other-page.html">Other page</a>', out)
        self.assertIn('<a href="/docs/sysadmin/rsync.html">rsync</a>', out)

    def test_wiki_special_links(self):
        out = render('[s](wiki:search) [i](wiki:index)')
        self.assertIn('<a href="search.html">s</a>', out)
        self.assertIn('<a href="index.html">i</a>', out)
        with self.assertRaises(MarkdownError):
            render('[x](wiki:../etc)')

    def test_missing_wiki_page_is_error(self):
        with self.assertRaises(MarkdownError):
            render('[[nope]]')

    def test_site_link_traversal_is_error(self):
        for t in ('site:../etc/passwd', 'site:/x', 'site:a/../b'):
            with self.assertRaises(MarkdownError, msg=t):
                render('[x](%s)' % t)


class Blocks(unittest.TestCase):
    def test_headings_lists_tables(self):
        out = render('## One\n\n- a\n- b\n\n1. x\n2. y\n\n| A | B |\n|---|---|\n| 1 | 2 |\n')
        self.assertIn('<h2 id="one">One</h2>', out)
        self.assertIn('<ul><li>a</li><li>b</li></ul>', out)
        self.assertIn('<ol><li>x</li><li>y</li></ol>', out)
        self.assertIn('<th>A</th>', out)
        self.assertIn('<td>2</td>', out)

    def test_h1_is_error(self):
        with self.assertRaises(MarkdownError):
            render('# Title')

    def test_nested_list_is_error(self):
        with self.assertRaises(MarkdownError):
            render('- a\n  - b\n')

    def test_unclosed_fence_is_error(self):
        with self.assertRaises(MarkdownError) as cm:
            render('text\n\n```\nnever closed')
        self.assertEqual(cm.exception.line, 3)

    def test_bold_italic(self):
        out = render('**bold** and *em* and snake_case_name and 2*3*4')
        self.assertIn('<strong>bold</strong>', out)
        self.assertIn('<em>em</em>', out)
        self.assertIn('snake_case_name', out)

    def test_bold_can_wrap_a_link(self):
        out = render('**Read the [[other-page]].** Then [go](https://example.org) *now*.')
        self.assertIn('<strong>Read the <a href="other-page.html">Other page</a>.</strong>', out)
        self.assertIn('<em>now</em>', out)

    def test_nul_characters_cannot_forge_a_link_slot(self):
        out = render('x \x000\x00 [a](https://example.org)')
        self.assertEqual(out.count('<a '), 1)
        self.assertNotIn('\x00', out)

    def test_table_row_width_mismatch(self):
        with self.assertRaises(MarkdownError):
            render('| A | B |\n|---|---|\n| 1 |\n')


class Pages(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.root = os.path.join(self.tmp, 'proj')
        shutil.copytree(ROOT, self.root, ignore=shutil.ignore_patterns('content', 'build', '.git', '__pycache__'))
        os.makedirs(os.path.join(self.root, 'content'))
        self.site = os.path.join(self.tmp, 'site')
        os.makedirs(self.site)
        for n in ('style.css', 'search.js', 'search.css', 'logo-nav-dark.svg', 'logo-nav-light.svg'):
            with open(os.path.join(self.site, n), 'w') as f:
                f.write('/* stub */')

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def add(self, name, text):
        with open(os.path.join(self.root, 'content', name), 'w') as f:
            f.write(text)

    GOOD = '---\ntitle: Good page\ncategory: fixes\nsummary: A summary.\ndate: 2026-10-03\n---\n\n## Hi\n\ntext\n'

    def run_build(self, **kw):
        return build.build(self.root, self.site, os.path.join(self.tmp, 'out'), **kw)

    def errors(self, problems):
        return [str(p) for p in problems if p.error]

    def test_good_page_builds_and_output_has_no_inline_code(self):
        self.add('good-page.md', self.GOOD)
        problems, pages = self.run_build()
        self.assertEqual(self.errors(problems), [])
        out = os.path.join(self.tmp, 'out')
        for name in os.listdir(out):
            if name.endswith('.html'):
                with open(os.path.join(out, name)) as f:
                    h = f.read()
                self.assertIsNone(re.search(r'<script(?![^>]*\ssrc=)', h), name)
                self.assertNotIn('<style', h, name)
                self.assertIsNone(re.search(r'\sstyle=', h), name)
                self.assertIsNone(re.search(r'\son[a-z]+=', h), name)
        self.assertTrue(os.path.exists(os.path.join(out, 'wiki-search-index.js')))

    def test_front_matter_errors_are_reported_together(self):
        self.add('bad.md', '---\ntitle: T\ncategory: nonsense\nsummary: s\ndate: 31-10-2026\nfoo: x\n---\n\nbody\n')
        problems, _ = self.run_build(check_only=True)
        text = '\n'.join(self.errors(problems))
        self.assertIn('unknown front matter key "foo"', text)

    def test_bad_category_and_date(self):
        self.add('bad.md', '---\ntitle: T\ncategory: nonsense\nsummary: s\ndate: 31-10-2026\n---\n\nbody\n')
        text = '\n'.join(self.errors(self.run_build(check_only=True)[0]))
        self.assertIn('category "nonsense"', text)
        self.assertIn('date must look like', text)

    def test_bad_settings_and_bad_text_are_reported_together(self):
        self.add('both.md', '---\ntitle: T\ncategory: help\nsummary: s\ndate: 31-10-2026\n---\n\n# Big\n\n[x](javascript:alert(1))\n')
        text = '\n'.join(self.errors(self.run_build(check_only=True)[0]))
        self.assertIn('category "help"', text)
        self.assertIn('use ## for headings', text)

    def test_bad_file_names(self):
        for name in ('Bad Name.md', 'UPPER.md', 'index.md', 'category-x.md'):
            self.add(name, self.GOOD)
        text = '\n'.join(self.errors(self.run_build(check_only=True)[0]))
        self.assertEqual(text.count('file name must be'), 4)

    def test_secret_detection(self):
        self.add('s.md', self.GOOD + '\npassword = hunter2hunter2\nAKIAABCDEFGHIJKLMNOP\n-----BEGIN RSA PRIVATE KEY-----\n')
        text = '\n'.join(self.errors(self.run_build(check_only=True)[0]))
        self.assertIn('real password', text)
        self.assertIn('AWS', text)
        self.assertIn('private key', text)

    def test_placeholder_password_is_fine(self):
        self.add('s.md', self.GOOD + '\npassword = <password>\npassword: changeme\n')
        self.assertEqual(self.errors(self.run_build(check_only=True)[0]), [])

    def test_broken_wiki_link_names_file_and_line(self):
        self.add('l.md', self.GOOD + '\nSee [[ghost]].\n')
        text = '\n'.join(self.errors(self.run_build(check_only=True)[0]))
        self.assertIn('content/l.md:', text)
        self.assertIn('[[ghost]]', text)

    def test_nothing_written_when_there_are_errors(self):
        self.add('bad.md', '---\ntitle: T\n---\n\nbody\n')
        self.run_build()
        self.assertFalse(os.path.exists(os.path.join(self.tmp, 'out')))

    def test_release_refuses_placeholder_repo(self):
        self.add('good-page.md', self.GOOD)
        toml = os.path.join(self.root, 'wiki.toml')
        with open(toml) as f:
            text = f.read()
        with open(toml, 'w') as f:
            f.write(re.sub(r'^repo_url = .*$', 'repo_url = "https://github.com/OWNER/techcommune-wiki"', text, flags=re.M))
        text = '\n'.join(self.errors(self.run_build(release=True)[0]))
        self.assertIn('repo_url is still a placeholder', text)

    def test_hostile_front_matter_values_are_escaped(self):
        self.add('h.md', '---\ntitle: <img src=x onerror=1>\ncategory: fixes\nsummary: "><script>x</script>\ndate: 2026-10-03\n'
                         'author: <b>me</b>\ntested_on: a" onmouseover="b\n---\n\ntext\n')
        problems, _ = self.run_build()
        self.assertEqual(self.errors(problems), [])
        with open(os.path.join(self.tmp, 'out', 'h.html')) as f:
            h = f.read()
        for bad in ('<img src=x', '<script>x', '<b>me', 'onmouseover="b'):
            self.assertNotIn(bad, h)

    def test_logo_in_the_tab_bar_and_files_copied(self):
        self.add('good-page.md', self.GOOD)
        self.run_build()
        out = os.path.join(self.tmp, 'out')
        with open(os.path.join(out, 'good-page.html')) as f:
            h = f.read()
        self.assertIn('<div class="tabs tabs-logo">', h)
        self.assertIn('srcset="logo-nav-light.svg"', h)
        self.assertIn('src="logo-nav-dark.svg"', h)
        self.assertTrue(os.path.exists(os.path.join(out, 'logo-nav-dark.svg')))
        self.assertTrue(os.path.exists(os.path.join(out, 'logo-nav-light.svg')))

    def test_repo_links(self):
        self.add('good-page.md', self.GOOD)
        self.run_build()
        with open(os.path.join(self.tmp, 'out', 'good-page.html')) as f:
            h = f.read()
        self.assertIn('/edit/main/content/good-page.md', h)
        self.assertIn('/new/main/content?filename=your-page-name.md', h)


if __name__ == '__main__':
    unittest.main()
