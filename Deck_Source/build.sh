#!/usr/bin/env bash
# Rebuilds a deck's PDF and PPTX from its slide sources.
# Usage: Deck_Source/build.sh [output_dir] [deck_dir] [name]
#   defaults: the repo root, this folder (the Phase 1 deck), MeltWise_Presentation
#   Phase 2:  Deck_Source/build.sh Phase2_Submission Deck_Source/phase2 MeltWise_Phase2_Presentation
# Needs python3, node, Chrome or Chromium (set CHROME=/path/to/chrome if it isn't found),
# and internet access for the first `npm install` and for the Google Fonts the slides use.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
OUT="$(cd "${1:-$HERE/..}" && pwd)"
DECK="$(cd "${2:-$HERE}" && pwd)"
NAME="${3:-MeltWise_Presentation}"
BUILD="$DECK/build"

find_chrome() {
  local candidate
  for candidate in "${CHROME:-}" \
      "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" \
      "$(command -v google-chrome || true)" \
      "$(command -v chromium || true)" \
      "$(command -v chromium-browser || true)" \
      "$HOME"/.cache/ms-playwright/chromium-*/chrome-linux*/chrome; do
    if [ -n "$candidate" ] && [ -x "$candidate" ]; then
      echo "$candidate"
      return
    fi
  done
  echo "Chrome or Chromium not found. Install one, or set CHROME=/path/to/chrome." >&2
  return 1
}

CHROME_BIN="$(find_chrome)"
NO_SANDBOX=""
if [ "$(id -u)" -eq 0 ]; then NO_SANDBOX="--no-sandbox"; fi  # Chrome won't start as root with its sandbox on

uri() { python3 -c 'import pathlib, sys; print(pathlib.Path(sys.argv[1]).as_uri())' "$1"; }

# Headless Chrome can keep running after it has written its output, so each run gets its
# own profile and is stopped once the output file stops growing (or after 30 seconds).
render() {  # render <output file> <chrome args...>
  local output="$1" profile pid size=-1 now
  shift
  profile="$(mktemp -d)"
  rm -f "$output"
  "$CHROME_BIN" --headless=new --disable-gpu --hide-scrollbars --no-first-run --no-default-browser-check \
    --disable-extensions $NO_SANDBOX --user-data-dir="$profile" --virtual-time-budget=10000 "$@" >/dev/null 2>&1 &
  pid=$!
  for _ in $(seq 60); do
    sleep 0.5
    [ -s "$output" ] || continue
    now=$(( $(wc -c < "$output") ))
    [ "$now" = "$size" ] && break
    size=$now
  done
  kill "$pid" 2>/dev/null || true
  wait "$pid" 2>/dev/null || true
  pkill -f -- "--user-data-dir=$profile" 2>/dev/null || true
  rm -rf "$profile" 2>/dev/null || true
  [ -s "$output" ] || { echo "Chrome did not write $output" >&2; exit 1; }
}

cd "$HERE"
[ -d node_modules/pptxgenjs ] || npm install --no-audit --no-fund
DECK_DIR="$DECK" python3 build_deck.py

slides="$(python3 -c 'import json, sys; print(len(json.load(open(sys.argv[1]))["order"]))' "$DECK/deck.json")"
for i in $(seq 1 "$slides"); do
  n="$(printf %02d "$i")"
  render "$BUILD/slide_$n.png" --window-size=1920,1080 --screenshot="$BUILD/slide_$n.png" "$(uri "$BUILD/slide_$n.html")"
done
contact_h=$(( (slides + 3) / 4 * 269 + 8 ))   # 4 thumbnails a row
render "$BUILD/contact.png" --window-size=1920,$contact_h --screenshot="$BUILD/contact.png" "$(uri "$BUILD/contact.html")"
render "$BUILD/deck.pdf" --no-pdf-header-footer --print-to-pdf="$BUILD/deck.pdf" "$(uri "$BUILD/deck_print.html")"

node make_pptx.js "$OUT/$NAME.pptx" "$BUILD"
cp "$BUILD/deck.pdf" "$OUT/$NAME.pdf"
echo "Wrote $NAME.pdf and $NAME.pptx to $OUT"
echo "All slides at a glance: $BUILD/contact.png"
