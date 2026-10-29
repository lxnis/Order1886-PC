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
import time
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
# Saves outside the portable folder (29 Oct): every launcher version reads and writes the same
# place, so a new download or a rebuilt folder finds the progress without copying anything.
# user\savedata stays the game's working copy; the launcher syncs it (newest wins) before Play
# and after the game exits, and keeps the replaced copy in backup\.
SAVE_HOME = Path(os.environ.get('ORDER_SAVE_HOME') or
                 Path(os.environ.get('USERPROFILE', str(Path.home()))) / 'Saved Games' / 'The Order 1886 PC')
SAVE_KEEP_BACKUPS = 5

FPS = ['30', '60']        # 60 = maximum (above it the game logic breaks; QTE in chapters 6/9: use 30)
RES = {'1080p (native)': 'native', '2K (2560x1440)': '2560x1440', '4K (3840x2160)': '3840x2160'}
# Anti-aliasing: always the game's own AA, TAA + MSAA 4x (BB_ORDER_NO_MSAA=0). The upscaler hook
# (FSR 3.1 in place of TAA, section 75) is no longer offered (19 Oct). MSAA off (section 49) was the
# v0.2 default; with it a cutscene went fully blurred (28 Oct, likely its depth of field); it stays
# available for testing through Extra env BB_ORDER_NO_MSAA=1 (and BB_ORDER_TAA_HOOK=fsr3).
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
    # GPU log: errors only (29 Oct). Every warning went unbuffered to order_play.log from the draw
    # recording thread (dozens per frame, "isn't dword aligned", "Rejecting invalid T#"); on
    # Windows each line is a WriteFile the antivirus also inspects: 31-33 FPS in Chapter I, 60
    # without them (draw pipe stage B 24 -> 5 us per draw, as on Linux). Extra env
    # BB_GPU_LOG=warning brings them back for debugging.
    'BB_GPU_LOG': 'error',
}

BG, PANEL, FG, DIM, ACCENT, WARN = '#1e1f24', '#2a2c33', '#e8e8ec', '#9a9ca6', '#8a6a3a', '#e0a040'
# Look chosen in the launcher editor (28 Oct): font, outer spacing.
FONT, PAD = 'Trebuchet MS', 35
# Type sizes and the space above each element, from the launcher editor (29 Oct).
SET, HEAD, NOTE, SMALL, PLAY = 25, 36, 13, 15, 15
GAP = {'title': 16, 'subtitle': 4, 'folder': 24, 'play': 8, 'buttons': 12, 'status': 29,
       'fps': 8, 'resolution': 2, 'anisotropic': 2, 'present': 2, 'display': 2, 'performance': 2,
       'aspect': 10, 'async': 0, 'facefix': 4, 'showfps': 0, 'extra_env': 10, 'note': 10}


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


def save_files(root):
    """Save files of the game under root (a savedata folder): .../1/CUSA00035/<slot>/..."""
    out = []
    for tid in TITLE_IDS:
        for d in (root.glob(f'*/{tid}') if root.is_dir() else ()):
            out += [f for f in d.rglob('*') if f.is_file()]
    return out


def save_time(root):
    """Newest modification time of the saves under root (0 = none)."""
    return max((f.stat().st_mtime for f in save_files(root)), default=0)


def copy_saves(src, dst, backup_dir=None):
    """Replaces the game's save folders under dst with src's (dst's old ones to backup_dir first)."""
    stamp = time.strftime('%Y%m%d-%H%M%S')
    for tid in TITLE_IDS:
        for s in src.glob(f'*/{tid}'):
            user = s.parent.name
            d = dst / user / tid
            tmp = dst / user / f'{tid}.new'
            shutil.rmtree(tmp, ignore_errors=True)
            shutil.copytree(s, tmp)
            if d.exists():
                if backup_dir is not None:
                    b = backup_dir / stamp / user / tid
                    b.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copytree(d, b, dirs_exist_ok=True)
                shutil.rmtree(d)
            tmp.rename(d)
    if backup_dir is not None and backup_dir.is_dir():
        old = sorted(p for p in backup_dir.iterdir() if p.is_dir())
        for p in old[:-SAVE_KEEP_BACKUPS]:
            shutil.rmtree(p, ignore_errors=True)


