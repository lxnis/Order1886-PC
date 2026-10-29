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


def srt_no_patch_win():
    """107 (Windows): the SRT walker fault handler of shadPS4 patches the shared Xbyak walker code in
    place (mov -> xor) while the Fast mode's 3 recording threads may be running the same code. On
    Windows the walker faults hundreds of times per session (Linux: never), and the game hung with the
    GPU thread silent (28 Oct, Galahad's jump; 19 Oct, loading a later save). When the thread has a
    recovery point (section 97 / draw-prep worker), let the fault fall through to it instead: probe.c
    then bb_longjmps that thread back and the walker result is 0, without touching shared code."""
    path = m.BBPORT / 'gpu/shadps4/shader_recompiler/ir/passes/flatten_extended_userdata_pass.cpp'
    text = read(path)
    mark = 'bbport-order-win (107)'
    if mark in text:
        print('-- srt_no_patch_win: sudah')
        return
    anchor = ('    if (code < code_start || code >= code_end) {\n'
              '        return false; // Not in SRT code range\n'
              '    }\n')
    if text.count(anchor) != 1:
        sys.exit('flatten_extended_userdata_pass.cpp: anchor SrtWalkerSignalHandler (107) tidak ditemukan')
    add = ('    if (runtime_fault_recover != nullptr) { // ' + mark + ': recover this thread (bb_longjmp)\n'
           '        return false;                       // instead of patching the shared walker code\n'
           '    }\n')
    write(path, text.replace(anchor, anchor + add, 1))
    print('ok srt_no_patch_win (107)')


def gpu_stall_win():
    """108 (Windows): the game froze at Galahad's jump with the GPU command thread spinning in
    Liverpool::Process (dump of 28 Oct: thread 3824 at 100% CPU in the decode loop, 4 guest threads
    spinning, every other thread asleep): a GPU wait that is never met (WaitRegMem, MemSemaphore or
    Rewind). Log which wait and its packet, and go on after BB_ORDER_STALL_MS (default 4000 ms,
    0 = wait forever as before). Rewind waits are only logged."""
    path = m.BBPORT / 'gpu/shadps4/video_core/amdgpu/liverpool.cpp'
    text = read(path)
    mark = 'bbport-order-win (108)'
    if mark in text:
        print('-- gpu_stall_win: sudah')
        return
    helper = (
        '\n'
        '// ' + mark + ': a GPU wait that is never met froze the game (Galahad\'s jump): log it and go\n'
        '// on after BB_ORDER_STALL_MS (default 4000, 0 = wait forever).\n'
        '#include <atomic>\n'
        '#include <cstdlib>\n'
        'static bool BbOrderStall(u64& t0, const char* what, const void* pkt, const volatile u32* mem) {\n'
        '    const u64 now = u64(std::chrono::duration_cast<std::chrono::milliseconds>(\n'
        '                            std::chrono::steady_clock::now().time_since_epoch())\n'
        '                            .count());\n'
        '    if (t0 == 0) {\n'
        '        t0 = now;\n'
        '        return false;\n'
        '    }\n'
        '    static const u64 limit = [] {\n'
        '        const char* e = std::getenv("BB_ORDER_STALL_MS");\n'
        '        return e && *e ? u64(std::strtoull(e, nullptr, 10)) : u64(4000);\n'
        '    }();\n'
        '    if (limit == 0 || now - t0 < limit) {\n'
        '        return false;\n'
        '    }\n'
        '    static std::atomic<u32> told{0};\n'
        '    if (told.fetch_add(1) < 64) {\n'
        '        const u32* p = static_cast<const u32*>(pkt);\n'
        '        std::fprintf(stderr,\n'
        '                     "bbport-order (108): GPU menunggu %s %llu ms -> dilewati; paket %08x %08x "\n'
        '                     "%08x %08x %08x %08x %08x",\n'
        '                     what, (unsigned long long)(now - t0), p[0], p[1], p[2], p[3], p[4], p[5],\n'
        '                     p[6]);\n'
        '        if (mem != nullptr) {\n'
        '            std::fprintf(stderr, "; nilai di alamat %08x", *mem);\n'
        '        }\n'
        '        std::fprintf(stderr, "\\n");\n'
        '        std::fflush(stderr);\n'
        '    }\n'
        '    t0 = 0;\n'
        '    return true;\n'
        '}\n'
        '#define BB_ORDER_WRM_MEM(w)                                                                  \\\n'
        '    ((w)->mem_space.Value() == PM4CmdWaitRegMem::MemSpace::Memory                             \\\n'
        '         ? (w)->Address<const volatile u32*>()                                                \\\n'
        '         : nullptr)\n')
    anchor = '#define YIELD_ASC(id) YIELD(acb_task_name[id])\n'
    edits = [
        (anchor, anchor + helper),
        # GFX WaitRegMem
        ('                while (!wait_reg_mem->Test(regs.reg_array)) {\n'
         '                    if (rasterizer && !rasterizer->DrawPipeIdle()) {\n',
         '                u64 bb_stall = 0;\n'
         '                while (!wait_reg_mem->Test(regs.reg_array)) {\n'
         '                    if (BbOrderStall(bb_stall, "WaitRegMem gfx", header,\n'
         '                                     BB_ORDER_WRM_MEM(wait_reg_mem))) {\n'
         '                        break;\n'
         '                    }\n'
         '                    if (rasterizer && !rasterizer->DrawPipeIdle()) {\n'),
        # ASC WaitRegMem
        ('            while (!wait_reg_mem->Test(regs.reg_array)) {\n'
         '                // BB_HONEST_LABELS: the value may come from a fence waiting for work not\n',
         '            u64 bb_stall = 0;\n'
         '            while (!wait_reg_mem->Test(regs.reg_array)) {\n'
         '                if (BbOrderStall(bb_stall, "WaitRegMem asc", header,\n'
         '                                 BB_ORDER_WRM_MEM(wait_reg_mem))) {\n'
         '                    break;\n'
         '                }\n'
         '                // BB_HONEST_LABELS: the value may come from a fence waiting for work not\n'),
        # MemSemaphore GFX / ASC
        ('                    while (!mem_semaphore->Signaled()) {\n'
         '                        YIELD_GFX();\n',
         '                    u64 bb_stall = 0;\n'
         '                    while (!mem_semaphore->Signaled()) {\n'
         '                        if (BbOrderStall(bb_stall, "MemSemaphore gfx", header, nullptr)) {\n'
         '                            break;\n'
         '                        }\n'
         '                        YIELD_GFX();\n'),
        ('                while (!mem_semaphore->Signaled()) {\n'
         '                    YIELD_ASC(vqid);\n',
         '                u64 bb_stall = 0;\n'
         '                while (!mem_semaphore->Signaled()) {\n'
         '                    if (BbOrderStall(bb_stall, "MemSemaphore asc", header, nullptr)) {\n'
         '                        break;\n'
         '                    }\n'
         '                    YIELD_ASC(vqid);\n'),
        # Rewind GFX / ASC: log only
        ('                while (!rewind->Valid()) {\n'
         '                    YIELD_GFX();\n',
         '                u64 bb_stall = 0;\n'
         '                while (!rewind->Valid()) {\n'
         '                    (void)BbOrderStall(bb_stall, "Rewind gfx (hanya log)", header, nullptr);\n'
         '                    YIELD_GFX();\n'),
        ('            while (!rewind->Valid()) {\n'
         '                YIELD_ASC(vqid);\n',
         '            u64 bb_stall = 0;\n'
         '            while (!rewind->Valid()) {\n'
         '                (void)BbOrderStall(bb_stall, "Rewind asc (hanya log)", header, nullptr);\n'
         '                YIELD_ASC(vqid);\n'),
    ]
    for old, new in edits:
        if text.count(old) != 1:
            sys.exit('liverpool.cpp: anchor (108) tidak ditemukan/tidak unik (%d):\n%s' % (text.count(old), old))
        text = text.replace(old, new, 1)
    write(path, text)
    print('ok gpu_stall_win (108)')


