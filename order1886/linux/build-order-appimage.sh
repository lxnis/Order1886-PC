#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-or-later
# Builds TheOrder1886-x86_64.AppImage: the Tkinter launcher (PyInstaller) + the current bb-probe
# build (branch order1886) + bbport's preparation scripts + order_patches.py.
# NO game files, NO prepared image (boot-linked.bin, eboot.elf, out/): the launcher prepares the
# game image on the player's machine from their own dump (~/.local/share/order1886/).
#
#   bash build-order-appimage.sh        (after building bbport with order_patch.py)
set -euo pipefail

PROJECT=${PROJECT:-$HOME/Project}
KERJA=${KERJA:-$HOME/PS41886}
BBPORT=$PROJECT/bbport
WORK=$KERJA/appimage                  # build area (outside the bbport repo)
APPDIR=$WORK/TheOrder1886.AppDir
SHARE=$APPDIR/usr/share/order1886
OUT=$KERJA/TheOrder1886-x86_64.AppImage

say() { printf '\n\033[1;34m==> %s\033[0m\n' "$*"; }
die() { printf '\033[1;31mERROR: %s\033[0m\n' "$*" >&2; exit 1; }

[[ -x $BBPORT/out/bb-probe ]] || die "$BBPORT/out/bb-probe not found (build bbport first)."
[[ -f $KERJA/order_launcher.pyw ]] || die "$KERJA/order_launcher.pyw not found."
[[ -f $KERJA/order_patches.py ]] || die "$KERJA/order_patches.py not found."
python3 -c 'import tkinter' 2>/dev/null || die "Tkinter missing: sudo dnf install python3-tkinter"
mkdir -p "$WORK"

branch=$(git -C "$BBPORT" rev-parse --abbrev-ref HEAD)
commit=$(git -C "$BBPORT" rev-parse HEAD)
say "Port build: branch $branch ($(git -C "$BBPORT" rev-parse --short HEAD))"
[[ $branch == order1886 ]] || echo "  note: bbport is on branch $branch, not order1886."

# ---- 1. launcher (PyInstaller) ---------------------------------------------------------
say "Building the launcher with PyInstaller"
if [[ ! -x $WORK/venv/bin/pyinstaller ]]; then
    python3 -m venv "$WORK/venv"
    "$WORK/venv/bin/pip" install --quiet --upgrade pip pyinstaller
fi
cp "$KERJA/order_launcher.pyw" "$WORK/order-launcher.py"
"$WORK/venv/bin/pyinstaller" --noconfirm --clean --onedir --windowed --name order-launcher \
    --distpath "$WORK/dist" --workpath "$WORK/pyi-build" --specpath "$WORK" \
    "$WORK/order-launcher.py" > "$WORK/pyinstaller.log" 2>&1 \
    || { tail -20 "$WORK/pyinstaller.log"; die "PyInstaller failed (log: $WORK/pyinstaller.log)"; }

# ---- 2. AppDir -------------------------------------------------------------------------
say "Assembling $APPDIR"
rm -rf "$APPDIR"
mkdir -p "$SHARE/bin" "$SHARE/lib" "$SHARE/licenses"
cp -a "$WORK/dist/order-launcher/." "$SHARE/"
install -m755 "$BBPORT/out/bb-probe" "$SHARE/bin/bb-probe"
printf '%s %s\n' "$branch" "$commit" > "$SHARE/bin/bb-probe.commit"
# DLSS: the bridge (MIT) and NVIDIA's DLSS library beside bb-probe (found there at run time).
if [[ -f $BBPORT/out/libbbport_dlss.so ]]; then
    install -m755 "$BBPORT/out/libbbport_dlss.so" "$SHARE/bin/"
    for f in "$BBPORT"/out/libnvidia-ngx-dlss.so.*; do [[ -f $f ]] && install -m755 "$f" "$SHARE/bin/"; done
    [[ -f $BBPORT/out/NVIDIA-DLSS-LICENSE.txt ]] && cp "$BBPORT/out/NVIDIA-DLSS-LICENSE.txt" "$SHARE/licenses/"
    echo "  + DLSS bridge and NVIDIA DLSS library"
else
    echo "  note: no DLSS bridge in $BBPORT/out (build with DLSS_SDK_ROOT): DLSS falls back to FSR 3.1."
fi
cp -a "$BBPORT/scripts" "$SHARE/scripts"
install -m644 "$KERJA/order_patches.py" "$SHARE/order_patches.py"
find "$SHARE" -name __pycache__ -type d -prune -exec rm -rf {} +

# Libraries of the port that are not part of every desktop. The base system, GPU drivers,
# Vulkan loader, X11/Wayland and audio stay the system's own.
SYSTEM='^((libc|libm|libdl|librt|libpthread|libresolv|libutil|libgcc_s|libstdc\+\+|libz|libffi|libcap)\.so|linux-vdso|ld-linux|libvulkan|libGL|libEGL|libgbm|libdrm|libX|libxcb|libxkbcommon|libwayland|libdecor|libasound|libpulse|libpipewire|libjack|libdbus|libudev|libsystemd)'
say "Bundling libraries"
while read -r name _ path _; do
    [[ $path == "not" ]] && die "bb-probe needs $name, which is not installed."
    [[ -z $path || ! -f $path ]] && continue
    if [[ ! $name =~ $SYSTEM ]] && [[ ! -e $SHARE/lib/$name ]]; then
        cp -L "$path" "$SHARE/lib/$name"; echo "  + $name"
    fi
done < <(ldd "$SHARE/bin/bb-probe" | awk '{print $1, $2, $3, $4}')

