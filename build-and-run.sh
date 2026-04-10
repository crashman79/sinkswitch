#!/bin/sh
# Build the SinkSwitch Flatpak from this repo and run it (user install).
# Requires: flatpak, flatpak-builder; Freedesktop 24.08 Platform/SDK from Flathub.
#
#   ./build-and-run.sh                      # build + install + run
#   ./build-and-run.sh --clean              # rm flatpak build dir, then build + run
#   ./build-and-run.sh -c                   # same
#   ./build-and-run.sh -- --minimized       # pass args to the app (after --)
#   ./build-and-run.sh -c -- --minimized
#
# Override build directory (default: ../sinkswitch-flatpak-build next to repo):
#   SINKSWITCH_FLATPAK_BUILD_DIR=/path/to/build ./build-and-run.sh
#
# If flatpak-builder fails with rofiles-fuse errors:
#   SINKSWITCH_FLATPAK_BUILDER_OPTS=--disable-rofiles-fuse ./build-and-run.sh

set -e
cd "$(dirname "$0")"
ROOT="$(pwd)"
MANIFEST="$ROOT/flatpak/io.github.crashman79.sinkswitch.yml"
BUILD_DIR="${SINKSWITCH_FLATPAK_BUILD_DIR:-$ROOT/../sinkswitch-flatpak-build}"
FB_OPTS="${SINKSWITCH_FLATPAK_BUILDER_OPTS:-}"

clean=0
while [ $# -gt 0 ]; do
	case "$1" in
		--clean|-c) clean=1; shift ;;
		--) shift; break ;;
		*) break ;;
	esac
done

if [ ! -f "$MANIFEST" ]; then
	echo "Missing manifest: $MANIFEST" >&2
	exit 1
fi

if ! command -v flatpak >/dev/null 2>&1 || ! command -v flatpak-builder >/dev/null 2>&1; then
	echo "Install flatpak and flatpak-builder (see flatpak/README.md)." >&2
	exit 1
fi

if [ "$clean" -eq 1 ]; then
	echo "Removing Flatpak build dir: $BUILD_DIR"
	rm -rf "$BUILD_DIR"
fi

flatpak remote-add --user --if-not-exists flathub https://flathub.org/repo/flathub.flatpakrepo

echo "Installing org.freedesktop.Platform/Sdk 24.08 if needed..."
flatpak install --user -y --noninteractive flathub org.freedesktop.Platform//24.08 org.freedesktop.Sdk//24.08

echo "Building and installing (user) from $MANIFEST → $BUILD_DIR"
# shellcheck disable=SC2086
flatpak-builder --user --install --force-clean $FB_OPTS "$BUILD_DIR" "$MANIFEST"

echo "Running io.github.crashman79.sinkswitch ..."
exec flatpak run io.github.crashman79.sinkswitch "$@"
