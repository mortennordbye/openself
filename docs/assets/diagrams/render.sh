#!/bin/sh
# Renders every diagram here (except _*.d2, shared parts) to SVG with D2 and to PNG with rsvg-convert,
# both in containers so the output is the same everywhere. Used by `make diagram` and CI.
set -eu
cd "$(dirname "$0")"
for f in [!_]*.d2; do
  name=${f%.d2}
  docker run --rm -u "$(id -u):$(id -g)" -v "$PWD:/work" terrastruct/d2:v0.7.1 --layout elk \
    --elk-nodeNodeBetweenLayers=35 --elk-padding="[top=25,left=25,bottom=25,right=25]" \
    --scale 1 --pad 40 "/work/$f" "/work/$name.svg"
  # rsvg-convert skips data URIs written as "svg+xml; charset=utf-8;base64", which is how D2
  # inlines Iconify icons, so they are rewritten to the plain form first.
  sed 's/svg+xml; charset=utf-8;base64/svg+xml;base64/g' "$name.svg" > "$name.svg.tmp" && mv "$name.svg.tmp" "$name.svg"
done
docker run --rm -e OWNER="$(id -u):$(id -g)" -v "$PWD:/work" -w /work alpine:3.22 sh -c \
  'apk add -q rsvg-convert font-dejavu >/dev/null && for s in [!_]*.svg; do rsvg-convert -z 2 "$s" -o "${s%.svg}.png"; done && chown "$OWNER" *.png'