def asc_trace_win():
    """109 (Windows): after 108 the black screen on loading a Chapter I save was a compute queue stuck
    on a Rewind packet whose valid bit never came (the dispatch after it still held the placeholder
    sizes aaaaaaaa/bbbbbbbb/cccccccc; later the same memory held other data). To tell a stale decode
    (a ring read past what was submitted) from a guest that never patched: remember the last compute
    submissions and, when a Rewind waits 4 s, log its address and those submissions."""
    path = m.BBPORT / 'gpu/shadps4/video_core/amdgpu/liverpool.cpp'
    text = read(path)
    mark = 'bbport-order-win (109)'
    if mark in text:
        print('-- asc_trace_win: sudah')
        return
    if 'bbport-order-win (108)' not in text:
        sys.exit('liverpool.cpp: 108 belum terpasang (gpu_stall_win dulu)')
    helper_anchor = '#define BB_ORDER_WRM_MEM(w)'
    helper = (
        '// ' + mark + ': the last compute submissions, logged when a Rewind waits too long.\n'
        'struct BbOrderAscSub {\n'
        '    u32 vqid;\n'
        '    const u32* data;\n'
        '    u32 dwords;\n'
        '    u64 ms;\n'
        '};\n'
        'static std::array<BbOrderAscSub, 32> bb_order_asc_subs{};\n'
        'static std::atomic<u32> bb_order_asc_next{0};\n'
        'static u64 BbOrderNowMs() {\n'
        '    return u64(std::chrono::duration_cast<std::chrono::milliseconds>(\n'
        '                   std::chrono::steady_clock::now().time_since_epoch())\n'
        '                   .count());\n'
        '}\n'
        'static void BbOrderAscNote(u32 vqid, std::span<const u32> acb) {\n'
        '    const u32 i = bb_order_asc_next.fetch_add(1) % bb_order_asc_subs.size();\n'
        '    bb_order_asc_subs[i] = {vqid, acb.data(), u32(acb.size()), BbOrderNowMs()};\n'
        '}\n'
        'static void BbOrderAscDump(const void* pkt) {\n'
        '    static std::atomic<u32> told{0};\n'
        '    if (told.fetch_add(1) >= 4) {\n'
        '        return;\n'
        '    }\n'
        '    const u64 now = BbOrderNowMs();\n'
        '    const auto at = reinterpret_cast<uintptr_t>(pkt);\n'
        '    std::fprintf(stderr, "bbport-order (109): Rewind macet di %p; kiriman compute terakhir:\\n", pkt);\n'
        '    const u32 n = bb_order_asc_next.load();\n'
        '    for (u32 k = 0; k < bb_order_asc_subs.size() && k < n; ++k) {\n'
        '        const auto& e = bb_order_asc_subs[(n - 1 - k) % bb_order_asc_subs.size()];\n'
        '        const auto b = reinterpret_cast<uintptr_t>(e.data), end = b + e.dwords * 4ull;\n'
        '        std::fprintf(stderr, "  vq %u  %p..%p  %u dword  %llu ms lalu%s\\n", e.vqid, (const void*)b,\n'
        '                     (const void*)end, e.dwords, (unsigned long long)(now - e.ms),\n'
        '                     at >= b && at < end ? "  <== berisi Rewind" : "");\n'
        '    }\n'
        '    std::fflush(stderr);\n'
        '}\n')
    edits = [
        (helper_anchor, helper + helper_anchor),
        ('                (void)BbOrderStall(bb_stall, "Rewind asc (hanya log)", header, nullptr);\n',
         '                if (BbOrderStall(bb_stall, "Rewind asc (hanya log)", header, nullptr)) {\n'
         '                    BbOrderAscDump(header);\n'
         '                }\n'),
        ('    const auto vqid = gnm_vqid - 1;\n    const auto& task = ProcessCompute(acb, vqid);\n',
         '    const auto vqid = gnm_vqid - 1;\n    BbOrderAscNote(gnm_vqid, acb);\n'
         '    const auto& task = ProcessCompute(acb, vqid);\n'),
    ]
    for old, new in edits:
        if text.count(old) != 1:
            sys.exit('liverpool.cpp: anchor (109) tidak ditemukan/tidak unik (%d):\n%s' % (text.count(old), old))
        text = text.replace(old, new, 1)
    write(path, text)
    print('ok asc_trace_win (109)')


