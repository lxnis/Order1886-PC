#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""The Order: 1886 (PS4) - Linux launcher for the native PC port (bbport, branch order1886).

Two modes:
  - development (python3 order_launcher.pyw): Project/bbport/out/bb-probe, data in PS41886/.
  - AppImage (AppRun sets ORDER1886_APPDIR): the bundled port and scripts; game image, saves,
    shader cache, log and settings in ~/.local/share/order1886/ (no game files in the AppImage).

Same layout as the DmC launcher: game folder (Browse), FPS, resolution, 16:9, Play.
Supported dumps (your own disc/console only): CUSA00035 and CUSA00076, plus any other
"The Order: 1886" folder (the binary FPS/resolution patches are then skipped if they do not match).

Per game folder:
  - game image (prepare.py + link_modules.py + content_profile.py) in PS41886/out (CUSA00035,
    the image we already have) or PS41886/out_<TITLE_ID> for other versions; prepared again
    automatically when the folder changes (out*/source.txt).
  - saves and shader cache in PS41886/user, log in PS41886/order_play.log.
  - FPS/resolution patches: order_patches.py (checks the original bytes first; on a different
    eboot it refuses and the game runs unpatched: 30 FPS, native resolution).
Settings: PS41886/order_launcher.json.

Start:  python3 $HOME/PS41886/order_launcher.pyw
"""
import json
import os
import re
import shlex
import shutil
import struct
import subprocess
import sys
import threading
from pathlib import Path
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

PROJECT = (Path.home() / 'Project')
BBPORT = PROJECT / 'bbport'
APPDIR = os.environ.get('ORDER1886_APPDIR')
if APPDIR:
    SHARE = Path(APPDIR) / 'usr' / 'share' / 'order1886'
    KERJA = Path(os.environ.get('XDG_DATA_HOME') or Path.home() / '.local' / 'share') / 'order1886'
    PROBE = SHARE / 'bin' / 'bb-probe'
    SCRIPTS = SHARE / 'scripts'
    PATCHER = SHARE / 'order_patches.py'
    WORKDIR = KERJA                     # the port keeps user/cache/<title> under its cwd
    DEFAULT_GAME = None
else:
    SHARE = None
    KERJA = (Path.home() / 'PS41886')
    PROBE = BBPORT / 'out' / 'bb-probe'
    SCRIPTS = BBPORT / 'scripts'
    PATCHER = KERJA / 'order_patches.py'
    WORKDIR = BBPORT
    DEFAULT_GAME = (Path.home() / 'PS4/CUSA00035')
USER, LOG = KERJA / 'user', KERJA / 'order_play.log'
CONF = KERJA / 'order_launcher.json'


def python3():
    """The system's python3 for the preparation scripts (the AppImage launcher is frozen)."""
    if getattr(sys, 'frozen', False):
        found = shutil.which('python3')
        if not found:
            raise RuntimeError('python3 is needed to prepare the game (install it with your package manager).')
        return found
    return sys.executable


def clean_env():
    """Environment for child processes, without PyInstaller's library path or the AppImage marker."""
    env = dict(os.environ)
    orig = env.pop('LD_LIBRARY_PATH_ORIG', None)
    if getattr(sys, 'frozen', False):
        if orig is not None:
            env['LD_LIBRARY_PATH'] = orig
        else:
            env.pop('LD_LIBRARY_PATH', None)
    env.pop('ORDER1886_APPDIR', None)
    return env

