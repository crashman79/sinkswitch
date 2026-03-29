#!/bin/sh
# Build the SinkSwitch binary (optional: wipe PyInstaller output first) and run dist/sinkswitch.
#
#   ./build-and-run.sh                 # incremental build, then run
#   ./build-and-run.sh --clean         # rm build/ + dist/, then build, then run
#   ./build-and-run.sh -c              # same
#   ./build-and-run.sh -- --minimized  # build (no clean), run with args after --
#
# Combine clean + app flags:
#   ./build-and-run.sh -c -- --minimized

set -e
cd "$(dirname "$0")"

clean=0
while [ $# -gt 0 ]; do
	case "$1" in
		--clean|-c) clean=1; shift ;;
		--) shift; break ;;
		*) break ;;
	esac
done

if [ "$clean" -eq 1 ]; then
	echo "Removing build/ and dist/ ..."
	rm -rf build dist
fi

./build.sh
exec ./dist/sinkswitch "$@"