def rewind_ctx_win():
    """110 (Windows): 109 showed the stuck Rewind (0x106EA85F8C) is not in any ring submission: it is
    inside an indirect buffer the compute queue reached. Log, with each Rewind stall report, the
    queue, how much of that buffer is left, and the dwords around the packet (32 before, 16 after),
    to see whether the packets before it were patched by the game and whether it is past the end of
    what the game meant to submit."""
    path = m.BBPORT / 'gpu/shadps4/video_core/amdgpu/liverpool.cpp'
    text = read(path)
    mark = 'bbport-order-win (110)'
    if mark in text:
        print('-- rewind_ctx_win: sudah')
        return
    if 'bbport-order-win (109)' not in text:
        sys.exit('liverpool.cpp: 109 belum terpasang (asc_trace_win dulu)')
    helper_anchor = '#define BB_ORDER_WRM_MEM(w)'
    helper = (
        '// ' + mark + ': the memory around a stuck Rewind and what is left of its buffer.\n'
        'static void BbOrderRewindCtx(const void* pkt, std::span<const u32> rest, u32 vqid) {\n'
        '    static std::atomic<u32> told{0};\n'
        '    if (told.fetch_add(1) >= 3) {\n'
        '        return;\n'
        '    }\n'
        '    const u32* p = static_cast<const u32*>(pkt);\n'
        '    std::fprintf(stderr, "bbport-order (110): Rewind vq %u di %p, sisa buffer %zu dword (%p..%p)\\n",\n'
        '                 vqid + 1, pkt, rest.size(), (const void*)rest.data(),\n'
        '                 (const void*)(rest.data() + rest.size()));\n'
        '    for (int row = -32; row < 16; row += 8) {\n'
        '        std::fprintf(stderr, "  %+4d:", row);\n'
        '        for (int k = 0; k < 8; ++k) {\n'
        '            std::fprintf(stderr, " %08x", p[row + k]);\n'
        '        }\n'
        '        std::fprintf(stderr, "\\n");\n'
        '    }\n'
        '    std::fflush(stderr);\n'
        '}\n')
    edits = [
        (helper_anchor, helper + helper_anchor),
        ('                    BbOrderAscDump(header);\n',
         '                    BbOrderAscDump(header);\n'
         '                    BbOrderRewindCtx(header, acb, vqid);\n'),
    ]
    for old, new in edits:
        if text.count(old) != 1:
            sys.exit('liverpool.cpp: anchor (110) tidak ditemukan/tidak unik (%d):\n%s' % (text.count(old), old))
        text = text.replace(old, new, 1)
    write(path, text)
    print('ok rewind_ctx_win (110)')