def find_old_saves(skip):
    """Saves of other copies of this port (older versions, other downloads): folders with
    Order1886-Launcher.exe and user\\savedata, up to two levels below each drive, Desktop,
    Downloads and Documents. Newest first: [(time, savedata folder)]."""
    places = [Path(f'{c}:\\') for c in 'CDEFGHIJKLMNOPQRSTUVWXYZ' if os.path.isdir(f'{c}:\\')]
    home = Path(os.environ.get('USERPROFILE', str(Path.home())))
    places += [home / 'Desktop', home / 'Downloads', home / 'Documents']
    seen, found = set(), []
    for place in places:
        for pattern in ('Order1886-Launcher.exe', '*/Order1886-Launcher.exe', '*/*/Order1886-Launcher.exe'):
            try:
                hits = list(place.glob(pattern))
            except OSError:
                continue
            for exe in hits:
                sd = exe.parent / 'user' / 'savedata'
                try:
                    key = str(sd.resolve()).lower()
                except OSError:
                    continue
                if key in seen or key == str(skip.resolve()).lower():
                    continue
                seen.add(key)
                t = save_time(sd)
                if t:
                    found.append((t, sd))
    return sorted(found, reverse=True)


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

        # Landscape, 2x size (28 Oct): left = game, folder, Play; right = settings.
        f = ttk.Frame(root, padding=PAD)
        f.pack(fill='both', expand=True)
        left = ttk.Frame(f)
        left.grid(row=0, column=0, sticky='nsew', padx=(0, PAD))
        opts = ttk.Frame(f, style='Panel.TFrame', padding=16)
        opts.grid(row=0, column=1, sticky='nsew')
        f.columnconfigure(1, weight=1)
        f.rowconfigure(0, weight=1)

        self.lbl_icon = ttk.Label(left, text='1886', style='Title.TLabel', anchor='center')
        self.lbl_icon.pack(anchor='center')
        ttk.Label(left, text=APP, style='Title.TLabel', anchor='center').pack(anchor='center', pady=(GAP['title'], 0))
        ttk.Label(left, text='CUSA00035 v01.02  ·  PC port (Windows)', style='Dim.TLabel',
                  anchor='center').pack(anchor='center', pady=(GAP['subtitle'], 0))

        folder = ttk.Frame(left, style='Panel.TFrame', padding=16)
        folder.pack(fill='x', pady=(GAP['folder'], 0))
        ttk.Label(folder, text='Game folder', style='Panel.TLabel').pack(anchor='w')
        row = ttk.Frame(folder, style='Panel.TFrame')
        row.pack(fill='x', pady=(8, 0))
        self.lbl_folder = ttk.Label(row, style='Folder.TLabel')
        self.lbl_folder.pack(side='left')
        ttk.Button(row, text='Browse…', width=8, command=self.browse).pack(side='right', padx=(12, 0))

        self.btn_play = ttk.Button(left, text='▶  Play', style='Play.TButton', command=self.play)
        self.btn_play.pack(fill='x', pady=(GAP['play'], 0))
        buttons = ttk.Frame(left)
        buttons.pack(fill='x', pady=(GAP['buttons'], 0))
        for i, (text, cmd) in enumerate((('Log', self.open_log), ('Saves', self.open_saves),
                                         ('Import', self.import_saves), ('Cache', self.clear_cache),
                                         ('Prepare', self.reprepare))):
            buttons.columnconfigure(i, weight=1, uniform='b')
            ttk.Button(buttons, text=text, command=cmd).grid(row=0, column=i, sticky='ew',
                                                             padx=(0 if i == 0 else 12, 0))
        self.lbl_status = ttk.Label(left, style='Dim.TLabel', wraplength=520, justify='left')
        self.lbl_status.pack(anchor='w', pady=(GAP['status'], 0))

        opts.columnconfigure(1, weight=1)
        ttk.Label(opts, text='Settings', style='Head.TLabel').grid(row=0, column=0, columnspan=2,
                                                                 sticky='w')

        def combo(r, label, var, values, key):
            ttk.Label(opts, text=label, style='Set.TLabel').grid(row=r, column=0, sticky='w', padx=(0, 16),
                                                                 pady=(GAP[key], 0))
            cb = ttk.Combobox(opts, textvariable=var, values=values, state='readonly', width=24,
                              font=(FONT, SET))
            cb.grid(row=r, column=1, sticky='ew', pady=(GAP[key], 0))
            cb.bind('<<ComboboxSelected>>', lambda e: self.changed())
            return cb

        pick = lambda key, table, default: tk.StringVar(value=c.get(key) if c.get(key) in table else default)
        self.v_fps = pick('fps', FPS, '60')
        self.v_res = pick('resolution', RES, '1080p (native)')
        self.v_af = pick('anisotropic', ANISO, 'Game')
        self.v_present = pick('present', PRESENT, 'VSync')
        self.v_mode = pick('display', DISPLAY, 'Fullscreen')
        self.v_perf = pick('performance', PERF, PERF[0])
        self.v_aspect = tk.BooleanVar(value=bool(c.get('aspect169', False)))
        self.v_async = tk.BooleanVar(value=bool(c.get('async_pipelines', True)))
        self.v_facefix = tk.BooleanVar(value=bool(c.get('facefix', True)))
        self.v_showfps = tk.BooleanVar(value=bool(c.get('show_fps', True)))
        self.v_env = tk.StringVar(value=c.get('extra_env', ''))
        combo(1, 'FPS', self.v_fps, FPS, 'fps')
        self.c_res = combo(2, 'Resolution', self.v_res, list(RES), 'resolution')
        combo(3, 'Anisotropic', self.v_af, list(ANISO), 'anisotropic')
        combo(4, 'Present mode', self.v_present, list(PRESENT), 'present')
        combo(5, 'Display', self.v_mode, list(DISPLAY), 'display')
        combo(6, 'Performance', self.v_perf, list(PERF), 'performance')
        checks = (('16:9 full screen (no black bars) (supports 2K and 4K)', self.v_aspect, 'aspect'),
                  ('Compile shaders in the background (less stutter)', self.v_async, 'async'),
                  ('Face dot fix', self.v_facefix, 'facefix'),
                  ('FPS counter in game', self.v_showfps, 'showfps'))
        for i, (text, var, key) in enumerate(checks):
            ttk.Checkbutton(opts, text=text, variable=var, command=self.changed,
                            style='Panel.TCheckbutton').grid(row=7 + i, column=0, columnspan=2,
                                                             sticky='w', pady=(GAP[key], 0))
        ttk.Label(opts, text='Extra env', style='Set.TLabel').grid(row=11, column=0, sticky='w', pady=(GAP['extra_env'], 0))
        e = ttk.Entry(opts, textvariable=self.v_env, width=30, font=(FONT, SET))
        e.grid(row=11, column=1, sticky='ew', pady=(GAP['extra_env'], 0))
        e.bind('<FocusOut>', lambda ev: self.changed())
        self.lbl_note = ttk.Label(opts, style='Note.TLabel', wraplength=560, justify='left')
        self.lbl_note.grid(row=12, column=0, columnspan=2, sticky='w', pady=(GAP['note'], 0))

        root.bind('<Return>', lambda e: self.play())
        root.bind('<Escape>', lambda e: root.destroy())
        self.refresh()
        self.status('EXPERIMENTAL')
        self.root.after(200, self.startup_saves)

    def style(self):
        s = ttk.Style(self.root)
        s.theme_use('clam')
        s.configure('.', background=BG, foreground=FG, fieldbackground=PANEL, bordercolor=PANEL,
                    lightcolor=PANEL, darkcolor=PANEL, font=(FONT, 20))
        s.configure('TFrame', background=BG)
        s.configure('Panel.TFrame', background=PANEL)
        s.configure('TLabel', background=BG, foreground=FG)
        s.configure('Title.TLabel', font=(FONT, 30, 'bold'))
        s.configure('Head.TLabel', background=PANEL, foreground=FG, font=(FONT, HEAD, 'bold'))
        s.configure('Dim.TLabel', foreground=DIM, font=(FONT, SMALL))
        s.configure('Panel.TLabel', background=PANEL)
        s.configure('Set.TLabel', background=PANEL, font=(FONT, SET))
        s.configure('Folder.TLabel', background=PANEL, foreground=DIM, font=(FONT, SMALL))
        s.configure('Note.TLabel', background=PANEL, foreground=WARN, font=(FONT, NOTE))
        s.configure('Panel.TCheckbutton', background=PANEL, foreground=FG, indicatorsize=16, padding=2,
                    font=(FONT, SET))
        s.map('Panel.TCheckbutton', background=[('active', PANEL)],
              indicatorcolor=[('selected', ACCENT), ('!selected', BG)])
        s.configure('TEntry', fieldbackground=BG, foreground=FG, insertcolor=FG, padding=3)
        s.configure('TCombobox', arrowcolor=FG, foreground=FG, padding=3, arrowsize=16)
        s.map('TCombobox', fieldbackground=[('readonly', BG)], foreground=[('readonly', FG)],
              selectbackground=[('readonly', BG)], selectforeground=[('readonly', FG)])
        s.configure('TButton', background=PANEL, foreground=FG, padding=12, borderwidth=0)
        s.map('TButton', background=[('active', '#383b44'), ('disabled', PANEL)],
              foreground=[('disabled', DIM)])
        s.configure('Play.TButton', background=ACCENT, font=(FONT, PLAY, 'bold'), padding=20)
        s.map('Play.TButton', background=[('active', '#a07c46'), ('disabled', PANEL)])
        self.root.option_add('*TCombobox*Listbox.background', PANEL)
        self.root.option_add('*TCombobox*Listbox.foreground', FG)
        self.root.option_add('*TCombobox*Listbox.selectBackground', ACCENT)
        self.root.option_add('*TCombobox*Listbox.font', (FONT, SET))

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
                self.icon = img.subsample(max(1, img.width() // 256))   # 2x (was 64 px; landscape layout)
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
        env['BB_ORDER_NO_MSAA'] = '0'   # MSAA on (28 Oct: off likely broke cutscene depth of field)
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
        self.sync_saves(quiet=True)
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
        self.sync_saves(quiet=True)
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

    # ---- saves ---------------------------------------------------------------------------
    def sync_saves(self, quiet=False):
        """Newest wins between user\\savedata (this folder) and SAVE_HOME\\savedata."""
        local, home = USER / 'savedata', SAVE_HOME / 'savedata'
        tl, th = save_time(local), save_time(home)
        try:
            if th > tl + 2:
                copy_saves(home, local, SAVE_HOME / 'backup')
                msg = f'Saves loaded from {SAVE_HOME}.'
            elif tl > th + 2:
                copy_saves(local, home, SAVE_HOME / 'backup')
                msg = f'Saves backed up to {SAVE_HOME}.'
            else:
                return
        except OSError as e:
            messagebox.showerror(APP, f'Could not sync the saves:\n{e}\n\nThey stay in {local}.')
            return
        if not quiet:
            self.status(msg)

    def startup_saves(self):
        """First start with no shared saves yet: offer the saves of this folder and of older copies
        of the port (newest first); with only one copy, take it."""
        if save_time(SAVE_HOME / 'savedata'):
            self.sync_saves()
            return
        self.status('Looking for saves of an older version…')
        self.root.update_idletasks()
        local = USER / 'savedata'
        found = find_old_saves(local)
        if save_time(local):
            found = sorted(found + [(save_time(local), local)], reverse=True)
        chosen = found[0][1] if len(found) == 1 else None
        for t, sd in found[:4] if chosen is None else ():
            when = time.strftime('%d %b %Y %H:%M', time.localtime(t))
            where = 'this folder' if sd == local else str(sd.parent.parent)
            if messagebox.askyesno(APP, f'Saves found ({len(found)} copies of the port):\n\n{where}\n'
                                   f'last saved {when}\n\nUse these?'):
                chosen = sd
                break
        if chosen is None and save_time(local):
            chosen = local
        if chosen is None:
            self.status('No saves yet (new game). Progress is kept in Saved Games\\The Order 1886 PC.')
            return
        try:
            copy_saves(chosen, SAVE_HOME / 'savedata')
            if chosen != local:
                copy_saves(SAVE_HOME / 'savedata', local, SAVE_HOME / 'backup')
        except OSError as e:
            messagebox.showerror(APP, f'Could not copy the saves:\n{e}')
            return
        self.status('Saves: ' + ('this folder' if chosen == local else str(chosen.parent.parent))
                    + f' (kept in {SAVE_HOME})')

    def import_saves(self):
        f = filedialog.askdirectory(parent=self.root, title='Select the old port folder (contains user\\savedata)',
                                    mustexist=True)
        if not f:
            return
        f = Path(f)
        for sd in (f / 'user' / 'savedata', f / 'savedata', f):
            if save_time(sd):
                break
        else:
            messagebox.showerror(APP, f'No The Order: 1886 saves in:\n{f}')
            return
        if not messagebox.askyesno(APP, f'Replace the current saves with the ones in\n{sd}?\n'
                                   f'(the current ones go to {SAVE_HOME / "backup"})'):
            return
        try:
            copy_saves(sd, SAVE_HOME / 'savedata', SAVE_HOME / 'backup')
            copy_saves(SAVE_HOME / 'savedata', USER / 'savedata', SAVE_HOME / 'backup')
        except OSError as e:
            messagebox.showerror(APP, f'Could not copy the saves:\n{e}')
            return
        self.status(f'Saves imported from {sd}.')

    def open_log(self):
        if LOG.exists():
            os.startfile(str(LOG))
        else:
            messagebox.showinfo(APP, 'No log yet. Play once first.')

    def open_saves(self):
        SAVE_HOME.mkdir(parents=True, exist_ok=True)
        os.startfile(str(SAVE_HOME))

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