KNOWN_IDS = {'CUSA00035': 'CUSA00035', 'CUSA00076': 'CUSA00076 (EU)'}
FPS = ['30', '60']                       # 60 = maximum (above it the game logic breaks: QTE mash)
RES = {'1080p (native)': 'native', '2K (2560x1440)': '2560x1440', '4K (3840x2160)': '3840x2160'}
# Upscaler / AA in place of the game's own TAA (compute 92311aca, order_patch.py section 75):
# DLAA / FSR 3.1 Native AA at the game's render resolution (1080p, 2K or 4K).
UPSCALER = {'Native (game TAA)': 'off', 'DLSS (DLAA, NVIDIA RTX)': 'dlss', 'FSR 3.1 (Native AA)': 'fsr3'}
# CPU usage of the port (17 Oct, i3-12100F): Fast = parallel recording + the game's job workers
# sleep when idle (order_patch.py 73/74, order_patches.py --spin): ~80 FPS in game instead of ~60.
PERF = ('Fast (parallel, 80+ FPS)', 'Safe (serial, ~60 FPS)')
FAST_ENV = {'BB_VK_RECORD_THREAD': '1', 'BB_VK_RECORD_THREADS': '3', 'BB_PREP_WORKERS': '2',
            'BB_ASYNC_SUBMIT': '0', 'BB_ASYNC_FENCES': '0', 'BB_ORDER_YIELD_US': '50'}
FAST_SPIN = '64'

# Anti-aliasing of the game itself: TAA + MSAA 4x (scene color). MSAA off = section 49
# (BB_ORDER_NO_MSAA=1): lighter, edges a little softer/jaggier.
AA = {'Game (TAA + MSAA)': '0', 'Game TAA, MSAA off': '1'}
ANISO = {'Game': '0', '4x': '4', '8x': '8', '16x': '16'}
DISPLAY = ('Fullscreen', 'Windowed')   # BB_FULLSCREEN=1/0 (window.cpp, SDL)

# Same base settings as order-port.sh: serial recording (no screen glitches), no upscaler, the
# game's own filtering, 9 GiB direct memory (large GpuStack for 1440p/4K), pink band fixes.
ORDER_ENV = {
    'BB_SKIP_GAME_CHECK': '1', 'BB_GAME_MENU': '0', 'BB_UPSCALER': 'off', 'BB_ANISO': '0',
    'BB_NEO': '0', 'BB_DMEM_MB': '9216',
    'BB_ORDER_RT_IGNORE_CPU': '1', 'BB_ORDER_RT_IGNORE_GPUBUF': '1',
    '__GL_SHADER_DISK_CACHE': '1', '__GL_SHADER_DISK_CACHE_SKIP_CLEANUP': '1',
    '__GL_SHADER_DISK_CACHE_SIZE': '10737418240',
}
# order-port.sh's serial package (Safe): no parallel recording.
SERIAL_ENV = {'BB_VK_RECORD_THREAD': '0', 'BB_VK_RECORD_THREADS': '1', 'BB_PREP_WORKERS': '0',
              'BB_ASYNC_SUBMIT': '0', 'BB_ASYNC_FENCES': '0'}

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


def out_dir(title_id):
    """CUSA00035 keeps the image prepared so far (out/); other versions get their own folder."""
    return KERJA / 'out' if title_id in ('', 'CUSA00035') else KERJA / f'out_{title_id}'



def set_ini(path, key, value):
    """The port reads its settings (FPS counter...) from bbport.ini in its working folder."""
    try:
        lines = path.read_text(encoding='utf-8').splitlines() if path.is_file() else []
    except OSError:
        lines = []
    lines = [l for l in lines if not l.startswith(key + '=')] + [f'{key}={value}']
    try:
        path.write_text('\n'.join(lines) + '\n', encoding='utf-8')
    except OSError:
        pass

