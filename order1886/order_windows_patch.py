#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""The Order: 1886 (CUSA00035 v01.02) — perubahan port untuk pohon Windows
(GetLostIn/CTR-NitroFueled-PC, branch dmc dari lxnis/DmC-PC, MSYS2 CLANG64).

Memakai order_patch.py (versi Linux, file yang sama di folder ini) dan menyesuaikan titik sisip yang
berbeda di pohon Windows. Idempotent (marker 'bbport-order'); line ending file (CRLF) dipertahankan.

    python order_windows_patch.py G:/Project/order-win
"""
import importlib.util
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


class Linux:
    """order_patch.py dimuat per pernyataan: setiap fungsi bagian mendapat salinan globals saat ia
    didefinisikan. Di order_patch.py beberapa nama konstanta dipakai ulang oleh bagian yang lebih baru
    (mis. FB_OLD); di pohon baru fungsi lama akan membaca nilai yang salah tanpa ini."""

    def __init__(self, src):
        import ast
        import types
        self.__dict__['_spaces'] = []
        tree = ast.parse(src.read_text(encoding='utf-8'), str(src))
        ns = {'__name__': 'order_patch', '__file__': str(src)}
        self.__dict__['_ns'] = ns
        for node in tree.body:
            if isinstance(node, ast.If) and 'main' in ast.unparse(node.test):
                continue
            code = compile(ast.Module(body=[node], type_ignores=[]), str(src), 'exec')
            exec(code, ns)
            if isinstance(node, ast.FunctionDef):
                snap = dict(ns)
                f = ns[node.name]
                ns[node.name] = types.FunctionType(f.__code__, snap, f.__name__, f.__defaults__, f.__closure__)
                snap[node.name] = ns[node.name]
                self._spaces.append(snap)
        self.__dict__['__file__'] = str(src)

    def __getattr__(self, name):
        return self._ns[name]

    def __setattr__(self, name, value):
        """Mengganti nilai (BBPORT, read, write, titik sisip) di semua salinan globals."""
        self._ns[name] = value
        for snap in self._spaces:
            if name in snap or name in ('BBPORT', 'PROJECT', 'read', 'write'):
                snap[name] = value


def load_linux_patch():
    src = HERE / 'order_patch.py'
    if not src.is_file():
        src = HERE.parent / 'order_patch.py'
    return Linux(src)


m = load_linux_patch()


def read(path):
    raw = path.read_bytes().decode('utf-8')
    read.crlf[str(path)] = '\r\n' in raw
    return raw.replace('\r\n', '\n')


read.crlf = {}


def write(path, text):
    if read.crlf.get(str(path), False):
        text = text.replace('\n', '\r\n')
    path.write_bytes(text.encode('utf-8'))


m.read, m.write = read, write

# ---------------------------------------------------------------------------------------------
# Titik sisip pohon Windows
# 7: tekstur divalidasi lewat IsBindableFormat (SacredFire), bukan IsKnownFormat langsung.
m.TILE_OLD = '!IsBindableFormat(data_fmt, num_fmt)) {'
m.TILE_NEW = '!IsBindableFormat(data_fmt, num_fmt) || !IsKnownTileMode(tsharp.GetTileMode())) {'


def runtime_kernel_win():
    """2. Stub The Order di runtime_kernel.c pohon Windows (hanya yang belum ada di pohon ini)."""
    path = m.BBPORT / 'src' / 'runtime_kernel.c'
    text = read(path)
    if m.MARK in text:
        print('2. runtime_kernel.c: sudah dipatch')
        return
    anchor_fn = '/* ---- bbport-dmc: DmC Definitive Edition (Unreal Engine 3) ---- */\n'
    anchor_tab = '    /* ---- bbport-dmc ---- */\n'
    if text.count(anchor_fn) != 1 or text.count(anchor_tab) != 1:
        sys.exit('runtime_kernel.c (Windows): titik sisip bbport-dmc tidak ditemukan')
    every = text
    for other in ('runtime_services.c', 'runtime_savedata.c', 'runtime.c', 'runtime_file.c'):
        p = m.BBPORT / 'src' / other
        if p.is_file():
            every += p.read_text(encoding='utf-8', errors='replace')
    rows = []
    for line in m.TABLE.splitlines():
        if not line.strip().startswith('{'):
            rows.append(line)
            continue
        keep = []
        for cell in line.strip().split('}, '):
            cell = cell.strip().rstrip(',').rstrip('}')
            name = cell.split(',')[0].strip().strip('{').strip('"')
            if f'"{name}"' not in every:
                keep.append('{' + cell.lstrip('{') + '}')
        if keep:
            rows.append('    ' + ', '.join(keep) + ',')
    if '#include <time.h>' not in text:
        text = '#include <time.h>\n' + text
    text = text.replace(anchor_fn, m.FUNCTIONS.lstrip('\n') + anchor_fn, 1)
    text = text.replace(anchor_tab, anchor_tab + '\n'.join(rows) + '\n', 1)
    write(path, text)
    print('2. runtime_kernel.c (Windows): stub The Order ditambahkan (yang belum ada)')


def draw_log_win():
    """90. Perekam draw (BB_ORDER_DRAWLOG) tanpa saklar bagian 89 (89 tidak dipasang di Windows)."""
    rz = m.BBPORT / 'gpu' / 'shadps4' / 'video_core' / 'renderer_vulkan' / 'vk_rasterizer.cpp'
    rt = read(rz)
    if 'bbport-order (90)' in rt:
        print('90. rekam draw 16 frame (BB_ORDER_DRAWLOG): sudah dipatch')
        return
    for name, old in (('helper', m.DL_HELPER_ANCHOR), ('draw', m.DLD_OLD), ('indirect', m.DLI_OLD)):
        if rt.count(old) != 1:
            sys.exit('bagian 90 (Windows): titik sisip %s tidak ditemukan' % name)
    rt = (rt.replace(m.DL_HELPER_ANCHOR, m.DL_HELPER + m.DL_HELPER_ANCHOR, 1)
          .replace(m.DLD_OLD, m.DLD_NEW, 1).replace(m.DLI_OLD, m.DLI_NEW, 1))
    write(rz, rt)
    print('90. rekam draw 16 frame (BB_ORDER_DRAWLOG=file)')


def info_recover_win():
    # Section 97 declares sigjmp_buf itself via <setjmp.h>; Windows has no sigsetjmp, so use
    # bbport_toggles.h, which maps sigsetjmp to bb_setjmp (the loader's exception handler).
    path = m.BBPORT / 'gpu/shadps4/shader_recompiler/info.h'
    text = read(path)
    old = '#include <setjmp.h>\nextern "C" __thread sigjmp_buf* runtime_fault_recover;\n'
    new = '#include "bbport_toggles.h" // bbport-order-win (97)\n'
    if new in text:
        return
    if old not in text:
        sys.exit('info.h: anchor section 97 tidak ditemukan')
    write(path, text.replace(old, new, 1))
    print('ok info_recover_win')


def dlss_hook_win():
    # Section 75 (BB_ORDER_TAA_HOOK=dlss) uses the Linux DLSS class (Dlss, dlss_failed). The Windows
    # tree has DlssNgx with a different API: the hook falls back to FSR 3.1 here.
    path = m.BBPORT / 'gpu/shadps4/video_core/renderer_vulkan/vk_temporal_upscaler.cpp'
    text = read(path)
    if 'bbport-order-win (75)' in text:
        return
    a_old = ('            const Dlss* dlss = Dlss::Get();\n'
             '            if (!dlss || !dlss->Available()) {\n'
             '                std::printf("bbport-order (75): DLSS tidak tersedia (%s): FSR 3.1 dipakai\\n",\n'
             '                            dlss ? dlss->Problem().c_str() : "bridge atau library NVIDIA tidak ada");\n'
             '                order_mode = 1;\n'
             '            }\n')
    a_new = ('            // bbport-order-win (75): hook DLSS belum ada di Windows\n'
             '            std::printf("bbport-order (75): DLSS belum didukung di Windows: FSR 3.1 dipakai\\n");\n'
             '            order_mode = 1;\n')
    b_old = '    if (order_mode == 2 && dlss_failed) {\n'
    b_new = '    if (order_mode == 2) {\n'
    start = text.find('    if (order_mode == 2) {\n        Dlss* dlss = Dlss::Get();\n')
    end = text.find('    } else if (context) {\n', start)
    if a_old not in text or b_old not in text or start < 0 or end < 0:
        sys.exit('vk_temporal_upscaler.cpp: anchor section 75 tidak ditemukan')
    text = text.replace(a_old, a_new, 1).replace(b_old, b_new, 1)
    start = text.find('    if (order_mode == 2) {\n        Dlss* dlss = Dlss::Get();\n')
    end = text.find('    } else if (context) {\n', start)
    text = text[:start] + '    if (context) {\n' + text[end + len('    } else if (context) {\n'):]
    write(path, text)
    print('ok dlss_hook_win')


def vb_paged_note_win():
    # Diagnostic note (BB_ORDER_DIAG): the paged buffer layer does not exist in the Windows tree.
    path = m.BBPORT / 'gpu/shadps4/video_core/renderer_vulkan/vk_rasterizer.cpp'
    text = read(path)
    old = ('int(Shader::IsPagedBuffer(\n'
           '                                      VideoCore::BufferCache::LayerPagedActive(), vsharp)),\n')
    new = '0 /* bbport-order-win: paged */,\n'
    if new in text:
        return
    if old not in text:
        sys.exit('vk_rasterizer.cpp: anchor IsPagedBuffer tidak ditemukan')
    write(path, text.replace(old, new, 1))
    print('ok vb_paged_note_win')


def unused_stubs_win():
    # Stubs whose table rows were left out (the Windows tree already exports those names) are unused:
    # -Werror=unused-function. Mark them unused instead of removing them.
    import re
    path = m.BBPORT / 'src' / 'runtime_kernel.c'
    text = read(path)
    changed = []
    for name in re.findall(r'^static ABI [\w\s\*]+?\b(order_\w+)\(', text, re.M):
        if len(re.findall(r'\b' + name + r'\b', text)) == 1:
            text = re.sub(r'^static ABI ([\w\s\*]+?\b' + name + r'\()',
                          r'static __attribute__((unused)) ABI \1', text, count=1, flags=re.M)
            changed.append(name)
    if changed:
        write(path, text)
        print('ok unused_stubs_win: ' + ' '.join(changed))


def order_icon(path):
    """256x256 ICO (PNG inside): dark rounded square, bronze play triangle. No game artwork."""
    import struct
    import zlib
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


def branding_win():
    """Visible SacredFire/CTR branding -> The Order: 1886 (menu title, window title, exe icon,
    crash notice). Credits stay: LICENSE, copyright headers, README/SOURCE.txt of the package."""
    edits = [
        ('gpu/shim/bbport_overlay.cpp',
         '"SacredFire  (Insert / L3+R3)###bbport_settings"',
         '"The Order: 1886 PC  (Insert / L3+R3)###bbport_settings"', 2),
        ('gpu/shim/bbgpu.cpp', 'config->title : "SacredFire";', 'config->title : "The Order: 1886";', 1),
        ('gpu/shim/bbport_clobber.cpp',
         '"\\nSacredFire issue #2: the known \\"clobbered dword\\" bug',
         '"\\nPort issue (clobbered dword): the known \\"clobbered dword\\" bug', 1),
        ('gpu/shim/bbport_clobber.cpp',
         '"SacredFire issue #2: please attach this whole log to "\n'
         '                 "https://github.com/T3CHNOLOG1C/SacredFire/issues/2 (launcher: Log page, \\"Export "\n'
         '                 "log...\\") so that the writer can be found and fixed.\\n\\n"',
         '"Port issue (clobbered dword): please keep this whole log (launcher: Log) "\n'
         '                 "so that the writer can be found and fixed.\\n\\n"', 1),
        ('src/vulkan_smoke.c', '"SacredFire native probe"', '"The Order 1886 native port"', 1),
        ('packaging/windows/sacredfire.rc', '1 ICON "icons/ctr.ico"', '1 ICON "icons/order1886.ico"', 1),
        ('packaging/windows/sacredfire.manifest', 'name="sacredfire.sacredfire"', 'name="order1886.port"', 1),
    ]
    done = 0
    for rel, old, new, count in edits:
        path = m.BBPORT / rel
        text = read(path)
        if new in text:
            continue
        if text.count(old) != count:
            sys.exit(f'{rel}: anchor branding tidak ditemukan ({old[:50]})')
        write(path, text.replace(old, new))
        done += 1
    ico = m.BBPORT / 'packaging/windows/icons/order1886.ico'
    if not ico.is_file():
        order_icon(ico)
        done += 1
    if done:
        print(f'ok branding_win ({done} perubahan)')


SKIP = {
    'import_names',   # pohon Windows menamai import saat persiapan (tools/gen_import_names.py)
    'runtime_pad',    # statistik heap Bloodborne tidak ada di pohon Windows
    'unaligned_buffers',     # 89: bawaan mati di Linux (tidak relevan), emitter berbeda di Windows
    'fault_dump_generated',  # 96: diagnosa handler Linux; probe.c Windows punya handler sendiri
}
REPLACE = {
    'runtime_kernel': runtime_kernel_win,
    'draw_log': draw_log_win,
}


def main():
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    tree = Path(sys.argv[1]).resolve()
    if not (tree / 'src' / 'probe.c').is_file() or not (tree / 'gpu').is_dir():
        sys.exit(f'{tree}: bukan pohon port (src/probe.c, gpu/)')
    m.BBPORT = tree
    m.PROJECT = tree.parent
    src = Path(m.__file__).read_text(encoding='utf-8')
    order = src[src.index("if __name__ == '__main__':"):]
    import re
    calls = re.findall(r'^    (\w+)\(\)$', order, re.M)
    for name in calls:
        if name in SKIP:
            print(f'-- {name}: dilewati di Windows')
            continue
        REPLACE.get(name, getattr(m, name))()
    info_recover_win()
    dlss_hook_win()
    vb_paged_note_win()
    unused_stubs_win()
    branding_win()
    print('Selesai (Windows). Build ulang: bash build.sh di MSYS2 CLANG64.')


if __name__ == '__main__':
    main()