def dma_self_patch_win():
    """111 (Windows): the cause of the hang at Galahad's jump and of the black screen on loading.
    The game patches its own compute command buffer from the GPU: DMA_DATA copies the dispatch sizes
    in, then DMA_DATA writes 0x80000000 (the valid bit) into the REWIND packet right after it, and
    the REWIND waits for that bit (110: IB 0x106EA85F8C, DMA dst 0x106ea85f90, data 0x80000000).
    shadPS4 turns a DMA_DATA "data -> memory" into a GPU buffer fill, which does not reach the guest
    memory the command processor reads, so the REWIND waited forever. When the destination lies in
    the command buffer being decoded, write it to guest memory on the CPU (in stream order)."""
    path = m.BBPORT / 'gpu/shadps4/video_core/amdgpu/liverpool.cpp'
    text = read(path)
    mark = 'bbport-order-win (111)'
    if mark in text:
        print('-- dma_self_patch_win: sudah')
        return
    old = ('            } else if (dma_data->src_sel == DmaDataSrc::Data &&\n'
           '                       (dma_data->dst_sel == DmaDataDst::Memory ||\n'
           '                        dma_data->dst_sel == DmaDataDst::MemoryUsingL2)) {\n'
           '                rasterizer->FillBuffer(dma_data->DstAddress<VAddr>(), dma_data->NumBytes(),\n'
           '                                       dma_data->data, false);\n')
    new = ('            } else if (dma_data->src_sel == DmaDataSrc::Data &&\n'
           '                       (dma_data->dst_sel == DmaDataDst::Memory ||\n'
           '                        dma_data->dst_sel == DmaDataDst::MemoryUsingL2)) {\n'
           '                // ' + mark + ': a write into the command buffer being decoded (the\n'
           '                // valid bit of a REWIND) must reach guest memory, which this thread reads.\n'
           '                const VAddr bb_dst = dma_data->DstAddress<VAddr>();\n'
           '                const u32 bb_bytes = dma_data->NumBytes();\n'
           '                if (bb_dst >= base_addr && bb_dst + bb_bytes <= base_addr + acb_size) {\n'
           '                    static std::atomic<u32> bb_told{0};\n'
           '                    if (bb_told.fetch_add(1) == 0) {\n'
           '                        std::fprintf(stderr, "bbport-order (111): DMA_DATA ke command buffer "\n'
           '                                     "compute (%#llx, %u byte, %08x) ditulis langsung\\n",\n'
           '                                     (unsigned long long)bb_dst, bb_bytes, dma_data->data);\n'
           '                        std::fflush(stderr);\n'
           '                    }\n'
           '                    for (u32 i = 0; i < bb_bytes / 4; ++i) {\n'
           '                        reinterpret_cast<volatile u32*>(bb_dst)[i] = dma_data->data;\n'
           '                    }\n'
           '                } else {\n'
           '                    rasterizer->FillBuffer(bb_dst, bb_bytes, dma_data->data, false);\n'
           '                }\n')
    if text.count(old) != 1:
        sys.exit('liverpool.cpp: anchor DMA_DATA compute (111) tidak ditemukan/tidak unik (%d)' % text.count(old))
    write(path, text.replace(old, new, 1))
    print('ok dma_self_patch_win (111)')


def host_priority_win():
    """112 (Windows): low FPS (34-38 in Chapter I; Linux 60 on the same PC). Draw pipe stage B
    costs ~20 us per draw on Windows against ~5 us on Linux (frame stats, 18 Oct Linux logs), and
    the profile shows it waiting in std::this_thread::yield (WaitHostCopies, WaitDeferredSignals)
    for the Vulkan recording threads, with the game's 4 "Task Kernel" workers spinning at ~76% of a
    core each. On Windows a yield hands the core to any ready thread of the same priority, and a
    woken thread waits behind them: the port's own threads lose their turn to the game's spinning
    workers. Run the GPU command thread, stage B, the Vulkan recorders and the copy threads above
    normal priority. BB_ORDER_HOST_PRIORITY: 0 off, 1 above normal (default), 2 highest."""
    base = m.BBPORT / 'gpu'
    mark = 'bbport-order-win (112)'
    th = base / 'shim/bbport_threads.h'
    text = read(th)
    if mark in text:
        print('-- host_priority_win: sudah')
        return
    old_win = ('/// The calling thread only runs when cores are otherwise idle (lowest Windows priority).\n'
               'inline void MakeBackground() {\n'
               '    SetThreadPriority(GetCurrentThread(), THREAD_PRIORITY_IDLE);\n'
               '}\n')
    new_win = old_win + (
        '\n'
        '/// ' + mark + ': the port\'s own threads (GPU command thread, draw pipe stage B, Vulkan\n'
        '/// recorders, copy threads) above the game\'s spinning workers: a yield or a wake-up does not\n'
        '/// wait behind them. BB_ORDER_HOST_PRIORITY: 0 off, 1 above normal (default), 2 highest.\n'
        'inline int HostPriorityLevel() {\n'
        '    static const int level = [] {\n'
        '        const char* env = std::getenv("BB_ORDER_HOST_PRIORITY");\n'
        '        return env && *env ? std::atoi(env) : 1;\n'
        '    }();\n'
        '    return level;\n'
        '}\n'
        'inline void RaiseHostPriority() {\n'
        '    const int level = HostPriorityLevel();\n'
        '    if (level >= 2) {\n'
        '        SetThreadPriority(GetCurrentThread(), THREAD_PRIORITY_HIGHEST);\n'
        '    } else if (level == 1) {\n'
        '        SetThreadPriority(GetCurrentThread(), THREAD_PRIORITY_ABOVE_NORMAL);\n'
        '    }\n'
        '}\n')
    old_lin = ('/// The calling thread only runs on otherwise idle cores (falls back to the lowest nice level).\n'
               'inline void MakeBackground() {\n')
    new_lin = ('inline int HostPriorityLevel() { return 0; }\n'
               'inline void RaiseHostPriority() {} // ' + mark + ': Windows only\n\n' + old_lin)
    old_inc = '#include <algorithm>\n#include <thread>\n'
    new_inc = '#include <algorithm>\n#include <cstdlib>\n#include <thread>\n'
    for old, new in ((old_win, new_win), (old_lin, new_lin), (old_inc, new_inc)):
        if text.count(old) != 1:
            sys.exit('bbport_threads.h: anchor (112) tidak ditemukan/tidak unik (%d):\n%s' % (text.count(old), old))
        text = text.replace(old, new, 1)
    write(th, text)

    calls = [
        ('shadps4/video_core/amdgpu/liverpool.cpp',
         '    Common::SetCurrentThreadName("shadPS4:GpuCommandProcessor");\n',
         '    Common::SetCurrentThreadName("shadPS4:GpuCommandProcessor");\n'
         '    BbThreads::RaiseHostPriority(); // ' + mark + '\n'
         '    std::fprintf(stderr, "bbport-order (112): prioritas thread port = %d (BB_ORDER_HOST_PRIORITY)\\n",\n'
         '                 BbThreads::HostPriorityLevel());\n'),
        ('shadps4/video_core/renderer_vulkan/vk_scheduler.cpp',
         '    Worker& worker = *workers[index];\n',
         '    Worker& worker = *workers[index];\n'
         '    BbThreads::RaiseHostPriority(); // ' + mark + '\n'),
        ('shadps4/video_core/renderer_vulkan/vk_draw_pipe.h',
         '        Common::SetCurrentThreadName("bb:DrawRec");\n',
         '        Common::SetCurrentThreadName("bb:DrawRec");\n'
         '        BbThreads::RaiseHostPriority(); // ' + mark + '\n'),
        ('shim/bbport_copy.cpp',
         '        Common::SetCurrentThreadName(("bb:Copy" + std::to_string(index)).c_str());\n',
         '        Common::SetCurrentThreadName(("bb:Copy" + std::to_string(index)).c_str());\n'
         '        BbThreads::RaiseHostPriority(); // ' + mark + '\n'),
    ]
    for rel, old, new in calls:
        path = base / rel
        t = read(path)
        if t.count(old) != 1:
            sys.exit('%s: anchor (112) tidak ditemukan/tidak unik (%d)' % (rel, t.count(old)))
        write(path, t.replace(old, new, 1))
    print('ok host_priority_win (112)')