class Launcher:
    def __init__(self, root):
        self.root = root
        self.busy = False
        self.icon = None
        try:
            self.conf = json.loads(CONF.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            self.conf = {}

        root.title('The Order: 1886')
        root.configure(bg=BG)
        root.resizable(True, True)
        root.minsize(620, 0)
        self.style()

        f = ttk.Frame(root, padding=18)
        f.pack(fill='both', expand=True)
        top = ttk.Frame(f)
        top.pack(fill='x')
        # Centered header: game icon, title, then title ID and version.
        self.lbl_icon = ttk.Label(top, text='1886', anchor='center')
        self.lbl_icon.pack(anchor='center')
        ttk.Label(top, text='The Order: 1886', style='Title.TLabel',
                  anchor='center').pack(anchor='center', pady=(8, 0))
        self.lbl_info = ttk.Label(top, text='', style='Dim.TLabel', anchor='center')
        self.lbl_info.pack(anchor='center', pady=(2, 0))

        opts = ttk.Frame(f, style='Panel.TFrame', padding=16)
        opts.pack(fill='x', pady=14)
        opts.columnconfigure(1, weight=1)
        ttk.Label(opts, text='Game folder', style='Panel.TLabel').grid(row=0, column=0, sticky='w')
        row = ttk.Frame(opts, style='Panel.TFrame')
        row.grid(row=0, column=1, sticky='e', pady=2)
        self.lbl_folder = ttk.Label(row, style='Folder.TLabel')
        self.lbl_folder.pack(side='left')
        ttk.Button(row, text='Browse…', width=8, command=self.browse).pack(side='left', padx=(6, 0))

        def combo(r, label, var, values):
            ttk.Label(opts, text=label, style='Panel.TLabel').grid(row=r, column=0, sticky='w')
            c = ttk.Combobox(opts, textvariable=var, values=values, state='readonly', width=26)
            c.grid(row=r, column=1, sticky='e', pady=4)
            c.bind('<<ComboboxSelected>>', lambda e: self.changed())
            return c

        self.v_fps = tk.StringVar(value=self.conf.get('fps') if self.conf.get('fps') in FPS else '60')
        res = self.conf.get('resolution')
        self.v_res = tk.StringVar(value=res if res in RES else '1080p (native)')
        self.v_aspect = tk.BooleanVar(value=bool(self.conf.get('aspect169', False)))
        self.v_async = tk.BooleanVar(value=bool(self.conf.get('async_pipelines', True)))
        self.v_facefix = tk.BooleanVar(value=bool(self.conf.get('facefix', True)))
        self.v_stats = tk.BooleanVar(value=bool(self.conf.get('frame_stats', False)))
        self.v_showfps = tk.BooleanVar(value=bool(self.conf.get('show_fps', True)))
        perf = self.conf.get('performance')
        self.v_perf = tk.StringVar(value=perf if perf in PERF else PERF[0])
        self.v_env = tk.StringVar(value=self.conf.get('extra_env', ''))
        up = self.conf.get('upscaler')
        self.v_up = tk.StringVar(value=up if up in UPSCALER else 'Native (game TAA)')
        aa = self.conf.get('antialiasing')
        self.v_aa = tk.StringVar(value=aa if aa in AA else 'Game (TAA + MSAA)')
        af = self.conf.get('anisotropic')
        self.v_af = tk.StringVar(value=af if af in ANISO else 'Game')
        combo(1, 'FPS', self.v_fps, FPS)
        self.c_res = combo(2, 'Resolution', self.v_res, list(RES))
        combo(3, 'Upscaler', self.v_up, list(UPSCALER))
        combo(4, 'Anti-aliasing', self.v_aa, list(AA))
        combo(5, 'Anisotropic', self.v_af, list(ANISO))
        mode = self.conf.get('display')
        self.v_mode = tk.StringVar(value=mode if mode in DISPLAY else 'Fullscreen')
        combo(6, 'Display', self.v_mode, list(DISPLAY))
        combo(7, 'Performance', self.v_perf, list(PERF))
        checks = (('16:9 full screen (no black bars) (supports 2K and 4K)', self.v_aspect),
                  ('Compile shaders in the background (less stutter)', self.v_async),
                  ('Face dot fix', self.v_facefix),
                  ('FPS counter in game', self.v_showfps),
                  ('Frame statistics in the log', self.v_stats))
        for i, (text, var) in enumerate(checks):
            ttk.Checkbutton(opts, text=text, variable=var, command=self.changed,
                            style='Panel.TCheckbutton').grid(row=8 + i, column=0, columnspan=2,
                                                             sticky='w', pady=(8 if i == 0 else 2, 0))
        ttk.Label(opts, text='Extra env', style='Panel.TLabel').grid(row=13, column=0, sticky='w', pady=(10, 0))
        e = ttk.Entry(opts, textvariable=self.v_env, width=36)
        e.grid(row=13, column=1, sticky='e', pady=(10, 0))
        e.bind('<FocusOut>', lambda ev: self.changed())
        self.lbl_note = ttk.Label(opts, style='Note.TLabel', wraplength=560, justify='left')
        self.lbl_note.grid(row=14, column=0, columnspan=2, sticky='w', pady=(10, 0))

        buttons = ttk.Frame(f)
        buttons.pack(fill='x')
        self.btn_play = ttk.Button(buttons, text='▶  Play', style='Play.TButton', command=self.play)
        self.btn_play.pack(side='left', fill='x', expand=True)
        for text, width, cmd in (('Log', 6, self.open_log), ('Saves', 7, self.open_saves),
                                 ('Cache', 7, self.clear_cache), ('Prepare', 9, self.reprepare)):
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
        font = ('Sans', 12)
        s.configure('.', background=BG, foreground=FG, fieldbackground=PANEL, bordercolor=PANEL,
                    lightcolor=PANEL, darkcolor=PANEL, font=font)
        s.configure('TFrame', background=BG)
        s.configure('Panel.TFrame', background=PANEL)
        s.configure('TLabel', background=BG, foreground=FG)
        s.configure('Title.TLabel', font=('Sans', 18, 'bold'))
        s.configure('Dim.TLabel', foreground=DIM, font=('Sans', 11))
        s.configure('Panel.TLabel', background=PANEL)
        s.configure('Folder.TLabel', background=PANEL, foreground=DIM, font=('Sans', 11))
        s.configure('Note.TLabel', background=PANEL, foreground=WARN, font=('Sans', 11))
        s.configure('Panel.TCheckbutton', background=PANEL, foreground=FG)
        s.map('Panel.TCheckbutton', background=[('active', PANEL)],
              indicatorcolor=[('selected', ACCENT), ('!selected', BG)])
        s.configure('TEntry', fieldbackground=BG, foreground=FG, insertcolor=FG)
        s.configure('TCombobox', arrowcolor=FG, foreground=FG, padding=5)
        s.map('TCombobox', fieldbackground=[('readonly', BG)], foreground=[('readonly', FG)],
              selectbackground=[('readonly', BG)], selectforeground=[('readonly', FG)])
        s.configure('TButton', background=PANEL, foreground=FG, padding=8, borderwidth=0)
        s.map('TButton', background=[('active', '#383b44'), ('disabled', PANEL)],
              foreground=[('disabled', DIM)])
        s.configure('Play.TButton', background=ACCENT, font=('Sans', 14, 'bold'), padding=12)
        s.map('Play.TButton', background=[('active', '#a07c46'), ('disabled', PANEL)])
        self.root.option_add('*TCombobox*Listbox.background', PANEL)
        self.root.option_add('*TCombobox*Listbox.foreground', FG)
        self.root.option_add('*TCombobox*Listbox.selectBackground', ACCENT)
        self.root.option_add('*TCombobox*Listbox.font', ('Sans', 12))

    # ---- state ---------------------------------------------------------------------------
    def game(self):
        g = self.conf.get('game') or DEFAULT_GAME
        return Path(g) if g else None

    def title_id(self):
        g = self.game()
        return read_sfo(g).get('TITLE_ID', '') if g else ''

    def save(self):
        self.conf.update(fps=self.v_fps.get(), resolution=self.v_res.get(), upscaler=self.v_up.get(),
                         antialiasing=self.v_aa.get(), anisotropic=self.v_af.get(),
                         display=self.v_mode.get(),
                         aspect169=self.v_aspect.get(), async_pipelines=self.v_async.get(),
                         facefix=self.v_facefix.get(), frame_stats=self.v_stats.get(),
                         show_fps=self.v_showfps.get(),
                         performance=self.v_perf.get(),
                         extra_env=self.v_env.get().strip())
        try:
            CONF.write_text(json.dumps(self.conf, indent=1), encoding='utf-8')
        except OSError:
            pass

    def changed(self):
        self.save()
        self.refresh()

    def refresh(self):
        # 2K/4K only with 16:9: with the black bars (2.4:1) above 1080p the game's GPU memory is
        # overwritten (garbage shaders, black screen after loading; 18 Oct).
        if hasattr(self, 'c_res'):
            if self.v_aspect.get():
                self.c_res.configure(values=list(RES))
            else:
                self.c_res.configure(values=['1080p (native)'])
                if self.v_res.get() != '1080p (native)':
                    self.v_res.set('1080p (native)')
                    self.save()
        g = self.game()
        ok = bool(g) and (g / 'eboot.bin').exists()
        sfo = read_sfo(g) if ok else {}
        tid = sfo.get('TITLE_ID', '')
        self.lbl_folder.configure(text=f'…/{g.parent.name}/{g.name}' if g else '(not set)',
                                  foreground=DIM if ok else WARN)
        self.lbl_info.configure(text=f'{KNOWN_IDS.get(tid, tid or "?")}  ·  v{sfo.get("APP_VER", "?")}'
                                if ok else 'Select your game folder')
        note = ''
        if not PROBE.exists():
            note = 'The port is missing (bb-probe not found).'
        elif not ok:
            note = 'Game folder not found. Browse to your The Order: 1886 folder (with eboot.bin).'
        elif tid != 'CUSA00035':
            note = (f'{tid}: the FPS/resolution patches were made for CUSA00035 v01.02. If they do not '
                    'match this eboot the game runs unpatched (30 FPS, 1080p).')
        elif UPSCALER[self.v_up.get()] != 'off':
            note = (f'{self.v_up.get()}: replaces the game TAA (new - report ghosting or smearing). '
                    'If it cannot run, the log says why and the game TAA stays.')
            if UPSCALER[self.v_up.get()] == 'dlss' and not (PROBE.parent / 'libbbport_dlss.so').exists():
                note += ' DLSS files are missing: FSR 3.1 is used instead.'
        elif self.v_fps.get() != '30':
            note = 'Above 30 FPS: QTE softlock in chapters 6 and 9 (community note) - play those at 30.'
        self.lbl_note.configure(text=note)
        (self.lbl_note.grid if note else self.lbl_note.grid_remove)()
        if self.icon is None and ok:
            try:
                img = tk.PhotoImage(file=str(g / 'sce_sys' / 'icon0.png'))
                self.icon = img.subsample(max(1, img.width() // 128))
                self.lbl_icon.configure(image=self.icon, text='')
                self.root.iconphoto(False, self.icon)
            except tk.TclError:
                pass

    def status(self, text):
        self.lbl_status.configure(text=text)

    def pick_folder(self, start):
        """The desktop's own folder dialog (KDE kdialog, GNOME zenity, or the XDG portal through
        zenity); Tk's dialog (white, old-style) only when none is installed."""
        title = 'Select your The Order: 1886 folder (contains eboot.bin)'
        tools = []
        if shutil.which('kdialog'):
            tools.append(['kdialog', '--title', title, '--getexistingdirectory', str(start)])
        if shutil.which('zenity'):
            tools.append(['zenity', '--file-selection', '--directory', '--title', title,
                          f'--filename={start}/'])
        if 'gnome' in os.environ.get('XDG_CURRENT_DESKTOP', '').lower():
            tools.reverse()                      # GNOME: zenity first, KDE: kdialog first
        for cmd in tools:
            try:
                r = subprocess.run(cmd, env=clean_env(), capture_output=True, text=True)
            except OSError:
                continue
            if r.returncode == 0:
                return r.stdout.strip()
            if r.returncode == 1:               # cancelled
                return ''
        self.dark_dialogs()
        return filedialog.askdirectory(parent=self.root, title=title, initialdir=str(start),
                                       mustexist=True)

    def dark_dialogs(self):
        """Dark colors for Tk's built-in dialog (fallback only)."""
        for pattern, value in (('*Background', PANEL), ('*Foreground', FG),
                               ('*selectBackground', ACCENT), ('*selectForeground', FG),
                               ('*Entry.Background', BG), ('*Listbox.Background', BG),
                               ('*Button.Background', PANEL), ('*activeBackground', '#383b44'),
                               ('*highlightBackground', PANEL), ('*insertBackground', FG)):
            self.root.option_add(pattern, value)

    def browse(self):
        start = self.game() or Path('/run/media') / os.environ.get('USER', '')
        start = start if start.exists() else (start.parent if start.parent.exists() else Path.home())
        f = self.pick_folder(start)
        if not f:
            return
        f = Path(f)
        if not (f / 'eboot.bin').exists():
            messagebox.showerror('The Order: 1886', f'No eboot.bin in:\n{f}')
            return
        sfo = read_sfo(f)
        tid, title = sfo.get('TITLE_ID', ''), sfo.get('TITLE', '?')
        if tid not in KNOWN_IDS and 'order' not in title.lower():
            messagebox.showerror('The Order: 1886', f'{title} ({tid or "TITLE_ID unreadable"}) '
                                 'is not The Order: 1886.')
            return
        self.conf['game'] = str(f)
        self.icon = None
        self.save()
        self.refresh()
        self.status(f'Using: {title} {tid} v{sfo.get("APP_VER", "?")}')

    # ---- launching -----------------------------------------------------------------------
    def needs_prepare(self, out):
        try:
            same = (out / 'source.txt').read_text(encoding='utf-8').strip() == str(self.game())
        except OSError:
            # out/ prepared before this launcher (order-port.sh): CUSA00035 at the default path.
            same = out == KERJA / 'out' and self.game() == DEFAULT_GAME
        return not (same and (out / 'boot-linked.bin').exists() and (out / 'content.bin').exists())

    def prepare(self, env, out, step):
        game = self.game()
        out.mkdir(parents=True, exist_ok=True)
        (out / 'source.txt').unlink(missing_ok=True)
        steps = [('Preparing the game image (first start, takes a while)…', 'prepare.py',
                  [game, '--out', out]),
                 ('Linking modules (libc.prx, libSceFios2.prx)…', 'link_modules.py',
                  [game, '--out', out, '--modules', 'libc.prx', 'libSceFios2.prx']),
                 ('Content profile…', 'content_profile.py', [game, '--out', out])]
        with open(out / 'prepare.log', 'w', encoding='utf-8', errors='replace') as log:
            for text, script, args in steps:
                step(text)
                cmd = [python3(), str(SCRIPTS / script), *map(str, args)]
                log.write('$ ' + ' '.join(cmd) + '\n')
                log.flush()
                r = subprocess.run(cmd, cwd=SCRIPTS.parent, env=env, stdin=subprocess.DEVNULL,
                                   stdout=log, stderr=subprocess.STDOUT)
                if r.returncode != 0:
                    raise RuntimeError(f'{script} failed.\nSee {out / "prepare.log"}')
        (out / 'source.txt').write_text(str(game) + '\n', encoding='utf-8')

    def patch(self, out, step):
        """order_patches.py -> out/patches.bin. Returns a warning (or '') - never stops the game."""
        step('Applying FPS/resolution patches…')
        res = RES[self.v_res.get()] if self.v_aspect.get() else 'native'   # 2K/4K need 16:9
        cmd = [python3(), str(PATCHER), str(out), '--fps', '30' if self.v_fps.get() == '30' else '60',
               '--res', res]
        if self.v_aspect.get():
            cmd.append('--aspect169')
        if self.v_perf.get() == PERF[0]:
            cmd += ['--spin', FAST_SPIN]
        # Extra env ORDER_PATCH_ARGS="--views off --fix800 off": extra options for order_patches.py.
        try:
            for pair in shlex.split(self.v_env.get()):
                if pair.startswith('ORDER_PATCH_ARGS='):
                    cmd += shlex.split(pair.split('=', 1)[1])
        except ValueError:
            pass
        r = subprocess.run(cmd, cwd=KERJA, env=clean_env(), capture_output=True, text=True)
        self.patch_out = (r.stdout or '').strip()
        if r.returncode != 0:
            (out / 'patches.bin').unlink(missing_ok=True)
            return (r.stderr or r.stdout).strip() or 'order_patches.py failed'
        return ''

    def launch_env(self):
        env = clean_env()
        if SHARE is not None and (SHARE / 'lib').is_dir():   # libraries bundled for the port
            env['LD_LIBRARY_PATH'] = ':'.join(filter(None, [str(SHARE / 'lib'), env.get('LD_LIBRARY_PATH')]))
        for key, value in ORDER_ENV.items():
            env.setdefault(key, value)
        for key, value in (FAST_ENV if self.v_perf.get() == PERF[0] else SERIAL_ENV).items():
            env.setdefault(key, value)
        # 2K/4K in Fast mode: 3 draw preparation workers (18 Oct, 2K: 50-57 -> 58-60 FPS; the GPU
        # command thread is the limit, not the GPU). Extra env BB_PREP_WORKERS=N still wins.
        if self.v_perf.get() == PERF[0] and self.v_aspect.get() and RES[self.v_res.get()] != 'native':
            env['BB_PREP_WORKERS'] = '3'
        fps = self.v_fps.get()
        # With the 60 FPS patch the game presents on the next vblank: at a 60/120 Hz virtual
        # vblank a frame that takes 20 ms waits for the 3rd tick (120 Hz -> 40 FPS). Above 30 FPS
        # the vblank runs at 480 Hz (ticks every 2 ms) and the frame limit sets the rate instead.
        if fps == '30':
            env['BB_VBLANK_HZ'], env['BB_FPS_LIMIT'] = '60', '60'
        else:
            env['BB_VBLANK_HZ'] = '480'
            env['BB_FPS_LIMIT'] = fps
        # The game asks for flip rate 1 (every 2nd vblank = 30 FPS) in gameplay; above 30 FPS the
        # port ignores that (order_patch.py section 67). Extra env BB_ORDER_FLIPRATE=1 = the game's.
        if fps != '30':
            env['BB_ORDER_FLIPRATE'] = '0'
        # bbport's own upscaler path is Bloodborne's (jitter + compute 9a9cf8a9): kept off. The Order's
        # hook (in place of its TAA 92311aca) reads BB_ORDER_TAA_HOOK=dlss|fsr3.
        env['BB_UPSCALER'] = 'off'
        env['BB_ANISO'] = ANISO[self.v_af.get()]
        env['BB_FULLSCREEN'] = '1' if self.v_mode.get() == 'Fullscreen' else '0'
        if AA[self.v_aa.get()] == '1':
            env['BB_ORDER_NO_MSAA'] = '1'
        env['BB_ASYNC_PIPELINES'] = '1' if self.v_async.get() else '0'
        env['BB_ORDER_FACEFIX'] = '1' if self.v_facefix.get() else '0'
        if UPSCALER[self.v_up.get()] != 'off':
            env['BB_ORDER_TAA_HOOK'] = UPSCALER[self.v_up.get()]
        if self.v_stats.get():
            env['BB_FRAME_STATS'] = '1'
        # Extra env: KEY=VALUE pairs separated by spaces (e.g. BB_ORDER_FULLBARRIER=1).
        try:
            pairs = shlex.split(self.v_env.get())
        except ValueError:
            pairs = []
        for pair in pairs:
            if '=' in pair:
                k, v = pair.split('=', 1)
                if re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', k):
                    env[k] = v
        return env

    def play(self):
        if self.busy:
            return
        if not PROBE.exists():
            messagebox.showerror('The Order: 1886', f'{PROBE} not found.')
            return
        game = self.game()
        if not game or not (game / 'eboot.bin').exists():
            messagebox.showerror('The Order: 1886', f'Game files not found:\n{game}\nBrowse to your game folder.')
            return
        self.save()
        USER.mkdir(parents=True, exist_ok=True)
        tid = self.title_id()
        out = out_dir(tid)
        env = self.launch_env()
        prepare = self.needs_prepare(out) or self.conf.pop('force_prepare', False)
        self.busy = True
        self.btn_play.state(['disabled'])

        def step(text):
            self.root.after(0, self.status, text)

        def worker():
            try:
                if prepare:
                    self.prepare(env, out, step)
                warning = self.patch(out, step)
            except (RuntimeError, OSError) as e:
                self.root.after(0, self.failed, str(e))
                return
            cmd = [str(PROBE), str(out / 'boot-linked.bin'), '--content-profile', str(out / 'content.bin')]
            if (out / 'patches.bin').is_file():
                cmd += ['--patches', str(out / 'patches.bin')]
            cmd += ['--app0', str(game), '--user', str(USER), '--timeout', '0']
            self.root.after(0, self.started, warning)
            with open(LOG, 'w', encoding='utf-8', errors='replace') as log:
                log.write(f'== launcher: {tid} {game}\n== patches: {warning or "ok"}\n'
                          f'== {getattr(self, "patch_out", "")}\n')
                log.flush()
                WORKDIR.mkdir(parents=True, exist_ok=True)
                set_ini(WORKDIR / 'bbport.ini', 'show_fps', '1' if self.v_showfps.get() else '0')
                rc = subprocess.run(cmd, cwd=WORKDIR, env=env, stdin=subprocess.DEVNULL, stdout=log,
                                    stderr=subprocess.STDOUT).returncode
            self.root.after(0, self.finished, rc)

        threading.Thread(target=worker, daemon=True).start()

    def started(self, warning):
        self.status('Running The Order: 1886 …' + ('  (unpatched: patches do not match this version)'
                                                   if warning else ''))
        self.root.withdraw()

    def failed(self, message):
        self.busy = False
        self.btn_play.state(['!disabled'])
        self.status('Could not start.')
        messagebox.showerror('The Order: 1886', message)

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
            messagebox.showerror('The Order: 1886', 'The game stopped:\n' + '\n'.join(issues[:4]) +
                                 f'\n\nFull log: {LOG}')
        else:
            self.status(f'Finished (exit code {rc}).')

    def open_log(self):
        if LOG.exists():
            subprocess.Popen(['xdg-open', str(LOG)], env=clean_env())
        else:
            messagebox.showinfo('The Order: 1886', 'No log yet. Play once first.')

    def open_saves(self):
        USER.mkdir(parents=True, exist_ok=True)
        subprocess.Popen(['xdg-open', str(USER)], env=clean_env())

    def clear_cache(self):
        tid = self.title_id() or 'CUSA00035'
        for base in (USER, WORKDIR / 'user'):
            shutil.rmtree(base / 'cache' / tid, ignore_errors=True)
        self.status(f'Shader cache cleared ({tid}).')

    def reprepare(self):
        self.conf['force_prepare'] = True
        (out_dir(self.title_id()) / 'source.txt').unlink(missing_ok=True)
        self.save()
        self.status('The game image will be prepared again on the next Play.')


if __name__ == '__main__':
    root = tk.Tk(className='order-launcher')
    Launcher(root)
    root.mainloop()
