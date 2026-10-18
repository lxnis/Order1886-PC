<!-- order1886 -->
> **This branch (`order1886-win`) is a native Windows port of The Order: 1886 (PS4, CUSA00035).**
> See [order1886/README.md](order1886/README.md) for download, status and build steps. The text below is the README of the CTR-NitroFueled-PC project it is built on.

# The Order: 1886 — native PC port (Windows)

An experimental native Windows port of **The Order: 1886** (PS4, CUSA00035, update 01.02). The
game's own x86-64 code runs on your CPU and its graphics go through Vulkan. No emulator, no game
files included: **you need your own decrypted dump of the game.**

This branch (`order1886-win`) is [GetLostIn/CTR-NitroFueled-PC](https://github.com/GetLostIn/CTR-NitroFueled-PC)
(bbport → [SacredFire](https://github.com/T3CHNOLOG1C/SacredFire) → GetLostIn, with the Windows
layer from Supermedo's Windows port of bbport), via the [DmC branch](https://github.com/lxnis/DmC-PC),
plus the changes for The Order described below. The work on The Order was done on Linux first
(bbport, branch `order1886`) and carried over to this Windows tree. The README of the base project is kept in
[docs/README-CTR-NitroFueled-PC.md](docs/README-CTR-NitroFueled-PC.md).

## Download and play

1. Download `Order1886-PC-portable-windows.zip` from the Releases page and unpack it somewhere
   writable (not Program Files).
2. Run `Order1886-Launcher.exe`, press **Browse…** and select your `CUSA00035` folder
   (the one with `eboot.bin`, `sce_module\` and `sce_sys\param.sfo`).
3. Press **Play**. The first start prepares the game image from your dump (`out\`, a few minutes).

Requirements: 64-bit Windows 10 (1903+) or 11, a Vulkan 1.3 GPU with current drivers, 16 GB RAM.
Tested on an Intel i3-12100F with an NVIDIA RTX 3080 Ti (driver 616.92), Windows 11. Nothing else
to install.

Launcher settings: 30/60 FPS (community patch), 16:9 full screen without the black bars (also at
2K/4K), FSR 3.1 in place of the game's TAA, MSAA on/off, anisotropic filtering, present mode,
fullscreen/windowed, Fast (parallel) / Safe (serial) recording, background shader compiles, the
face dot fix and an FPS counter.

Status: boots, menus, gameplay and cutscenes run. Known issues:
- Shaders seen for the first time stall the game briefly, most visibly in cutscenes. They are
  cached (`user\cache`) and load at start from the next session on, so this fades as you play.
- At 60 FPS the button-mash QTEs of chapters 6 and 9 cannot be completed: play those at 30 FPS.
- 2K/4K only together with 16:9 (with the black bars the game's GPU memory gets overwritten).
- Faces can look too dark in dark rooms.
- DLSS (available in the Linux build) is not wired up on Windows yet; FSR 3.1 is.
- No online features (the game sees a signed-out console).

## Linux (AppImage)

`TheOrder1886-x86_64.AppImage` on the Releases page is the Linux build (bbport, native Linux, with
DLSS on NVIDIA RTX cards). Make it executable and run it; the launcher asks for your `CUSA00035`
folder and keeps the game image, saves and settings in `~/.local/share/order1886/`.
Its source: branch [`order1886-linux`](https://github.com/lxnis/Order1886-PC/tree/order1886-linux) of this repository (bbport with
every section of `order1886/order_patch.py` applied), built with `order1886/linux/build-order-appimage.sh`;
the Linux launcher is `order1886/linux/order_launcher.pyw`.

## What the changes are

Everything is applied by `order1886/order_windows_patch.py` (already applied in this branch;
marked `bbport-order` in the code). It loads `order1886/order_patch.py`, the Linux patch set of
the bbport `order1886` branch, and applies each of its sections to this tree, with Windows
variants where the trees differ. The main fixes:

| Area | Change |
|---|---|
| Runtime (`src/`) | The Order's missing system calls and stubs; the job workers' yield (`BB_ORDER_YIELD_US`) |
| Shader recompiler | SRT walker: dynamic offsets, deferred offsets, invalid user-data pointers read as 0 instead of crashing; unaligned buffer reads; SNORM/format fallbacks |
| Pipelines | background compiles also for indirect draws (cutscene stutter), per-frame rules so characters do not vanish; a bad shader skips the draw instead of aborting |
| Rasterizer | face fix (depth bias for the skin pass, the game's EQUAL depth test kept so distant objects do not flicker); render targets immune to CPU/GPU-buffer writes at 1440p/4K; MSAA handling |
| TAA | optional FSR 3.1 in place of the game's TAA (`BB_ORDER_TAA_HOOK=fsr3`) |
| Windows only | SRT recovery through `bb_setjmp`; the Linux DLSS hook falls back to FSR 3.1; branding (window and menu title, exe icon) |

`order1886/order_patches.py` writes the FPS/resolution community patches (`out\patches.bin`, from
the GoldHEN/shadPS4 patch database). `order1886/order_launcher_win.pyw` is the launcher,
`order1886/order_run.py` runs the game from a source build, and
`order1886/make_order_portable.py` builds the portable ZIP.

## Build from source

In the **MSYS2 CLANG64** shell, with the packages from `packaging/windows/README.md`:

```bash
git clone -b order1886-win https://github.com/lxnis/Order1886-PC
cd Order1886-PC
git submodule update --init --recursive
bash build.sh                                   # out/sacredfire.exe
python order1886/order_run.py --prepare         # ORDER_GAME=<your CUSA00035 folder>
```

The portable package (python.org Python with Tkinter, in PowerShell):

```powershell
py -3 order1886\make_order_portable.py --version v0.1
```

## License

GPL-2.0-or-later, like the projects it is built on (see `LICENSE`). The bundled libraries and their
licenses are listed in the package's `THIRD-PARTY.txt`.

Not affiliated with Sony Interactive Entertainment or Ready at Dawn. No game files, keys or
copyrighted game data are included or distributed; you need your own copy of the game.
Modified builds must not be connected to official servers.
