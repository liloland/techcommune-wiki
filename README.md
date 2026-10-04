# TechCommune wiki (maintainer notes)

A community wiki for techcommune.org. Pages are Markdown files in `content/`; a small standard-library Python builder turns them into static HTML. Nothing visitor-written is ever served until the maintainer has merged it.

## Layout

| Path | What |
|---|---|
| `content/*.md` | The pages (one file each; the file name is the page address) |
| `wiki.toml` | Wiki title, categories, repository address, licence |
| `tools/build.py` | The builder (`--check` validates only; `--release` refuses placeholder settings) |
| `tools/mdlite.py` | The Markdown renderer: escapes everything, allows only safe links, no images, no raw HTML |
| `templates/wiki.css` | Extra styles (kept in a file because the site's Content-Security-Policy forbids inline styles) |
| `tests/` | Unit tests (`python3 -m unittest discover -s tests`) |
| `.github/` | Pull request template, issue templates and the automatic page check |

## Everyday use

```bash
python3 tools/lint.py                                   # check every page (what the pull-request check runs)
python3 -m unittest discover -s tests                   # run the tests
python3 tools/build.py --site ~/modern --out build      # build into ./build
python3 tools/build.py --site ~/modern --out build --release   # same, but refuse placeholder settings
```

`--site` points at the main site folder: its `style.css`, `search.js`, `search.css` and icons are copied into the build, so the wiki folder is self-contained.

## Reviewing a pull request

1. Read the diff, not just the rendered page. Look for secrets, real names, copied text, links that go somewhere odd and commands that delete data without a warning.
2. Check the page builds: `python3 tools/lint.py` (the automatic check does this too).
3. Merge or close with a reason. Edit the page yourself if it is nearly right.

## Publishing (after a merge)

1. Mount the server's web folder read-write with sshfs (without `default_permissions`), and `git pull` on `main`.
2. Dry run: `tools/deploy.sh` runs the tests and the page check, builds with `--release`, and lists what would change on the server.
3. Publish: `tools/deploy.sh --go` copies only the changed files into `~/server-www/wiki/public/`, verifies the copy byte for byte and checks the live pages.

The script refuses to run when the repository has uncommitted changes, is not on `main`, or is out of step with GitHub, so what is published is always exactly what is public. The one-time server setup (folder, nginx location) is in `NGINX-wiki.txt`, kept with the other server instructions.

## Before the first publish

- Set `repo_url` in `wiki.toml` to the real repository (the build refuses to publish with the placeholder).
- Turn on branch protection for `main` and require the "Check pages" check.
- Set up the nginx location (see the planning notes) and include both header snippets.
- Do not use `pull_request_target` in any workflow: it would hand secrets to code from forks.