def task_kernel_sleep_win():
    """113 (Windows): section 74 (BB_ORDER_YIELD_US, launcher default 50) never worked on Windows.
    winpthreads' nanosleep rounds to whole milliseconds, so a 50 us (or 500 us) nap is Sleep(0):
    the game's 4 "Task Kernel" workers kept spinning at ~76% of a core each (28 Oct profile) and
    took the hyperthread siblings of the port's GPU threads on a 4-core/8-thread CPU, the problem
    section 74 fixed on Linux (i3-12100F: 2K ~50 -> 58-60 FPS). Sleep on a high-resolution waitable
    timer (Windows 10 1803+), else Sleep(1). The thread is recognised by the runtime's own name
    instead of pthread_getname_np."""
    path = m.BBPORT / 'src' / 'runtime_thread.c'
    text = read(path)
    mark = 'bbport-order-win (113)'
    if mark in text:
        print('-- task_kernel_sleep_win: sudah')
        return
    old_name = ('        char name[32] = {0};\n'
                '        pthread_getname_np(pthread_self(), name, sizeof name);\n'
                '        task_kernel = strncmp(name, "Task Kernel", 11) == 0;\n')
    new_name = ('        const char *name = runtime_thread_current_name(); /* ' + mark + ' */\n'
                '        task_kernel = name && strncmp(name, "Task Kernel", 11) == 0;\n')
    old_sleep = ('    if (sleep_us > 0 && task_kernel) {\n'
                 '        struct timespec ts = {0, (long)sleep_us * 1000L};\n'
                 '        nanosleep(&ts, NULL);\n')
    new_sleep = ('    if (sleep_us > 0 && task_kernel) {\n'
                 '        bb_order_sleep_us(sleep_us); /* ' + mark + ' */\n')
    anchor = 'static ABI int32_t thread_yield(void) { /* bbport-order (74) */\n'
    helper = ('/* ' + mark + ': winpthreads\' nanosleep sleeps whole milliseconds (50 us -> Sleep(0), a\n'
              '   spin). A high-resolution waitable timer sleeps microseconds (Windows 10 1803+). */\n'
              '#ifdef _WIN32\n'
              'static void bb_order_sleep_us(int us) {\n'
              '    static __thread HANDLE timer;\n'
              '    static __thread int tried;\n'
              '    static int told;\n'
              '    if (!tried) {\n'
              '        tried = 1;\n'
              '        timer = CreateWaitableTimerExW(NULL, NULL, 0x00000002 /* HIGH_RESOLUTION */,\n'
              '                                       TIMER_ALL_ACCESS);\n'
              '        if (!__atomic_exchange_n(&told, 1, __ATOMIC_RELAXED)) {\n'
              '            fprintf(stderr, "bbport-order (113): Task Kernel tidur %d us lewat %s\\n", us,\n'
              '                    timer ? "timer resolusi tinggi" : "Sleep(1)");\n'
              '        }\n'
              '    }\n'
              '    if (timer) {\n'
              '        LARGE_INTEGER due;\n'
              '        due.QuadPart = -(LONGLONG)us * 10; /* 100 ns units, relative */\n'
              '        if (SetWaitableTimer(timer, &due, 0, NULL, NULL, FALSE)) {\n'
              '            WaitForSingleObject(timer, INFINITE);\n'
              '            return;\n'
              '        }\n'
              '    }\n'
              '    Sleep(1);\n'
              '}\n'
              '#else\n'
              'static void bb_order_sleep_us(int us) {\n'
              '    struct timespec ts = {0, (long)us * 1000L};\n'
              '    nanosleep(&ts, NULL);\n'
              '}\n'
              '#endif\n')
    for old, new in ((old_name, new_name), (old_sleep, new_sleep), (anchor, helper + anchor)):
        if text.count(old) != 1:
            sys.exit('runtime_thread.c: anchor (113) tidak ditemukan/tidak unik (%d):\n%s' % (text.count(old), old))
        text = text.replace(old, new, 1)
    write(path, text)
    print('ok task_kernel_sleep_win (113)')


