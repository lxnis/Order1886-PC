#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""The Order: 1886 (PS4, CUSA00035 v01.02) - Windows launcher for the native port
(GetLostIn/CTR-NitroFueled-PC build, patched by order_windows_patch.py).

Two modes:
- portable (Order1886-Launcher.exe next to bin\\Order1886.exe, python\\, scripts\\, tools\\):
  everything is beside the launcher (out\\, user\\, bbport.ini, launcher.json, order_play.log).
- development (this script in G:\\PS41886): the MSYS2 build in G:\\Project\\order-win, data in
  G:\\PS4\\order_win. Start: C:\\msys64\\clang64\\bin\\pythonw.exe order_launcher_win.pyw

The first start of a game folder prepares the game image (prepare.py, link_modules.py, import
names, content profile) into out\\; every Play writes the FPS/resolution patches (order_patches.py
-> out\\patches.bin). Your own dump only; out\\ contains game code: do not share it.
"""
import json
import os
import re
import shutil
import struct
import subprocess
import sys
import threading
from pathlib import Path
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

APP = 'The Order: 1886'
TITLE_IDS = ('CUSA00035', 'CUSA00076')
BASE = Path(sys.executable if getattr(sys, 'frozen', False) else __file__).resolve().parent
PORTABLE = (BASE / 'bin' / 'Order1886.exe').is_file()
MSYS2 = Path(os.environ.get('MSYS2_ROOT', r'C:\msys64')) / 'clang64' / 'bin'
if PORTABLE:
    PORT = BASE
    PROBE = BASE / 'bin' / 'Order1886.exe'
    DATA = Path(os.environ.get('ORDER_DATA', BASE))
    PATCHER = BASE / 'tools' / 'order_patches.py'
    DEFAULT_GAME = None
    DLL_DIR = BASE / 'bin'
else:
    PORT = Path(os.environ.get('ORDER_PORT', BASE.parent if (BASE.parent / 'build.sh').is_file()
                               else r'G:\Project\order-win'))
    PROBE = PORT / 'out' / 'sacredfire.exe'
    DATA = Path(os.environ.get('ORDER_DATA', r'G:\PS4\order_win'))
    PATCHER = BASE / 'order_patches.py'
    DEFAULT_GAME = Path(r'H:\PS4\CUSA00035')
    DLL_DIR = MSYS2
OUT, USER, LOG = DATA / 'out', DATA / 'user', DATA / 'order_play.log'
CONF, INI = DATA / 'launcher.json', DATA / 'bbport.ini'
NO_WINDOW = getattr(subprocess, 'CREATE_NO_WINDOW', 0)

FPS = ['30', '60']        # 60 = maximum (above it the game logic breaks; QTE in chapters 6/9: use 30)
RES = {'1080p (native)': 'native', '2K (2560x1440)': '2560x1440', '4K (3840x2160)': '3840x2160'}
# Anti-aliasing: always the game's own TAA, MSAA off (BB_ORDER_NO_MSAA=1, section 49). The upscaler
# hook (FSR 3.1 in place of TAA, section 75) and MSAA 4x are no longer offered (19 Oct): lighter,
# simpler. Extra env BB_ORDER_TAA_HOOK=fsr3 or BB_ORDER_NO_MSAA=0 still work for testing.
ANISO = {'Game': '0', '4x': '4', '8x': '8', '16x': '16'}
PRESENT = {'Mailbox': 'Mailbox', 'VSync': 'Fifo', 'Immediate': 'Immediate'}
DISPLAY = ('Fullscreen', 'Windowed')
PERF = ('Fast (parallel)', 'Safe (serial)')
FAST_ENV = {'BB_VK_RECORD_THREAD': '1', 'BB_VK_RECORD_THREADS': '3', 'BB_PREP_WORKERS': '2',
            'BB_ASYNC_SUBMIT': '0', 'BB_ASYNC_FENCES': '0', 'BB_ORDER_YIELD_US': '50'}
SERIAL_ENV = {'BB_VK_RECORD_THREAD': '0', 'BB_VK_RECORD_THREADS': '1', 'BB_PREP_WORKERS': '0',
              'BB_ASYNC_SUBMIT': '0', 'BB_ASYNC_FENCES': '0'}
FAST_SPIN = '64'
ORDER_ENV = {
    'BB_SKIP_GAME_CHECK': '1', 'BB_GAME_MENU': '0', 'BB_UPSCALER': 'off', 'BB_NEO': '0',
    'BB_DMEM_MB': '9216', 'BB_ORDER_RT_IGNORE_CPU': '1', 'BB_ORDER_RT_IGNORE_GPUBUF': '1',
    # Windows: the PC memory model (dma-buf) is Linux only -> the 0.3 model, as run.py.
    'BB_PREUPLOAD': '1', 'BB_UFFD': '0', 'BB_COPY_GPU_BUFFERS': '1',
    'BB_GPU_WRITE_TWINS': '1', 'BB_GPU_WRITE_TWINS_MAX': '65536',
}

BG, PANEL, FG, DIM, ACCENT, WARN = '#1e1f24', '#2a2c33', '#e8e8ec', '#9a9ca6', '#8a6a3a', '#e0a040'


def read_sfo(folder):
    """TITLE_ID, TITLE, APP_VER, ... from sce_sys/param.sfo (PSF format)."""
    try:
        data = (Path(folder) / 'sce_sys' / 'param.sfo').read_bytes()
        magic, _ver, keys, vals, n = struct.unpack_from('<4sIIII', data, 0)
        if magic != b'\0PSF':
            return {}
        out = {}
        for i in range(n):
            koff, fmt, length, _max, doff = struct.unpack_from('<HHIII', data, 20 + 16 * i)
            key = data[keys + koff:data.index(b'\0', keys + koff)].decode()
            raw = data[vals + doff:vals + doff + length]
            out[key] = struct.unpack_from('<I', raw)[0] if fmt == 0x0404 else \
                raw.split(b'\0')[0].decode('utf-8', 'replace')
        return out
    except (OSError, struct.error, ValueError):
        return {}


def find_python():
    """Python for the preparation scripts: bundled (portable), MSYS2's, else py/python."""
    for candidate in (BASE / 'python' / 'python.exe', MSYS2 / 'python.exe'):
        if candidate.is_file():
            return [str(candidate)]
    if not getattr(sys, 'frozen', False) and Path(sys.executable).name.lower().startswith('python'):
        return [str(Path(sys.executable).with_name('python.exe'))]
    for name, extra in (('py', ['-3']), ('python', [])):
        if shutil.which(name):
            return [shutil.which(name), *extra]
    return None


