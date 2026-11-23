#!/usr/bin/env bash
# SPDX-License-Identifier: AGPL-3.0-or-later
set -euo pipefail
cd "$(dirname "$0")/.."
revision=43728af2e639fecb8a7af1cd68c29820a40de973
mkdir -p build-native/{runtime,notices}
if [[ ! -d build-native/chiaki/.git ]]; then
    git init -q build-native/chiaki
fi
git -C build-native/chiaki fetch --depth 1 https://github.com/streetpea/chiaki-ng.git "$revision"
git -C build-native/chiaki checkout --detach FETCH_HEAD
git -C build-native/chiaki submodule update --init --depth 1 \
    third-party/nanopb third-party/gf-complete third-party/jerasure third-party/curl

cmake -S native -B build-native/cmake -G Ninja -DCMAKE_BUILD_TYPE=Release \
    -DCHIAKI_SOURCE="$(cygpath -am build-native/chiaki)"
cmake --build build-native/cmake --target nexcap-remote

copy_runtime() {
    local binary=$1 dll package
    while IFS= read -r dll; do
        if [[ -f "/mingw64/bin/$dll" && ! -f "build-native/runtime/$dll" ]]; then
            cp "/mingw64/bin/$dll" build-native/runtime/
            package=$(pacman -Qoq "/mingw64/bin/$dll")
            if [[ -d "/mingw64/share/licenses/$package" ]]; then
                cp -R "/mingw64/share/licenses/$package" build-native/notices/
            elif [[ -d "/mingw64/share/licenses/${package#mingw-w64-x86_64-}" ]]; then
                cp -R "/mingw64/share/licenses/${package#mingw-w64-x86_64-}" build-native/notices/
            fi
            pacman -Q "$package" >> build-native/notices/msys2-packages.txt
            copy_runtime "build-native/runtime/$dll"
        fi
    done < <(objdump -p "$binary" | sed -n 's/^[[:space:]]*DLL Name: //p' | tr -d '\r')
}
: > build-native/notices/msys2-packages.txt
cp build-native/cmake/nexcap-remote.exe build-native/runtime/
copy_runtime build-native/runtime/nexcap-remote.exe
cp build-native/chiaki/COPYING build-native/notices/COPYING-chiaki-ng
cp -R build-native/chiaki/LICENSES build-native/notices/chiaki-ng-LICENSES
for dependency in nanopb gf-complete jerasure curl; do
    mkdir -p "build-native/notices/$dependency"
    find "build-native/chiaki/third-party/$dependency" -maxdepth 1 -type f \
        \( -iname 'COPYING*' -o -iname 'LICENSE*' -o -iname 'COPYRIGHT*' \) \
        -exec cp {} "build-native/notices/$dependency/" \;
done
echo "https://github.com/streetpea/chiaki-ng/tree/$revision" > build-native/notices/chiaki-ng-source.txt

# Verify it runs with the packaged DLLs and standard Windows paths alone.
PATH='/c/Windows/System32:/c/Windows' ./build-native/runtime/nexcap-remote.exe --version
