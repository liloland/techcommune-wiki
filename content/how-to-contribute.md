---
title: How to add or improve a page
category: about
summary: Everything you need to propose a fix, a tip or a story, using a GitHub account and your web browser.
date: 2026-10-03
author: TechCommune
tags: contributing, start-here
---

This wiki is a shared notebook for sysadmins. Every page is a plain text file in a public Git repository, and every change goes through a pull request that the site owner reviews before anything is published. There is no form to fill in and no account on this site. You need a free GitHub account and a web browser.

## Before you write

1. **Search first.** Use the [wiki search](wiki:search) and the [site search](site:search.html). If the topic is already covered, improve that page instead of adding a new one.
2. **Pick the right kind of page.** Fixes ("this broke, this worked"), tips (small time savers), experiences (what went wrong and what you learned) and ideas (things worth trying) each have a section on the [wiki home page](wiki:index).
3. **Read the [[wiki-rules]].** They are short, and they keep the wiki safe to read.

## Improve an existing page

1. Open the page and click **Improve this page** at the bottom. GitHub opens its editor.
2. Make your change and describe it in a sentence.
3. Choose to propose the change. GitHub creates a pull request for you.

## Add a new page

1. Click **Add a new page** at the bottom of any wiki page. GitHub opens a new file with the page template filled in.
2. Change `your-page-name.md` to a short name in lowercase letters, numbers and hyphens, such as `nginx-502-after-upgrade.md`.
3. Fill in the template, then propose the new file.

An automatic check runs on your pull request and tells you if something in the page cannot be used, such as a broken link or a missing field. Fix what it says and the check runs again.

## The page format

A page is a short block of settings at the top, then the text:

```
---
title: A short, clear title
category: fixes
summary: One sentence that says what this page helps with.
date: 2026-10-31
author: Your name or nickname (optional)
tested_on: Ubuntu 24.04, for example (optional)
tags: disk, cleanup
---

## The problem

What you saw, with the exact error message.

## What worked

The commands, in a code block.
```

The settings:

| Setting | Required | Notes |
|---|---|---|
| `title` | yes | Up to 80 characters |
| `category` | yes | `fixes`, `tips`, `experiences` or `ideas` |
| `summary` | yes | One sentence, up to 200 characters |
| `date` | yes | The day you wrote it, like `2026-10-31` |
| `author` | no | A name or nickname. Leave it out to stay anonymous on the page |
| `tested_on` | no | The system you tried it on |
| `tags` | no | Up to 6, lowercase, separated by commas |

## What you can write

- Headings with `##` and `###` (the title is already the main heading)
- Paragraphs, **bold** with `**bold**`, *italic* with `*italic*`, and `inline code` with backticks
- Code blocks between lines of three backticks, with the language after the first three, such as `bash`
- Bullet lists, numbered lists (one level only), simple tables and quotes starting with `>`
- Links: `[text](https://example.org)` for the web, `[[page-name]]` for another wiki page, and `[text](site:docs/sysadmin/rsync.html)` for a page on the main TechCommune site

Not supported: pictures, raw HTML (it is shown as text), and links that are not HTTPS.

## What happens next

The site owner reads your pull request, may ask for changes or edit it, and then either merges it or closes it with a reason. Merged pages are published to the wiki. Because the repository is public, your GitHub name and the commit history are public too.