def write_ini(path, updates):
    """Rewrites `updates` in the port's bbport.ini and keeps every other line."""
    try:
        lines = path.read_text(encoding='utf-8').splitlines()
    except OSError:
        lines = ['# bbport settings (The Order launcher)']
    done, out = set(), []
    for line in lines:
        key = line.split('=', 1)[0].strip() if '=' in line and not line.lstrip().startswith('#') else None
        if key in updates:
            out.append(f'{key}={updates[key]}')
            done.add(key)
        else:
            out.append(line)
    out += [f'{k}={v}' for k, v in updates.items() if k not in done]
    path.write_text('\n'.join(out) + '\n', encoding='utf-8')


class Launcher:
    def __init__(self, root):
        self.root = root
        self.busy = False
        self.icon = None
        try:
            self.conf = json.loads(CONF.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            self.conf = {}
        c = self.conf

        root.title(APP)
        root.configure(bg=BG)
        root.resizable(False, False)
        self.style()

        f = ttk.Frame(root, padding=12)
        f.pack(fill='both', expand=True)
        top = ttk.Frame(f)
        top.pack(fill='x')
        self.lbl_icon = ttk.Label(top, text='1886')
        self.lbl_icon.pack(side='left', padx=(0, 10))
        right = ttk.Frame(top)
        right.pack(side='left', fill='x', expand=True)
        ttk.Label(right, text=APP, style='Title.TLabel').pack(anchor='w')
        ttk.Label(right, text='CUSA00035 v01.02  ·  PC port (Windows)', style='Dim.TLabel').pack(anchor='w')

        opts = ttk.Frame(f, style='Panel.TFrame', padding=10)
        opts.pack(fill='x', pady=10)
        opts.columnconfigure(1, weight=1)
        ttk.Label(opts, text='Game folder', style='Panel.TLabel').grid(row=0, column=0, sticky='w')
        row = ttk.Frame(opts, style='Panel.TFrame')
        row.grid(row=0, column=1, sticky='e', pady=2)
        self.lbl_folder = ttk.Label(row, style='Folder.TLabel')
        self.lbl_folder.pack(side='left')
        ttk.Button(row, text='Browse…', width=8, command=self.browse).pack(side='left', padx=(6, 0))

        def combo(r, label, var, values):
            ttk.Label(opts, text=label, style='Panel.TLabel').grid(row=r, column=0, sticky='w')
            cb = ttk.Combobox(opts, textvariable=var, values=values, state='readonly', width=24)
            cb.grid(row=r, column=1, sticky='e', pady=2)
            cb.bind('<<ComboboxSelected>>', lambda e: self.changed())
            return cb

        pick = lambda key, table, default: tk.StringVar(value=c.get(key) if c.get(key) in table else default)
        self.v_fps = pick('fps', FPS, '60')
        self.v_res = pick('resolution', RES, '1080p (native)')
        self.v_af = pick('anisotropic', ANISO, 'Game')
        self.v_present = pick('present', PRESENT, 'Mailbox')
        self.v_mode = pick('display', DISPLAY, 'Fullscreen')
        self.v_perf = pick('performance', PERF, PERF[0])
        self.v_aspect = tk.BooleanVar(value=bool(c.get('aspect169', False)))
        self.v_async = tk.BooleanVar(value=bool(c.get('async_pipelines', True)))
        self.v_facefix = tk.BooleanVar(value=bool(c.get('facefix', True)))
        self.v_showfps = tk.BooleanVar(value=bool(c.get('show_fps', True)))
        self.v_env = tk.StringVar(value=c.get('extra_env', ''))
        combo(1, 'FPS', self.v_fps, FPS)
        self.c_res = combo(2, 'Resolution', self.v_res, list(RES))
        combo(3, 'Anisotropic', self.v_af, list(ANISO))
        combo(4, 'Present mode', self.v_present, list(PRESENT))
        combo(5, 'Display', self.v_mode, list(DISPLAY))
        combo(6, 'Performance', self.v_perf, list(PERF))
        checks = (('16:9 full screen (no black bars) (supports 2K and 4K)', self.v_aspect),
                  ('Compile shaders in the background (less stutter)', self.v_async),
                  ('Face dot fix', self.v_facefix),
                  ('FPS counter in game', self.v_showfps))
        for i, (text, var) in enumerate(checks):
            ttk.Checkbutton(opts, text=text, variable=var, command=self.changed,
                            style='Panel.TCheckbutton').grid(row=7 + i, column=0, columnspan=2,
                                                             sticky='w', pady=(6 if i == 0 else 1, 0))
        ttk.Label(opts, text='Extra env', style='Panel.TLabel').grid(row=11, column=0, sticky='w', pady=(8, 0))
        e = ttk.Entry(opts, textvariable=self.v_env, width=30)
        e.grid(row=11, column=1, sticky='e', pady=(8, 0))
        e.bind('<FocusOut>', lambda ev: self.changed())
        self.lbl_note = ttk.Label(opts, style='Note.TLabel', wraplength=420, justify='left')
        self.lbl_note.grid(row=12, column=0, columnspan=2, sticky='w', pady=(8, 0))

        buttons = ttk.Frame(f)
        buttons.pack(fill='x')
        self.btn_play = ttk.Button(buttons, text='▶  Play', style='Play.TButton', command=self.play)
        self.btn_play.pack(side='left', fill='x', expand=True)
        for text, width, cmd in (('Log', 5, self.open_log), ('Saves', 6, self.open_saves),
                                 ('Cache', 6, self.clear_cache), ('Prepare', 8, self.reprepare)):
            ttk.Button(buttons, text=text, width=width, command=cmd).pack(side='left', padx=(6, 0))
        self.lbl_status = ttk.Label(f, style='Dim.TLabel')
        self.lbl_status.pack(anchor='w', pady=(8, 0))

        root.bind('<Return>', lambda e: self.play())
        root.bind('<Escape>', lambda e: root.destroy())
        self.refresh()
        self.status('Ready. Enter = Play, Esc = quit.')

    def style(self):
        s = ttk.Style(self.root)
        s.theme_use('clam')
        s.configure('.', background=BG, foreground=FG, fieldbackground=PANEL, bordercolor=PANEL,
                    lightcolor=PANEL, darkcolor=PANEL, font=('Segoe UI', 10))
        s.configure('TFrame', background=BG)
        s.configure('Panel.TFrame', background=PANEL)
        s.configure('TLabel', background=BG, foreground=FG)
        s.configure('Title.TLabel', font=('Segoe UI', 13, 'bold'))
        s.configure('Dim.TLabel', foreground=DIM, font=('Segoe UI', 9))
        s.configure('Panel.TLabel', background=PANEL)
        s.configure('Folder.TLabel', background=PANEL, foreground=DIM, font=('Segoe UI', 9))
        s.configure('Note.TLabel', background=PANEL, foreground=WARN, font=('Segoe UI', 9))
        s.configure('Panel.TCheckbutton', background=PANEL, foreground=FG)
        s.map('Panel.TCheckbutton', background=[('active', PANEL)],
              indicatorcolor=[('selected', ACCENT), ('!selected', BG)])
        s.configure('TEntry', fieldbackground=BG, foreground=FG, insertcolor=FG)
        s.configure('TCombobox', arrowcolor=FG, foreground=FG, padding=3)
        s.map('TCombobox', fieldbackground=[('readonly', BG)], foreground=[('readonly', FG)],
              selectbackground=[('readonly', BG)], selectforeground=[('readonly', FG)])
        s.configure('TButton', background=PANEL, foreground=FG, padding=6, borderwidth=0)
        s.map('TButton', background=[('active', '#383b44'), ('disabled', PANEL)],
              foreground=[('disabled', DIM)])
        s.configure('Play.TButton', background=ACCENT, font=('Segoe UI', 11, 'bold'))
        s.map('Play.TButton', background=[('active', '#a07c46'), ('disabled', PANEL)])
        self.root.option_add('*TCombobox*Listbox.background', PANEL)
        self.root.option_add('*TCombobox*Listbox.foreground', FG)
        self.root.option_add('*TCombobox*Listbox.selectBackground', ACCENT)

    # ---- state ---------------------------------------------------------------------------
    def game(self):
        g = self.conf.get('game') or DEFAULT_GAME
        return Path(g) if g else None

    def save(self):
        for old in ('upscaler', 'antialiasing'):   # options removed 19 Oct
            self.conf.pop(old, None)
        self.conf.update(fps=self.v_fps.get(), resolution=self.v_res.get(), anisotropic=self.v_af.get(),
                         present=self.v_present.get(), display=self.v_mode.get(),
                         performance=self.v_perf.get(), aspect169=self.v_aspect.get(),
                         async_pipelines=self.v_async.get(), facefix=self.v_facefix.get(),
                         show_fps=self.v_showfps.get(), extra_env=self.v_env.get().strip())
        try:
            DATA.mkdir(parents=True, exist_ok=True)
            CONF.write_text(json.dumps(self.conf, indent=1), encoding='utf-8')
        except OSError:
            pass

    def changed(self):
        self.save()
        self.refresh()

    def refresh(self):
        # 2K/4K only with 16:9: with the black bars above 1080p the game's GPU memory is overwritten.
        if self.v_aspect.get():
            self.c_res.configure(values=list(RES))
        else:
            self.c_res.configure(values=['1080p (native)'])
            if self.v_res.get() != '1080p (native)':
                self.v_res.set('1080p (native)')
                self.save()
        g = self.game()
        ok = bool(g) and (g / 'eboot.bin').exists()
        self.lbl_folder.configure(text=f'…\\{g.parent.name}\\{g.name}' if g else '(not set)',
                                  foreground=DIM if ok else WARN)
        note = ''
        if not PROBE.exists():
            note = f'Port not found: {PROBE.name} is missing.'
        elif not ok:
            note = 'Game folder not found. Browse to your CUSA00035 folder.'
        elif self.v_fps.get() == '60':
            note = '60 FPS: the QTEs of chapters 6 and 9 need 30 FPS.'
        self.lbl_note.configure(text=note)
        (self.lbl_note.grid if note else self.lbl_note.grid_remove)()
        if self.icon is None and ok:
            try:
                img = tk.PhotoImage(file=str(g / 'sce_sys' / 'icon0.png'))
                self.icon = img.subsample(max(1, img.width() // 64))
                self.lbl_icon.configure(image=self.icon, text='')
                self.root.iconphoto(False, self.icon)
            except tk.TclError:
                pass

    def status(self, text):
        self.lbl_status.configure(text=text)

    def browse(self):
        start = self.game() or Path.home()
        start = start if start.exists() else (start.parent if start.parent.exists() else Path.home())
        f = filedialog.askdirectory(parent=self.root, title='Select The Order: 1886 folder (contains eboot.bin)',
                                    initialdir=str(start), mustexist=True)
        if not f:
            return
        f = Path(f)
        if not (f / 'eboot.bin').exists():
            messagebox.showerror(APP, f'No eboot.bin in:\n{f}\n\nSelect the CUSA00035 folder.')
            return
        sfo = read_sfo(f)
        if sfo.get('TITLE_ID') not in TITLE_IDS:
            if not messagebox.askyesno(APP, f'{sfo.get("TITLE", "?")} ({sfo.get("TITLE_ID", "?")}) is not '
                                       'CUSA00035. Use it anyway? (the FPS/resolution patches may not apply)'):
                return
        self.conf['game'] = str(f)
        self.icon = None
        self.save()
        self.refresh()
        self.status(f'Using: {sfo.get("TITLE", APP)} v{sfo.get("APP_VER", "?")}')

    # ---- launching -----------------------------------------------------------------------
    def needs_prepare(self):
        try:
            same = (OUT / 'source.txt').read_text(encoding='utf-8').strip() == str(self.game())
        except OSError:
            same = False
        return not (same and (OUT / 'boot-linked.bin').exists() and (OUT / 'content.bin').exists())

    def run_logged(self, cmd, log, env, cwd):
        log.write('$ ' + ' '.join(map(str, cmd)) + '\n')
        log.flush()
        return subprocess.run(list(map(str, cmd)), cwd=cwd, env=env, stdin=subprocess.DEVNULL, stdout=log,
                              stderr=subprocess.STDOUT, creationflags=NO_WINDOW).returncode

    def prepare(self, env, python, step):
        game = self.game()
        OUT.mkdir(parents=True, exist_ok=True)
        (OUT / 'source.txt').unlink(missing_ok=True)
        steps = [('Preparing the game image (first start, takes a while)…', 'scripts/prepare.py',
                  [game, '--out', OUT]),
                 ('Linking modules…', 'scripts/link_modules.py',
                  [game, '--out', OUT, '--modules', 'libc.prx', 'libSceFios2.prx']),
                 ('Import names…', 'tools/gen_import_names.py', ['--out', OUT]),
                 ('Content profile…', 'scripts/content_profile.py', [game, '--out', OUT])]
        with open(OUT / 'prepare.log', 'w', encoding='utf-8', errors='replace') as log:
            for text, script, args in steps:
                step(text)
                if self.run_logged([*python, '-X', 'utf8', PORT / script, *args], log, env, PORT):
                    raise RuntimeError(f'{script} failed.\nSee {OUT / "prepare.log"}')
        (OUT / 'source.txt').write_text(str(game) + '\n', encoding='utf-8')

    def patch(self, env, python, step):
        """order_patches.py -> out\\patches.bin. Returns a warning (or '') - never stops the game."""
        step('Applying FPS/resolution patches…')
        res = RES[self.v_res.get()] if self.v_aspect.get() else 'native'
        cmd = [*python, '-X', 'utf8', PATCHER, OUT, '--fps', self.v_fps.get(), '--res', res]
        if self.v_aspect.get():
            cmd.append('--aspect169')
        if self.v_perf.get() == PERF[0]:
            cmd += ['--spin', FAST_SPIN]
        for pair in self.extra_pairs():
            if pair.startswith('ORDER_PATCH_ARGS='):
                cmd += pair.split('=', 1)[1].split()
        with open(OUT / 'patch.log', 'w', encoding='utf-8', errors='replace') as log:
            if self.run_logged(cmd, log, env, PATCHER.parent):
                (OUT / 'patches.bin').unlink(missing_ok=True)
                return 'order_patches.py failed (see out\\patch.log): 30 FPS, native resolution.'
        return ''

    def extra_pairs(self):
        """KEY=VALUE pairs; a value with spaces in double quotes (backslashes kept for Windows paths)."""
        return [f'{k}={v[1:-1] if v.startswith(chr(34)) else v}'
                for k, v in re.findall(r'([A-Za-z_][A-Za-z0-9_]*)=("[^"]*"|\S*)', self.v_env.get())]

    def launch_env(self):
        env = dict(os.environ)
        for key, value in ORDER_ENV.items():
            env.setdefault(key, value)
        for key, value in (FAST_ENV if self.v_perf.get() == PERF[0] else SERIAL_ENV).items():
            env.setdefault(key, value)
        if self.v_perf.get() == PERF[0] and self.v_aspect.get() and RES[self.v_res.get()] != 'native':
            env['BB_PREP_WORKERS'] = '3'
        env['BB_GUEST_IN_PLACE'] = '0'
        if DLL_DIR.is_dir():
            env['PATH'] = f'{DLL_DIR}{os.pathsep}{env.get("PATH", "")}'
        fps = self.v_fps.get()
        if fps == '30':
            env['BB_VBLANK_HZ'], env['BB_FPS_LIMIT'] = '60', '60'
        else:
            env['BB_VBLANK_HZ'], env['BB_FPS_LIMIT'] = '480', fps
            env['BB_ORDER_FLIPRATE'] = '0'
        env['BB_CONFIG'] = str(INI)
        env['BB_GPU_USER_DIR'] = str(USER)
        env['BB_UPSCALER'] = 'off'
        env['BB_ANISO'] = ANISO[self.v_af.get()]
        env['BB_PRESENT_MODE'] = PRESENT[self.v_present.get()]
        env['BB_FULLSCREEN'] = '1' if self.v_mode.get() == 'Fullscreen' else '0'
        env['BB_ORDER_NO_MSAA'] = '1'
        env['BB_ASYNC_PIPELINES'] = '1' if self.v_async.get() else '0'
        env['BB_ORDER_FACEFIX'] = '1' if self.v_facefix.get() else '0'
        for pair in self.extra_pairs():
            if '=' in pair:
                k, v = pair.split('=', 1)
                if re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', k):
                    env[k] = v
        write_ini(INI, {'fullscreen': env['BB_FULLSCREEN'], 'fps_limit': env['BB_FPS_LIMIT'],
                        'show_fps': '1' if self.v_showfps.get() else '0', 'upscaler': 'off',
                        'async_pipelines': env['BB_ASYNC_PIPELINES']})
        return env

    def play(self):
        if self.busy:
            return
        if not PROBE.exists():
            messagebox.showerror(APP, f'{PROBE} not found.\nBuild the port first (bash build.sh in MSYS2 CLANG64).')
            return
        game = self.game()
        if not game or not (game / 'eboot.bin').exists():
            messagebox.showerror(APP, f'Game files not found:\n{game}\nBrowse to your CUSA00035 folder.')
            return
        python = find_python()
        if not python:
            messagebox.showerror(APP, 'No Python found for the preparation scripts.')
            return
        self.save()
        DATA.mkdir(parents=True, exist_ok=True)
        USER.mkdir(parents=True, exist_ok=True)
        env = self.launch_env()
        prepare = self.needs_prepare() or self.conf.pop('force_prepare', False)
        self.busy = True
        self.btn_play.state(['disabled'])
        step = lambda t: self.root.after(0, self.status, t)

        def worker():
            try:
                if prepare:
                    self.prepare(env, python, step)
                warning = self.patch(env, python, step)
            except (RuntimeError, OSError) as e:
                self.root.after(0, self.failed, str(e))
                return
            cmd = [str(PROBE), str(OUT / 'boot-linked.bin'), '--content-profile', str(OUT / 'content.bin'),
                   '--app0', str(game), '--user', str(USER), '--timeout', '0']
            if (OUT / 'import_names.txt').is_file():
                cmd += ['--import-names', str(OUT / 'import_names.txt')]
            if (OUT / 'patches.bin').is_file():
                cmd += ['--patches', str(OUT / 'patches.bin')]
            self.root.after(0, self.started)
            with open(LOG, 'w', encoding='utf-8', errors='replace') as log:
                log.write('env: ' + ' '.join(f'{k}={env[k]}' for k in sorted(env) if k.startswith('BB_')) + '\n')
                if warning:
                    log.write(warning + '\n')
                log.flush()
                rc = subprocess.run(cmd, cwd=PORT, env=env, stdin=subprocess.DEVNULL, stdout=log,
                                    stderr=subprocess.STDOUT, creationflags=NO_WINDOW).returncode
            self.root.after(0, self.finished, rc)

        threading.Thread(target=worker, daemon=True).start()

    def started(self):
        self.status(f'Running {APP} …')
        self.root.withdraw()

    def failed(self, message):
        self.busy = False
        self.btn_play.state(['!disabled'])
        self.status('Could not start.')
        messagebox.showerror(APP, message)

    def finished(self, rc):
        self.busy = False
        self.btn_play.state(['!disabled'])
        self.root.deiconify()
        try:
            lines = LOG.read_text(encoding='utf-8', errors='replace').splitlines()
        except OSError:
            lines = []
        issues = [l for l in lines if re.match(r'^(STOP|Fault|Guest fault|Host fault)', l)]
        if issues:
            self.status('The game stopped with an error. See Log.')
            messagebox.showerror(APP, 'The game stopped:\n' + '\n'.join(issues[:4]) + f'\n\nFull log: {LOG}')
        else:
            self.status(f'Finished (exit code {rc}).')

    def open_log(self):
        if LOG.exists():
            os.startfile(str(LOG))
        else:
            messagebox.showinfo(APP, 'No log yet. Play once first.')

    def open_saves(self):
        USER.mkdir(parents=True, exist_ok=True)
        os.startfile(str(USER))

    def clear_cache(self):
        for tid in TITLE_IDS:
            shutil.rmtree(USER / 'cache' / tid, ignore_errors=True)
        self.status('Shader cache cleared.')

    def reprepare(self):
        self.conf['force_prepare'] = True
        (OUT / 'source.txt').unlink(missing_ok=True)
        self.status('The game image will be prepared again on the next Play.')


if __name__ == '__main__':
    root = tk.Tk(className='order1886-launcher')
    Launcher(root)
    root.mainloop()
