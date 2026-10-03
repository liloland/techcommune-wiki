#!/usr/bin/env bash
# Publish the wiki: check, build, and copy to the web server folder (mounted over sshfs).
#   tools/deploy.sh          dry run: checks everything and shows what WOULD change
#   tools/deploy.sh --go     do it, then verify the copy
# Settings (environment): SITE=main site folder (default ~/modern), DEST=target folder (default ~/server-www/wiki/public),
#                         LIVE_URL=address to test afterwards (default https://techcommune.org/wiki/, set empty to skip)
set -euo pipefail
export PYTHONDONTWRITEBYTECODE=1
cd "$(dirname "$0")/.."
SITE="${SITE:-$HOME/modern}"
DEST="${DEST:-$HOME/server-www/wiki/public}"
LIVE_URL="${LIVE_URL-https://techcommune.org/wiki/}"
GO=0; [ "${1:-}" = "--go" ] && GO=1
say() { printf '\n== %s\n' "$*"; }
die() { printf 'STOP: %s\n' "$*" >&2; exit 1; }

say "1. Is the repository clean and on main?"
[ -z "$(git status --porcelain)" ] || die "uncommitted changes (commit or stash them first, the build must match a commit)"
[ "$(git rev-parse --abbrev-ref HEAD)" = "main" ] || die "not on the main branch"
if git fetch --quiet origin 2>/dev/null; then
    behind=$(git rev-list --count HEAD..origin/main)
    ahead=$(git rev-list --count origin/main..HEAD)
    [ "$behind" = 0 ] || die "main is $behind commit(s) behind GitHub: run  git pull  first"
    [ "$ahead" = 0 ] || die "$ahead local commit(s) are not on GitHub yet: push them first, so what you publish is what is public"
    echo "main matches GitHub ($(git rev-parse --short HEAD))"
else
    echo "warning: could not reach GitHub, skipping the up-to-date check"
fi

say "2. Tests and page check"
python3 -m unittest discover -s tests 2>&1 | tail -3
python3 tools/lint.py --site "$SITE"

say "3. Build (release mode refuses placeholder settings)"
OUT="$(mktemp -d)"; trap 'rm -rf "$OUT"' EXIT
python3 tools/build.py --site "$SITE" --out "$OUT/build" --release

say "4. Target folder"
[ -d "$DEST" ] || die "$DEST does not exist: mount sshfs read-write and create /var/www/wiki/public on the server first (see NGINX-wiki.txt)"
[ -w "$DEST" ] || die "$DEST is not writable: is sshfs mounted read-write (and without default_permissions)?"
echo "$DEST"

say "5. What would change ($([ $GO = 1 ] && echo 'applying now' || echo 'dry run'))"
RS=(rsync -rc --delete --no-perms --no-owner --no-group --omit-dir-times --itemize-changes)
changes=$("${RS[@]}" -n "$OUT/build/" "$DEST/" | grep -v '^\.' || true)
if [ -z "$changes" ]; then echo "nothing to do: the server copy is already identical"; else echo "$changes"; fi
if [ $GO = 0 ]; then echo; echo "Dry run only. Run again with --go to publish."; exit 0; fi
[ -z "$changes" ] || "${RS[@]}" "$OUT/build/" "$DEST/" > /dev/null

say "6. Verify the copy byte for byte"
diff -r "$OUT/build" "$DEST" > /dev/null && echo "identical" || die "the server copy differs from the build"

if [ -n "$LIVE_URL" ]; then
    say "7. Live check"
    for p in "" how-to-contribute.html search.html style.css; do
        printf '%-28s %s\n' "${LIVE_URL}${p}" "$(curl -sS -m10 -o /dev/null -w '%{http_code}' "${LIVE_URL}${p}" || echo fail)"
    done
fi
say "Done"
