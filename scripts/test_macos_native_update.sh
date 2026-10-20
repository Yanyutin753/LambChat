#!/usr/bin/env bash
set -euo pipefail
verifier="$1"
artifact="$2"
version="$3"
suffix="$4"
expected_app="$5"
root=$(mktemp -d)
trap 'rm -rf "$root"' EXIT
for baseline in v2.15.2 v2.15.3-dev.1; do
  download="$root/$baseline"
  mkdir -p "$download"
  name="LambChat-${baseline}-${suffix}.app.tar.gz"
  gh release download "$baseline" --repo "$GITHUB_REPOSITORY" --pattern "$name" --pattern "$name.sig" --dir "$download"
  core="${baseline#v}"
  "$verifier" "$download/$name" "$download/$name.sig" "${core%%-dev.*}"
  tar -xzf "$download/$name" -C "$download"
  app="$download/LambChat.app"
  test -f "$app/Contents/MacOS/lambchat"
  ! cmp -s "$app/Contents/MacOS/lambchat" "$expected_app/Contents/MacOS/lambchat"
  touch "$app/Contents/old-updater-marker"
  echo keep-me > "$download/user-data.txt"
  "$verifier" "$artifact" "$artifact.sig" "$version" "${baseline#v}" "$app/Contents/MacOS/lambchat"
  test ! -e "$app/Contents/old-updater-marker"
  test "$(cat "$download/user-data.txt")" = keep-me
  cmp "$app/Contents/MacOS/lambchat" "$expected_app/Contents/MacOS/lambchat"
  codesign --verify --deep --strict "$app"
  test "$("$app/Contents/MacOS/lambchat-daemon" version | tail -1)" = "${version%%-dev.*}"
  echo "PASS: native updater $baseline -> $version, App replacement matches, data preserved, codesign and daemon pass"
done
