#!/bin/sh
# Build and install SinkSwitch Flatpak (no standalone binary build path).
#
#   ./build.sh                 # build + install Flatpak
#   ./build.sh --clean         # remove Flatpak build dir first
#   ./build.sh -c              # same
#
# Override default build directory:
#   SINKSWITCH_FLATPAK_BUILD_DIR=/path/to/build ./build.sh
#
# Optional flatpak-builder flags (e.g. --disable-rofiles-fuse):
#   SINKSWITCH_FLATPAK_BUILDER_OPTS=--disable-rofiles-fuse ./build.sh

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
		*) echo "Unknown option: $1" >&2; exit 2 ;;
	esac
done

if [ ! -f "$MANIFEST" ]; then
	echo "Missing manifest: $MANIFEST" >&2
	exit 1
fi

if ! command -v flatpak >/dev/null 2>&1 || ! command -v flatpak-builder >/dev/null 2>&1; then
	echo "Install flatpak and flatpak-builder first (see flatpak/README.md)." >&2
	exit 1
fi

if [ "$clean" -eq 1 ]; then
	echo "Removing Flatpak build dir: $BUILD_DIR"
	rm -rf "$BUILD_DIR"
fi

flatpak remote-add --user --if-not-exists flathub https://flathub.org/repo/flathub.flatpakrepo
flatpak install --user -y --noninteractive flathub org.freedesktop.Platform//24.08 org.freedesktop.Sdk//24.08

echo "Building and installing (user) from $MANIFEST -> $BUILD_DIR"
# shellcheck disable=SC2086
flatpak-builder --user --install --force-clean $FB_OPTS "$BUILD_DIR" "$MANIFEST"

echo "Build/install complete. Run with: flatpak run io.github.crashman79.sinkswitch"
