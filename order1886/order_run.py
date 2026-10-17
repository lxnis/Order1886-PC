#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""The Order: 1886 (CUSA00035 v01.02) di Windows, memakai build GetLostIn/CTR-NitroFueled-PC
(worktree G:\\Project\\order-win, sudah di-patch dengan order_windows_patch.py).

    C:\\msys64\\clang64\\bin\\python.exe G:\\PS41886\\order_run.py            siapkan (pertama kali) + main
    C:\\msys64\\clang64\\bin\\python.exe G:\\PS41886\\order_run.py --prepare  siapkan ulang, lalu main

Image game diolah dari dump milik sendiri ke G:\\PS4\\order_win\\out (berisi kode game: JANGAN
dibagikan). Save dan cache shader di G:\\PS4\\order_win\\user, log di G:\\PS4\\order_win\\order_play.log.
Variabel environment yang di-set sebelum menjalankan menimpa nilai di bawah (mis. set BB_ORDER_YIELD_US=200).
Patch komunitas (order_patches.py): ORDER_FPS=60|30 (default 60), ORDER_RES=native|2560x1440|3840x2160
(hanya dengan ORDER_ASPECT=1, 16:9). ORDER_SAFE=1: rekam serial (lebih lambat, paling aman).
"""
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PORT = Path(os.environ.get('ORDER_PORT', HERE.parent if (HERE.parent / 'build.sh').is_file()
                           else r'G:\Project\order-win'))
GAME = Path(os.environ.get('ORDER_GAME', r'H:\PS4\CUSA00035'))
DATA = Path(os.environ.get('ORDER_DATA', r'G:\PS4\order_win'))
OUT, USER, LOG = DATA / 'out', DATA / 'user', DATA / 'order_play.log'
MSYS2 = Path(os.environ.get('MSYS2_ROOT', r'C:\msys64')) / 'clang64' / 'bin'

FAST_ENV = {'BB_VK_RECORD_THREAD': '1', 'BB_VK_RECORD_THREADS': '3', 'BB_PREP_WORKERS': '2',
            'BB_ASYNC_SUBMIT': '0', 'BB_ASYNC_FENCES': '0', 'BB_ORDER_YIELD_US': '50'}
SERIAL_ENV = {'BB_VK_RECORD_THREAD': '0', 'BB_VK_RECORD_THREADS': '1', 'BB_PREP_WORKERS': '0',
              'BB_ASYNC_SUBMIT': '0', 'BB_ASYNC_FENCES': '0'}
ORDER_ENV = {
    # Sama dengan order-port.sh (Linux).
    'BB_SKIP_GAME_CHECK': '1', 'BB_GAME_MENU': '0', 'BB_UPSCALER': 'off', 'BB_ANISO': '0',
    'BB_NEO': '0', 'BB_DMEM_MB': '9216',
    'BB_ORDER_RT_IGNORE_CPU': '1', 'BB_ORDER_RT_IGNORE_GPUBUF': '1',
    # Shader di-compile di belakang (tanpa ini cutscene stutter: tiap shader baru menahan frame).
    'BB_ASYNC_PIPELINES': '1',
    # Windows: model memori PC (dma-buf) hanya ada di Linux -> model 0.3, seperti run.py.
    # Kalau macet di menu, coba matikan satu per satu: set BB_PREUPLOAD=0 / BB_GPU_WRITE_TWINS=0.
    'BB_PREUPLOAD': '1', 'BB_UFFD': '0', 'BB_COPY_GPU_BUFFERS': '1',
    'BB_GPU_WRITE_TWINS': '1', 'BB_GPU_WRITE_TWINS_MAX': '65536', 'BB_VBLANK_HZ': '60',
}


def fail(message):
    print(f'ERROR: {message}', file=sys.stderr)
    sys.exit(1)


def step(env, title, script, *args, cwd=None):
    print(f'== {title}', flush=True)
    cmd = [sys.executable, '-X', 'utf8', str(script), *map(str, args)]
    if subprocess.run(cmd, cwd=cwd or PORT, env=env).returncode != 0:
        fail(f'{Path(script).name} gagal (lihat output di atas).')


def main():
    probe = PORT / 'out' / 'sacredfire.exe'
    if not probe.is_file():
        fail(f'{probe} tidak ada: jalankan "bash build.sh" di MSYS2 CLANG64 dulu.')
    if not (GAME / 'eboot.bin').is_file():
        fail(f'Tidak ada eboot.bin di {GAME} (set ORDER_GAME ke folder CUSA00035).')
    env = dict(os.environ)
    for key, value in ORDER_ENV.items():
        env.setdefault(key, value)
    env['BB_GUEST_IN_PLACE'] = '0'
    # Seperti launcher: Fast (paralel) kecuali ORDER_SAFE=1 (serial, paket aman order-port.sh).
    safe = env.get('ORDER_SAFE', '0') == '1'
    for key, value in (SERIAL_ENV if safe else FAST_ENV).items():
        env.setdefault(key, value)
    fps = env.get('ORDER_FPS', '60')
    if fps == '30':
        env.setdefault('BB_FPS_LIMIT', '60')
    else:
        env['BB_VBLANK_HZ'] = '480'
        env.setdefault('BB_FPS_LIMIT', fps)
        env.setdefault('BB_ORDER_FLIPRATE', '0')
    if MSYS2.is_dir():   # DLL build dari source (SDL3, FFmpeg, ...)
        env['PATH'] = f'{MSYS2}{os.pathsep}{env.get("PATH", "")}'
    DATA.mkdir(parents=True, exist_ok=True)
    USER.mkdir(parents=True, exist_ok=True)
    env.setdefault('BB_CONFIG', str(DATA / 'bbport.ini'))
    env['BB_GPU_USER_DIR'] = str(USER)

    if '--prepare' in sys.argv or not (OUT / 'boot-linked.bin').is_file() or not (OUT / 'content.bin').is_file():
        step(env, '1/4 prepare.py (agak lama)', PORT / 'scripts/prepare.py', GAME, '--out', OUT)
        step(env, '2/4 link_modules.py (libc.prx + libSceFios2.prx)', PORT / 'scripts/link_modules.py',
             GAME, '--out', OUT, '--modules', 'libc.prx', 'libSceFios2.prx')
        step(env, '3/4 gen_import_names.py', PORT / 'tools/gen_import_names.py', '--out', OUT)
        step(env, '4/4 content_profile.py', PORT / 'scripts/content_profile.py', GAME, '--out', OUT)

    patch_args = ['--fps', fps, '--res', env.get('ORDER_RES', 'native'),
                  '--gpustack', env.get('ORDER_GPUSTACK', 'auto'), '--fix800', env.get('ORDER_FIX800', 'on'),
                  '--views', env.get('ORDER_VIEWS', 'on'), '--spin', env.get('ORDER_SPIN', 'off' if safe else '64')]
    if env.get('ORDER_ASPECT', '0') == '1':
        patch_args.append('--aspect169')
    patch_args += env.get('ORDER_PATCH_ARGS', '').split()
    step(env, 'order_patches.py', HERE / 'order_patches.py', OUT, *patch_args, cwd=HERE)

    cmd = [str(probe), str(OUT / 'boot-linked.bin'), '--content-profile', str(OUT / 'content.bin'),
           '--app0', str(GAME), '--user', str(USER), '--timeout', env.get('BB_TIMEOUT', '0')]
    if (OUT / 'import_names.txt').is_file():
        cmd += ['--import-names', str(OUT / 'import_names.txt')]
    if (OUT / 'patches.bin').is_file():
        cmd += ['--patches', str(OUT / 'patches.bin')]
    cmd += [a for a in sys.argv[1:] if a != '--prepare']
    print(f'== The Order: {probe.name} (log: {LOG})', flush=True)
    with open(LOG, 'w', encoding='utf-8', errors='replace') as log:
        log.write('env: ' + ' '.join(f'{k}={env[k]}' for k in sorted(env) if k.startswith(('BB_', 'ORDER_'))) + '\n')
        proc = subprocess.Popen(cmd, cwd=PORT, env=env, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, text=True, encoding='utf-8', errors='replace')
        for line in proc.stdout:
            log.write(line)
            if not line.startswith(('GPU [', 'SRT walker')):
                sys.stdout.write(line)
        rc = proc.wait()
    print(f'== kode keluar {rc}')
    sys.exit(rc)


if __name__ == '__main__':
    main()