def compute_pipe_win():
    """114 (Windows): low FPS in heavy scenes. Frame stats: draw pipe stage A waits 69-75% of the
    time, 50-56% of it in graphics WAIT_REG_MEM drains and the rest mostly in the drain before every
    compute packet (4400 drains/s). The same remedy as TOport's BB_COMPUTE_PIPE (IgorAugustoHH/
    The-Order-1886-PC-Port, GPL-2.0-or-later, liverpool.cpp ComputePipeOn/ComputePart, which ships it
    on with parts "ade"): (a) compute packets that only reach memory through the draw pipe
    (registers, dispatches, cache flushes, waits, nested buffers) do not drain it first; (e) a
    graphics wait lets the other queues run once before draining the draw pipe for a label it may
    not write. Unlike TOport here ReleaseMem and WriteData keep their drain (no in-order compute
    labels in this tree). BB_COMPUTE_PIPE=1 turns it on, BB_COMPUTE_PIPE_PARTS picks parts
    (default "ae")."""
    path = m.BBPORT / 'gpu/shadps4/video_core/amdgpu/liverpool.cpp'
    text = read(path)
    mark = 'bbport-order-win (114)'
    if mark in text:
        print('-- compute_pipe_win: sudah')
        return
    if 'bbport-order-win (108)' not in text:
        sys.exit('liverpool.cpp: 108 belum terpasang (gpu_stall_win dulu)')
    helper = (
        '// ' + mark + ': BB_COMPUTE_PIPE (after TOport, IgorAugustoHH/The-Order-1886-PC-Port,\n'
        '// GPL-2.0-or-later). a = compute packets that only reach memory through the draw pipe do not\n'
        '// drain it first; e = graphics waits let the other queues run once before draining.\n'
        'static bool BbComputePipeOn() {\n'
        '    static const bool on = [] {\n'
        '        const char* env = std::getenv("BB_COMPUTE_PIPE");\n'
        '        const bool v = env && env[0] == \'1\';\n'
        '        if (v) {\n'
        '            const char* parts = std::getenv("BB_COMPUTE_PIPE_PARTS");\n'
        '            std::fprintf(stderr, "bbport-order (114): compute pipe aktif, bagian %s\\n",\n'
        '                         parts ? parts : "ae");\n'
        '        }\n'
        '        return v;\n'
        '    }();\n'
        '    return on;\n'
        '}\n'
        'static bool BbComputePart(char part) {\n'
        '    static const std::string parts = [] {\n'
        '        const char* env = std::getenv("BB_COMPUTE_PIPE_PARTS");\n'
        '        return std::string(env ? env : "ae");\n'
        '    }();\n'
        '    return BbComputePipeOn() && parts.find(part) != std::string::npos;\n'
        '}\n'
        'static bool BbComputePacketPipelined(std::span<const u32> acb) {\n'
        '    const auto* header = reinterpret_cast<const PM4Header*>(acb.data());\n'
        '    if (header->type != 3 || header->type3.NumWords() + 1 > acb.size()) {\n'
        '        return false;\n'
        '    }\n'
        '    switch (header->type3.opcode) {\n'
        '    case PM4ItOpcode::Nop:\n'
        '    case PM4ItOpcode::SetShReg:\n'
        '    case PM4ItOpcode::SetQueueReg:\n'
        '    case PM4ItOpcode::DispatchDirect:\n'
        '    case PM4ItOpcode::DispatchIndirect:\n'
        '    case PM4ItOpcode::AcquireMem:\n'
        '    case PM4ItOpcode::EventWrite:\n'
        '    case PM4ItOpcode::WaitRegMem:\n'
        '    case PM4ItOpcode::IndirectBuffer:\n'
        '        return true;\n'
        '    default:\n'
        '        return false; // ReleaseMem, WriteData, DmaData, Rewind, ...: drained first\n'
        '    }\n'
        '}\n')
    anchor = '#define BB_ORDER_WRM_MEM(w)'
    edits = [
        (anchor, helper + anchor),
        ('        ProcessCommands();\n'
         '        if (rasterizer) {\n'
         '            rasterizer->DrainDrawPipe(Vulkan::DrawPipe::ReasonCompute); // bbport: compute work uses the caches\n',
         '        ProcessCommands();\n'
         '        if (rasterizer && !(BbComputePart(\'a\') && queue.tmp_dwords == 0 &&\n'
         '                            BbComputePacketPipelined(acb))) { // ' + mark + '\n'
         '            rasterizer->DrainDrawPipe(Vulkan::DrawPipe::ReasonCompute); // bbport: compute work uses the caches\n'),
        ('                u64 bb_stall = 0;\n'
         '                while (!wait_reg_mem->Test(regs.reg_array)) {\n'
         '                    if (BbOrderStall(bb_stall, "WaitRegMem gfx", header,\n'
         '                                     BB_ORDER_WRM_MEM(wait_reg_mem))) {\n'
         '                        break;\n'
         '                    }\n',
         '                u64 bb_stall = 0;\n'
         '                bool bb_yielded = !BbComputePart(\'e\'); // ' + mark + '\n'
         '                while (!wait_reg_mem->Test(regs.reg_array)) {\n'
         '                    if (BbOrderStall(bb_stall, "WaitRegMem gfx", header,\n'
         '                                     BB_ORDER_WRM_MEM(wait_reg_mem))) {\n'
         '                        break;\n'
         '                    }\n'
         '                    if (!bb_yielded) { // ' + mark + ': the other queues first\n'
         '                        bb_yielded = true;\n'
         '                        YIELD_GFX();\n'
         '                        continue;\n'
         '                    }\n'),
    ]
    for old, new in edits:
        if text.count(old) != 1:
            sys.exit('liverpool.cpp: anchor (114) tidak ditemukan/tidak unik (%d):\n%s' % (text.count(old), old))
        text = text.replace(old, new, 1)
    if '#include <string>\n' not in text:
        text = text.replace('#include <cstring>\n', '#include <cstring>\n#include <string>\n', 1)
    write(path, text)
    print('ok compute_pipe_win (114)')