# Licenses and where the sources are (GPL-2.0-or-later)
for f in "$BBPORT"/LICENSE* "$BBPORT"/COPYING*; do
    [[ -f $f ]] && cp "$f" "$SHARE/licenses/bbport-$(basename "$f")"
done
{
    echo "The Order: 1886 PC port is built from GPL-2.0-or-later sources:"
    echo "  bbport: $(git -C "$BBPORT" remote get-url origin 2>/dev/null || echo '?') commit $commit (branch $branch)"
    echo "  with the changes of order_patch.py applied (included here: run it on that commit to"
    echo "  reproduce the port's source tree), then built with bbport's build.sh."
    echo "The launcher (order-launcher.py), order_patches.py and build-order-appimage.sh are included."
    echo "No game files are included: bring your own dump of a game you own."
} > "$SHARE/licenses/SOURCES.txt"
cp "$KERJA/order_launcher.pyw" "$SHARE/licenses/order-launcher.py"
cp "$KERJA/order_patch.py" "$SHARE/licenses/order_patch.py"
cp "$0" "$SHARE/licenses/build-order-appimage.sh"

# AppRun, desktop entry, icon (generic: no game artwork)
cat > "$APPDIR/AppRun" <<'EOF'
#!/bin/sh
HERE="$(dirname "$(readlink -f "$0")")"
export ORDER1886_APPDIR="$HERE"
exec "$HERE/usr/share/order1886/order-launcher" "$@"
EOF
chmod +x "$APPDIR/AppRun"
cat > "$APPDIR/order1886.desktop" <<'EOF'
[Desktop Entry]
Type=Application
Name=The Order: 1886
Comment=Native PC port (bring your own game dump)
Exec=AppRun
Icon=order1886
Categories=Game;
Terminal=false
StartupWMClass=order-launcher
EOF
python3 - "$APPDIR/order1886.png" <<'EOF'
# 256x256 icon: dark rounded square with "1886" in a simple seven-segment style (no game artwork).
import struct, sys, zlib
N = 256
SEG = {'1': 'bc', '8': 'abcdefg', '6': 'acdefg'}
def lit(x, y):
    for i, ch in enumerate('1886'):
        x0, y0, w, h, t = 28 + i * 52, 88, 40, 80, 8
        lx, ly = x - x0, y - y0
        if not (0 <= lx < w and 0 <= ly < h):
            continue
        s = SEG[ch]
        if 'a' in s and ly < t: return True
        if 'g' in s and abs(ly - h // 2) < t // 2: return True
        if 'd' in s and ly >= h - t: return True
        if 'f' in s and lx < t and ly < h // 2: return True
        if 'b' in s and lx >= w - t and ly < h // 2: return True
        if 'e' in s and lx < t and ly >= h // 2: return True
        if 'c' in s and lx >= w - t and ly >= h // 2: return True
    return False
rows = []
for y in range(N):
    row = bytearray([0])
    for x in range(N):
        r = 40
        cx, cy = min(max(x, r), N - 1 - r), min(max(y, r), N - 1 - r)
        if (x - cx) ** 2 + (y - cy) ** 2 > r * r:
            row += bytes([0, 0, 0, 0]); continue
        row += bytes([214, 170, 96, 255]) if lit(x, y) else bytes([30 + y // 16, 28 + y // 16, 26 + y // 14, 255])
    rows.append(bytes(row))
chunk = lambda t, d: struct.pack('>I', len(d)) + t + d + struct.pack('>I', zlib.crc32(t + d))
png = b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', N, N, 8, 6, 0, 0, 0)) \
      + chunk(b'IDAT', zlib.compress(b''.join(rows), 9)) + chunk(b'IEND', b'')
open(sys.argv[1], 'wb').write(png)
EOF
ln -sf order1886.png "$APPDIR/.DirIcon"

# Safety check: nothing of the game may be inside.
bad=$(find "$APPDIR" \( -iname 'boot-linked.bin' -o -iname 'eboot.bin' -o -iname 'eboot.elf' \
      -o -iname '*.sprx' -o -iname '*.prx' -o -iname 'patches.bin' -o -iname 'content.bin' \
      -o -iname 'param.sfo' -o -iname 'icon0.png' -o -iname '*.rdc' \) -print)
[[ -z $bad ]] || die "game files found in the AppDir:\n$bad"

# ---- 3. pack ---------------------------------------------------------------------------
TOOL=$WORK/appimagetool-x86_64.AppImage
[[ -x $TOOL ]] || { [[ -x $PROJECT/appimage/appimagetool-x86_64.AppImage ]] && cp "$PROJECT/appimage/appimagetool-x86_64.AppImage" "$TOOL"; }
if [[ ! -x $TOOL ]]; then
    say "Downloading appimagetool"
    curl -fL -o "$TOOL" https:/$HOMEithub.com/AppImage/appimagetool/releases/download/continuous/appimagetool-x86_64.AppImage
    chmod +x "$TOOL"
fi
say "Packing $OUT"
rm -f "$OUT"
ARCH=x86_64 APPIMAGE_EXTRACT_AND_RUN=1 "$TOOL" --no-appstream "$APPDIR" "$OUT" > "$WORK/appimagetool.log" 2>&1 \
    || { tail -20 "$WORK/appimagetool.log"; die "appimagetool failed (log: $WORK/appimagetool.log)"; }
say "Done: $OUT ($(du -h "$OUT" | cut -f1))"
echo "  data folder of the AppImage: ~/.local/share/order1886 (game image, saves, cache, log)"
