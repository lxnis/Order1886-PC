#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Builds The Order: 1886 Windows portable folder + ZIP from the finished build of
G:\\Project\\order-win (branch order1886-win, patched by order_windows_patch.py, built with build.sh).

    py -3 G:\\PS41886\\make_order_portable.py [--version v0.1]

Runs with python.org's Python (it has Tkinter for PyInstaller); uses MSYS2's llvm-objdump to find
the DLLs sacredfire.exe needs and pacman to name their packages and licenses (THIRD-PARTY.txt),
the way GetLostIn's packaging/windows/make_portable.py does for CTR.

Output: G:\\PS41886\\dist\\Order1886-PC-portable\\ and Order1886-PC-portable-windows.zip (+ .sha256).
Nothing from your own machine goes in: no game files, no prepared image (boot*.bin, eboot.elf),
no saves, no shader cache, no logs, no settings.
"""
import argparse
import hashlib
import os
from pathlib import Path
import re
import shutil
import struct
import subprocess
import sys
import urllib.request
import zipfile
import zlib

HERE = Path(__file__).resolve().parent
ROOT = Path(os.environ.get('ORDER_PORT', r'G:\Project\order-win'))
LAUNCHER_SRC = HERE / 'order_launcher_win.pyw'
PATCH_SRC = HERE / 'order_windows_patch.py'
SOURCES = [PATCH_SRC, HERE / 'order_patch.py', HERE / 'order_patches.py', HERE / 'order_run.py']
MSYS2 = Path(os.environ.get('MSYS2_ROOT', r'C:\msys64'))
CLANG_BIN = MSYS2 / 'clang64' / 'bin'
NAME = 'Order1886-PC-portable'
LAUNCHER = 'Order1886-Launcher'
PYTHON_VERSION = '3.14.8'   # as GetLostIn's packager (pinned by SHA-256)
PYTHON_URL = f'https://www.python.org/ftp/python/{PYTHON_VERSION}/python-{PYTHON_VERSION}-embed-amd64.zip'
PYTHON_SHA256 = 'a93abe456ab01bd96d7a085b3cdb6566b3063f4241360d114142fbdb07f0a310'
SYSTEM_DLLS = {'kernel32', 'user32', 'gdi32', 'advapi32', 'shell32', 'ole32', 'oleaut32', 'ws2_32',
               'msvcrt', 'ntdll', 'bcrypt', 'bcryptprimitives', 'crypt32', 'secur32', 'winmm',
               'imm32', 'setupapi', 'version', 'shlwapi', 'comdlg32', 'comctl32', 'rpcrt4',
               'dwmapi', 'd3d11', 'dxgi', 'd3d9', 'd3d12', 'dxva2', 'mf', 'mfplat', 'mfuuid',
               'mfreadwrite', 'uxtheme', 'cfgmgr32', 'hid', 'opengl32', 'vulkan-1', 'iphlpapi',
               'mswsock', 'dnsapi', 'ncrypt', 'usp10', 'shcore', 'cabinet', 'wldap32', 'normaliz',
               'avrt', 'msimg32', 'propsys', 'windowscodecs', 'mmdevapi', 'powrprof', 'userenv',
               'psapi', 'netapi32', 'wsock32', 'd3dcompiler_47', 'gdiplus', 'd2d1', 'dwrite',
               'dinput8', 'xinput1_4', 'ucrtbase', 'vcruntime140', 'msvcp140', 'winspool',
               'cryptbase', 'sspicli', 'wintrust', 'rtworkq', 'ksuser', 'wevtapi', 'ntmarta'}
FORBIDDEN = re.compile(r'(^|[\\/])(eboot\.bin|eboot\.elf|boot[-\w]*\.bin|content\.bin|patches\.bin|'
                       r'param\.sfo|icon0\.png|.*\.sprx|.*\.prx|.*_play\.log|prepare\.log|patch\.log|launcher\.json|bbport\.ini)$'
                       r'|(^|[\\/])(user|savedata)[\\/]',   # saves and the shader cache (28 Oct)
                       re.IGNORECASE)
# The player's own data in an existing portable folder: never moved. The package is assembled and
# zipped in <dist>/launcher-build/package, then only the package files of the play folder are replaced (28 Oct:
# rebuilding had deleted the saves; a power cut while they were set aside stranded them).
KEEP = ('user', 'out', 'launcher.json', 'bbport.ini', 'order_play.log')

README = r'''The Order: 1886 - native PC port for Windows (portable)
=======================================================
A native Windows port of The Order: 1886 (PS4, CUSA00035, update 01.02): the game's own x86-64
code runs on your CPU and its graphics go through Vulkan. Built on bbport and the Windows layer
of SacredFire / GetLostIn's CTR-NitroFueled-PC. Experimental.

REQUIREMENTS (not included)
---------------------------
1. Your own decrypted dump of The Order: 1886 CUSA00035 (US, v01.02): the folder with eboot.bin,
   sce_module\ and sce_sys\param.sfo. No game files come with this package.
2. 64-bit Windows 10 (1903+) or 11, a Vulkan 1.3 GPU with current drivers, 16 GB RAM.
Nothing has to be installed: Python is included (python\).

START
-----
1. Unpack this folder somewhere writable (not Program Files), e.g. C:\Games\Order1886-PC-portable.
2. Run Order1886-Launcher.exe, press Browse... and select your CUSA00035 folder.
3. Press Play. The first start prepares the game image (out\, a few minutes) and compiles
   shaders while you play (some stutter); later starts are faster.
Settings: 30/60 FPS, 16:9 full screen (also 2K/4K), FSR 3.1 in place of the game's TAA, MSAA,
anisotropic filtering, present mode, fullscreen or windowed, Fast/Safe, FPS counter.
Log / Saves / Cache / Prepare: the last run's log, the save folder, clear the shader cache,
prepare the game image again on the next Play.

FILES IT CREATES (beside the launcher)
--------------------------------------
out\             the prepared game image (made from YOUR dump; do not share it)
user\            saves and the shader cache
bbport.ini       the port's settings; launcher.json the launcher's
order_play.log   everything the last run printed (attach it to a bug report)

KNOWN ISSUES
------------
- 60 FPS: the button-mash QTEs of chapters 6 and 9 need 30 FPS.
- 2K/4K only together with 16:9.
- Faces can look too dark in dark rooms; stutter on first loads (shader compiles).
- No online features (the game sees a signed-out console).

LICENSE
-------
GPL-2.0-or-later (LICENSE). Libraries in bin\ and python\: THIRD-PARTY.txt. Where the source of
this build is: SOURCE.txt and source\. Not affiliated with Sony Interactive Entertainment or
Ready at Dawn. You need your own copy of the game.
'''


def imports(path):
    out = subprocess.run([str(CLANG_BIN / 'llvm-objdump.exe'), '-p', str(path)], capture_output=True,
                         text=True, errors='replace').stdout
    return {m.group(1).lower() for m in re.finditer(r'DLL Name:\s*(\S+)', out)}


def closure(binaries):
    found, queue = {}, list(binaries)
    while queue:
        for dll in imports(queue.pop()):
            stem = dll[:-4] if dll.endswith('.dll') else dll
            if dll in found or stem in SYSTEM_DLLS or dll.startswith(('api-ms-', 'ext-ms-')):
                continue
            path = CLANG_BIN / dll
            if not path.is_file():
                sys.exit(f'{dll} is needed but is not in {CLANG_BIN}')
            found[dll] = path
            queue.append(path)
    return found


def pacman(*args):
    return subprocess.run([str(MSYS2 / 'usr' / 'bin' / 'pacman.exe'), *args], capture_output=True,
                          text=True, errors='replace').stdout


def third_party(dlls, python):
    packages = {}
    for dll in sorted(dlls):
        m = re.search(r'is owned by (\S+) (\S+)', pacman('-Qo', f'/clang64/bin/{dll}').strip())
        packages.setdefault(m.group(1) if m else '(unknown)',
                            {'version': m.group(2) if m else '', 'dlls': []})['dlls'].append(dll)
    lines = ['THIRD-PARTY SOFTWARE', '=' * 60,
             'The port is GPL-2.0-or-later (LICENSE). The libraries in bin\\ are MSYS2 CLANG64',
             'packages, copied unchanged; each keeps its own license, and the package page lists the',
             'source and the build recipe (https://packages.msys2.org/).', '']
    for package in sorted(packages):
        info = pacman('-Qi', package)
        field = lambda key: next((l.split(':', 1)[1].strip() for l in info.splitlines() if l.startswith(key)), '?')
        lines += [f'{package} {packages[package]["version"]}', f'  license: {field("Licenses")}',
                  f'  home:    {field("URL")}', f'  source:  https://packages.msys2.org/packages/{package}',
                  f'  files:   {", ".join(packages[package]["dlls"])}', '']
    lines += [f'{python}, in python\\', '  license: PSF-2.0 (python\\LICENSE.txt)',
              '  home:    https://www.python.org/', '',
              'Order1886-Launcher.exe: the launcher (source\\order_launcher_win.pyw), packed with PyInstaller',
              '  (GPL-2.0-or-later with its bootloader exception) and Python\'s Tkinter (Tcl/Tk: BSD-style).', '',
              'Order1886.exe includes AMD FidelityFX FSR (MIT), Dear ImGui (MIT) and shadPS4\'s video',
              'core (GPL-2.0-or-later); out\\aerolib.inl is shadPS4\'s symbol list (GPL-2.0-or-later).', '',
              'The game files are not included and are not covered by any of these licenses.', '']
    return '\r\n'.join(lines)


def bundle_python(folder, cache):
    archive = cache / Path(PYTHON_URL).name
    if not archive.is_file():
        cache.mkdir(parents=True, exist_ok=True)
        print(f'Downloading {PYTHON_URL}')
        with urllib.request.urlopen(PYTHON_URL, timeout=120) as response:
            archive.write_bytes(response.read())
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    if digest != PYTHON_SHA256:
        archive.unlink()
        sys.exit(f'{archive.name}: SHA-256 {digest}, expected {PYTHON_SHA256}')
    target = folder / 'python'
    with zipfile.ZipFile(archive) as z:
        z.extractall(target)
    pth = next(target.glob('python3*._pth'))
    zipped = next(target.glob('python3*.zip')).name
    pth.write_bytes(f'{zipped}\r\n.\r\n..\\scripts\r\n..\\tools\r\n'.encode())
    return f'Python {PYTHON_VERSION} (python.org embeddable package)'


def icon(path):
    """A 256x256 ICO (PNG inside): dark rounded square, red play triangle. No game artwork."""
    n, rows = 256, []
    for y in range(n):
        row = bytearray([0])
        for x in range(n):
            r = 40
            cx, cy = min(max(x, r), n - 1 - r), min(max(y, r), n - 1 - r)
            if (x - cx) ** 2 + (y - cy) ** 2 > r * r:
                row += bytes(4)
                continue
            tri = 88 <= x <= 188 and abs(y - 128) <= (x - 88) * 0.58 and abs(y - 128) <= 58
            row += bytes([200, 150, 90, 255]) if tri else bytes([30 + y // 16, 31 + y // 16, 36 + y // 14, 255])
        rows.append(bytes(row))
    chunk = lambda t, d: struct.pack('>I', len(d)) + t + d + struct.pack('>I', zlib.crc32(t + d))
    png = (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', n, n, 8, 6, 0, 0, 0))
           + chunk(b'IDAT', zlib.compress(b''.join(rows), 9)) + chunk(b'IEND', b''))
    path.write_bytes(struct.pack('<HHH', 0, 1, 1) + struct.pack('<BBBBHHII', 0, 0, 0, 0, 1, 32, len(png), 22) + png)


def build_launcher(work):
    """Order1886-Launcher.exe: PyInstaller one-file, windowed, with Tkinter (python.org's Python)."""
    try:
        import tkinter  # noqa: F401
    except ImportError:
        sys.exit('This Python has no Tkinter: run the packager with python.org\'s Python (py -3).')
    if subprocess.run([sys.executable, '-m', 'PyInstaller', '--version'], capture_output=True).returncode:
        print('Installing PyInstaller')
        subprocess.run([sys.executable, '-m', 'pip', 'install', '--user', '--upgrade', 'pyinstaller'], check=True)
    work.mkdir(parents=True, exist_ok=True)
    ico = work / 'order.ico'
    icon(ico)
    cmd = [sys.executable, '-m', 'PyInstaller', '--noconfirm', '--clean', '--onefile', '--windowed',
           '--name', LAUNCHER, '--icon', str(ico), '--distpath', str(work / 'dist'),
           '--workpath', str(work / 'build'), '--specpath', str(work), str(LAUNCHER_SRC)]
    with open(work / 'pyinstaller.log', 'w', encoding='utf-8', errors='replace') as log:
        if subprocess.run(cmd, stdout=log, stderr=subprocess.STDOUT).returncode:
            sys.exit(f'PyInstaller failed: see {work / "pyinstaller.log"}')
    return work / 'dist' / f'{LAUNCHER}.exe'


def write_text(path, text):
    path.write_bytes(text.replace('\r\n', '\n').replace('\n', '\r\n').encode('utf-8'))


def git(*args):
    return subprocess.run(['git', '-C', str(ROOT), *args], capture_output=True, text=True).stdout.strip()


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--version', default='v0.1')
    p.add_argument('--dist', type=Path, default=HERE / 'dist')
    a = p.parse_args()

    exe, caps = ROOT / 'out' / 'sacredfire.exe', ROOT / 'out' / 'bb-gpu-capabilities.exe'
    for f in (exe, caps, LAUNCHER_SRC, *SOURCES):
        if not f.is_file():
            sys.exit(f'{f} not found (build the port with build.sh first)')
    for f in ('src/runtime_kernel.c', 'gpu/shadps4/video_core/renderer_vulkan/vk_rasterizer.cpp'):
        if 'bbport-order' not in (ROOT / f).read_text(encoding='utf-8', errors='replace'):
            sys.exit(f'{f} has no The Order fixes: run order_windows_patch.py and build.sh first')

    print('== Launcher (PyInstaller)')
    launcher = build_launcher(a.dist / 'launcher-build')

    # The package is assembled and zipped in a separate folder; the play folder is then updated in
    # place. The player's data (saves, settings, game image: KEEP) never moves, so a power cut or a
    # crash during packaging cannot strand it.
    play = a.dist / NAME
    recover_keep(play, a.dist / f'{NAME}-keep')   # data set aside by the older packager
    folder = a.dist / 'launcher-build' / 'package' / NAME   # not beside the play folder: not to be started
    print(f'== Assembling {folder}')
    shutil.rmtree(folder, ignore_errors=True)
    if folder.exists():
        sys.exit(f'{folder} could not be removed (is it open?)')
    for sub in ('bin', 'scripts', 'tools', 'out', 'source'):
        (folder / sub).mkdir(parents=True)
    shutil.copy2(exe, folder / 'bin' / 'Order1886.exe')   # the build's sacredfire.exe, renamed
    shutil.copy2(caps, folder / 'bin')
    version = f'{a.version}-order1886-windows'
    (folder / 'bin' / 'VERSION').write_text(version + '\n')
    dlls = closure([exe, caps])
    for path in dlls.values():
        shutil.copy2(path, folder / 'bin')
    shutil.copy2(launcher, folder)
    python = bundle_python(folder, a.dist / 'pycache')
    for script in (ROOT / 'scripts').glob('*.py'):
        shutil.copy2(script, folder / 'scripts')
    shutil.copy2(ROOT / 'tools' / 'gen_import_names.py', folder / 'tools')
    shutil.copy2(HERE / 'order_patches.py', folder / 'tools')
    # shadPS4's symbol list, so the first start needs no download.
    for candidate in (Path(r'G:\PS4\order_win\out\aerolib.inl'), Path(r'G:\PS4\dmc_win\out\aerolib.inl'),
                      ROOT / 'out' / 'aerolib.inl'):
        if candidate.is_file():
            shutil.copy2(candidate, folder / 'out')
            break
    write_text(folder / 'README.txt', README)
    write_text(folder / 'LICENSE', (ROOT / 'LICENSE').read_text(encoding='utf-8'))
    (folder / 'THIRD-PARTY.txt').write_bytes(third_party(dlls, python).encode('utf-8'))
    shutil.copy2(LAUNCHER_SRC, folder / 'source')
    for f in SOURCES:
        shutil.copy2(f, folder / 'source')
    shutil.copy2(Path(__file__), folder / 'source')
    write_text(folder / 'SOURCE.txt', '\n'.join([
        'Source of this build (GPL-2.0-or-later):',
        f'  base:    {git("remote", "get-url", "origin") or "https://github.com/GetLostIn/CTR-NitroFueled-PC"}',
        f'  commit:  {git("rev-parse", "HEAD") or "?"} (branch {git("rev-parse", "--abbrev-ref", "HEAD") or "?"})',
        '  The Order changes: source\\order_windows_patch.py (uses source\\order_patch.py, the bbport',
        '               order1886 patch set) applied to that commit, then build.sh in MSYS2 CLANG64.',
        '  FPS/resolution patches: source\\order_patches.py (also in tools\\).',
        '  launcher:    source\\order_launcher_win.pyw; package: source\\make_order_portable.py', '']))

    bad = [str(p.relative_to(folder)) for p in folder.rglob('*') if p.is_file() and FORBIDDEN.search(str(p))]
    if bad:
        sys.exit('Game or personal files in the package, stopping:\n  ' + '\n  '.join(bad))

    archive = a.dist / f'{NAME}-windows.zip'
    archive.unlink(missing_ok=True)
    print(f'== Zipping {archive}')
    with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for path in sorted(folder.rglob('*')):
            rel = path.relative_to(folder)
            if not path.is_file() or (rel.parts[0] in KEEP and rel.parts[0] != 'out'):
                continue
            if FORBIDDEN.search(str(path)):
                sys.exit(f'Game or personal file in the package, stopping: {rel}')
            z.write(path, f'{NAME}/{rel.as_posix()}')
    digest = hashlib.sha256(archive.read_bytes()).hexdigest().upper()
    (a.dist / f'{archive.name}.sha256').write_text(f'{digest}  {archive.name}\n')
    update_play_folder(folder, play)
    shutil.rmtree(folder, ignore_errors=True)
    print(f'{archive}  {archive.stat().st_size / 1e6:.1f} MB  {len(dlls)} DLLs  {version}')
    print(f'SHA256 {digest}')
    print(f'Folder to test: {play}\\{LAUNCHER}.exe')


def recover_keep(play, keep):
    """The older packager moved KEEP aside while zipping; a run cut short (power cut, 28 Oct) left it
    there. Put it back before anything else; the play folder's own copy wins if both exist."""
    if not keep.is_dir():
        return
    play.mkdir(parents=True, exist_ok=True)
    moved = []
    for src in sorted(keep.iterdir()):
        dst = play / src.name
        if src.is_dir():
            for path in sorted(src.rglob('*')):
                target = dst / path.relative_to(src)
                if path.is_dir():
                    target.mkdir(parents=True, exist_ok=True)
                elif not target.exists():
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.move(str(path), str(target))
        elif not dst.exists():
            shutil.move(str(src), str(dst))
        moved.append(src.name)
    shutil.rmtree(keep, ignore_errors=True)
    if moved:
        print(f'== Put back from an earlier run into {play}: {", ".join(moved)}')


def update_play_folder(new, play):
    """Replaces the package files of the play folder with the new ones; KEEP (saves, settings, game
    image) stays where it is. out/ is the game image: only the package's own files in it are updated."""
    play.mkdir(parents=True, exist_ok=True)
    for old in play.iterdir():
        if old.name in KEEP:
            continue
        if old.is_dir():
            shutil.rmtree(old)
        else:
            old.unlink()
    for item in new.iterdir():
        dst = play / item.name
        if item.name == 'out' and item.is_dir():   # the package's own files in the game image folder
            dst.mkdir(exist_ok=True)
            for f in item.iterdir():
                if f.is_file():
                    shutil.copy2(f, dst / f.name)
        elif item.name in KEEP:                     # never the package's: player data
            continue
        elif item.is_dir():
            shutil.copytree(item, dst)
        else:
            shutil.copy2(item, dst)
    kept = [n for n in KEEP if (play / n).exists()]
    print(f'== Updated {play}; untouched: {", ".join(kept) or "-"}')


if __name__ == '__main__':
    main()