def addr64_loads_win():
    """115: missing shadows and sunlight. GCN buffer loads with ADDR64 (address = T# base + 64-bit
    VGPR pair + SOFFSET + offset, not bounded by NUM_RECORDS) were translated as ordinary buffer
    loads, so the light data the game reads that way came back wrong. Ported from TOport
    (IgorAugustoHH/The-Order-1886-PC-Port, GPL-2.0-or-later: vector_memory.cpp BUFFER_LOAD,
    IR ReadGuestU32, EmitReadGuestU32; there: "fixed the missing sunlight", "sun light and correct
    shadows"). Each dword is read from guest memory through the direct memory access path, so it
    needs BB_DIRECT_MEMORY_ACCESS=1; BB_ADDR64_LOADS=0 turns it off."""
    sr = m.BBPORT / 'gpu/shadps4/shader_recompiler'
    mark = 'bbport-order-win (115)'
    vm = sr / 'frontend/translate/vector_memory.cpp'
    if mark in read(vm):
        print('-- addr64_loads_win: sudah')
        return
    files = {
        'ir/opcodes.inc': [(
            'OPCODE(ReadConstBuffer,',
            'OPCODE(ReadGuestU32,                                        U32,            U64,                                                                            )\n',
            'before')],
        'ir/ir_emitter.h': [(
            '    [[nodiscard]] U32 ReadConstBuffer(const Value& handle, const U32& index, BufferInstInfo info);\n',
            '    [[nodiscard]] U32 ReadGuestU32(const U64& address); // ' + mark + '\n', 'before')],
        'ir/ir_emitter.cpp': [(
            'U32 IREmitter::ReadConstBuffer(const Value& handle, const U32& index, BufferInstInfo info) {\n',
            'U32 IREmitter::ReadGuestU32(const U64& address) { // ' + mark + '\n'
            '    return Inst<U32>(Opcode::ReadGuestU32, address);\n'
            '}\n\n', 'before')],
        'backend/spirv/emit_spirv_instructions.h': [(
            'Id EmitReadConstBuffer(EmitContext& ctx, u32 handle, Id index);\n',
            'Id EmitReadGuestU32(EmitContext& ctx, Id address); // ' + mark + '\n', 'before')],
        'backend/spirv/emit_spirv_context_get_set.cpp': [(
            'Id EmitReadConstBuffer(EmitContext& ctx, u32 handle, Id index) {\n',
            '// ' + mark + ': one dword of guest memory at a per-lane 64-bit address (ADDR64 loads),\n'
            '// through the direct memory access lookup (missing pages read as 0).\n'
            'Id EmitReadGuestU32(EmitContext& ctx, Id address) {\n'
            '    ASSERT(EmulatorSettings.IsDirectMemoryAccessEnabled());\n'
            '    return ctx.OpFunctionCall(ctx.U32[1], ctx.read_const_dynamic,\n'
            '                              ctx.OpBitcast(ctx.U32[2], address), ctx.u32_zero_value);\n'
            '}\n\n', 'before')],
        'ir/passes/shader_info_collection_pass.cpp': [(
            '    case IR::Opcode::ReadConst:\n'
            '        if (!info.has_readconst) {\n',
            '    case IR::Opcode::ReadGuestU32: // ' + mark + '\n'
            '        info.readconst_types |= Info::ReadConstType::Dynamic;\n'
            '        info.uses_dma = true;\n'
            '        break;\n', 'before')],
        'frontend/translate/vector_memory.cpp': [(
            'void Translator::BUFFER_LOAD(u32 num_dwords, bool is_inst_typed, bool is_buffer_typed,\n'
            '                             const GcnInst& inst, u32 scalar_width, bool is_signed) {\n'
            '    const auto& mubuf = inst.control.mubuf;\n'
            '    const IR::VectorReg vaddr{inst.src[0].code};\n'
            '    const IR::ScalarReg sharp{inst.src[2].code * 4};\n'
            '\n',
            '    // ' + mark + ' (from TOport): GCN ADDR64 = T# base + VGPR[vaddr:vaddr+1] + SOFFSET +\n'
            '    // offset, not bounded by NUM_RECORDS or the stride; read from guest memory.\n'
            '    static const bool addr64_loads = [] {\n'
            '        const char* env = std::getenv("BB_ADDR64_LOADS");\n'
            '        return !(env && env[0] == \'0\');\n'
            '    }();\n'
            '    if (addr64_loads && mubuf.addr64 && !is_inst_typed && !is_buffer_typed &&\n'
            '        scalar_width == 32 && !mubuf.lds && !mubuf.tfe &&\n'
            '        EmulatorSettings.IsDirectMemoryAccessEnabled()) {\n'
            '        const IR::U64 base = ir.PackUint2x32(ir.CompositeConstruct(\n'
            '            ir.GetScalarReg(sharp), ir.BitwiseAnd(ir.GetScalarReg(sharp + 1), ir.Imm32(0xff))));\n'
            '        const IR::U64 vector_address = ir.PackUint2x32(\n'
            '            ir.CompositeConstruct(ir.GetVectorReg(vaddr), ir.GetVectorReg(vaddr + 1)));\n'
            '        const IR::U64 scalar_offset = ir.UConvert(64, IR::U32{GetSrc(inst.src[3])});\n'
            '        const IR::U64 address = ir.IAdd(ir.IAdd(base, vector_address), scalar_offset);\n'
            '        std::array<IR::U32, 4> values;\n'
            '        for (u32 i = 0; i < num_dwords; ++i) {\n'
            '            values[i] = ir.ReadGuestU32(ir.IAdd(address, ir.Imm64(u64(mubuf.offset) + i * 4)));\n'
            '        }\n'
            '        const IR::VectorReg dst_reg{inst.src[1].code};\n'
            '        for (u32 i = 0; i < num_dwords; ++i) {\n'
            '            ir.SetVectorReg(dst_reg + i, values[i]);\n'
            '        }\n'
            '        return;\n'
            '    }\n\n', 'after')],
    }
    for rel, edits in files.items():
        path = sr / rel
        text = read(path)
        for anchor, add, where in edits:
            if text.count(anchor) != 1:
                sys.exit('%s: anchor (115) tidak ditemukan/tidak unik (%d):\n%s' % (rel, text.count(anchor), anchor))
            text = text.replace(anchor, add + anchor if where == 'before' else anchor + add, 1)
        if rel == 'frontend/translate/vector_memory.cpp':
            if '#include <array>' not in text:
                text = text.replace('#include <cstdlib>\n', '#include <array>\n#include <cstdlib>\n', 1)
            if 'core/emulator_settings.h' not in text:
                text = text.replace('#include "shader_recompiler/frontend/translate/translate.h"\n',
                                    '#include "shader_recompiler/frontend/translate/translate.h"\n'
                                    '#include "core/emulator_settings.h"\n', 1)
        write(path, text)
    print('ok addr64_loads_win (115)')


def addr64_opcode_fix_win():
    """115 fix-up: the first 115 wrote "OPCODE(ReadConstBuffer," twice into ir/opcodes.inc (the
    anchor was repeated in the insertion): the build failed (29 Oct 00:27). Remove the duplicate."""
    path = m.BBPORT / 'gpu/shadps4/shader_recompiler/ir/opcodes.inc'
    text = read(path)
    bad = 'OPCODE(ReadConstBuffer,OPCODE(ReadConstBuffer,'
    if bad not in text:
        print('-- addr64_opcode_fix_win: tidak perlu')
        return
    write(path, text.replace(bad, 'OPCODE(ReadConstBuffer,', 1))
    print('ok addr64_opcode_fix_win (opcodes.inc diperbaiki)')


def content_service_label_win():
    """116. sceAppContentGetAddcontInfoList with a nonzero service label: The Order asks for its
    add-ons under a second label on some players' runs (a friend's RTX 4070 SUPER, 29 Oct: black
    screen, log ends "STOP: nonzero AppContent service label unsupported", exit 21). The port has
    no add-ons under any label: answer the same list as label 0 (offline profile) and log it once."""
    path = m.BBPORT / 'src' / 'runtime_content.c'
    text = read(path)
    if 'bbport-order-win (116)' in text:
        print('-- content_service_label_win: sudah')
        return
    old = '    if (service) { fputs("STOP: nonzero AppContent service label unsupported\\n",stderr); exit(21); }\n'
    new = ('    if (service) { /* bbport-order-win (116): same offline list as label 0 */\n'
           '        static int noted; if (!noted) { noted=1; printf("bbport-order-win (116): AppContent service label %u -> daftar add-on label 0\\n",service); }\n'
           '    }\n')
    if old not in text:
        sys.exit('content_service_label_win: titik sisip tidak ditemukan di runtime_content.c')
    write(path, text.replace(old, new, 1))
    print('ok content_service_label_win (116)')


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
    srt_no_patch_win()
    gpu_stall_win()
    asc_trace_win()
    rewind_ctx_win()
    dma_self_patch_win()
    host_priority_win()
    task_kernel_sleep_win()
    compute_pipe_win()
    addr64_loads_win()
    addr64_opcode_fix_win()
    content_service_label_win()
    branding_win()
    print('Selesai (Windows). Build ulang: bash build.sh di MSYS2 CLANG64.')


if __name__ == '__main__':
    main()
