#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""The Order: 1886 (CUSA00035 v01.02) — perubahan bbport untuk branch order1886 (Linux).

Idempotent: setiap bagian punya marker 'bbport-order'; dijalankan ulang tidak menggandakan apa pun.

    python3 order_patch.py            (dari folder mana saja)

Bagian:
  1. src/import_names.inc : tambah nama untuk semua import The Order yang belum tercatat
     (runtime_symbol() menolak fungsi yang sebenarnya sudah ada kalau NID-nya tidak dikenal,
     contoh: pthread_key_create mqULNdimTn0#I#J). Sumber nama: Project/nid_nama.txt (shadPS4 aerolib).
  2. src/runtime_kernel.c : stub offline untuk fungsi yang belum ada di bbport
     (IME keyboard, progress bar dialog, SaveDataDialog, add-on content, screenshot,
     video recording, select, chmod/futimes/getdents, GetModuleInfoFromAddr).
  3. src/runtime_memory.c : antrean hook GPU 64 -> 16384 + flush per batch
     ("STOP: GPU hook queue overflow" saat GPU siap sesudah ratusan mapping memori).
  4. src/runtime_pad.c    : statistik heap (BB_FRAME_STATS) membaca alamat libc Bloodborne
     0x8056ff8c0 -> crash di game lain; sekarang dicek dulu apakah halamannya dipetakan.
  5. gpu/.../pixel_format.cpp + liverpool_to_vk.cpp : format FMASK (MSAA, data_format 44..56)
     ("Unknown data_format=48 and num_format=4" saat custom resolve MSAA 4x).
  6. liverpool_to_vk.cpp SurfaceFormat : kombinasi yang tidak ada di tabel (5_9_9_9 + UbnormNz)
     memakai number format terdekat (Unorm, Float, Uint, ...) alih-alih berhenti.
  7. vk_rasterizer.cpp : T# dengan tile mode 27..30 (tidak ada di PS4) atau LinearGeneral (31,
     tidak bisa diukur UpdateSize) ditolak seperti T# tidak valid lain.
  8. liverpool_to_vk.cpp ComponentSwizzle : swizzle 2/3 (tidak ada) -> identity, bukan crash.
  9. vk_rasterizer.cpp + image.cpp : T# berukuran > 1 GiB ditolak (ErrorOutOfDeviceMemory saat
     logo Santa Monica); kalau vmaCreateImage tetap gagal, ukuran/format dicatat di log.
 10. flatten_extended_userdata_pass.cpp : Phi trivial di offset descriptor (loop) diselesaikan
     ke nilainya -> lebih sedikit "SRT walker" gagal dan T# sampah.
 11. flatten_extended_userdata_pass.cpp : bacaan yang offset-nya dinamis (Phi dinamis/bindless)
     mendapat slot berisi 0 -> texture kosong yang sah, bukan descriptor sampah.
"""
import json
import os
import re
import sys
from pathlib import Path

# Linux layout of the original work (bbport in $ORDER_PROJECT/bbport, work folder $ORDER_WORK).
PROJECT = Path(os.environ.get('ORDER_PROJECT', Path.home() / 'Project'))
KERJA = Path(os.environ.get('ORDER_WORK', Path.home() / 'PS41886'))
BBPORT = PROJECT / 'bbport'
LINK_JSON = KERJA / 'out' / 'link.json'
NID_DB = PROJECT / 'nid_nama.txt'
MARK = 'bbport-order'


def read(path):
    return path.read_text(encoding='utf-8')


def write(path, text):
    path.write_text(text, encoding='utf-8')


def import_names():
    inc = BBPORT / 'src' / 'import_names.inc'
    if not LINK_JSON.is_file():
        sys.exit(f'{LINK_JSON} belum ada: jalankan dulu "bash order-port.sh --prepare".')
    names = {}
    for line in read(NID_DB).splitlines():
        parts = line.split()
        if len(parts) == 2:
            names.setdefault(parts[0], parts[1])
    text = read(inc)
    known = set(re.findall(r'\{"([^"]+)"', text))
    added, unknown = [], []
    for full in json.loads(read(LINK_JSON))['runtime_imports']:
        if '#' not in full or full in known:
            continue
        nid = full.split('#', 1)[0]
        if nid in names:
            added.append(f'{{"{full}","{names[nid]}"}},')
            known.add(full)
        else:
            unknown.append(full)
    if added:
        if not text.endswith('\n'):
            text += '\n'
        text += f'/* {MARK}: import The Order: 1886 */\n' + '\n'.join(added) + '\n'
        write(inc, text)
    print(f'1. import_names.inc: {len(added)} nama ditambahkan, {len(unknown)} tanpa nama')
    for full in unknown[:10]:
        print('   tanpa nama:', full)


FUNCTIONS = r'''
/* ---- bbport-order: stub offline The Order: 1886 ---- */
#define ORDER_LOG(name) do { static int n_; if (n_ < 4) { n_++; printf("Runtime: order-stub %s\n", name); } } while (0)
static ABI int32_t order_ok(void) { ORDER_LOG("no-op -> 0"); return 0; }
/* libSceIme keyboard (USB keyboard untuk chat/teks): tidak ada keyboard terhubung. */
static ABI int32_t order_ime_kbd_open(int32_t user, const void *param) {
    (void)user; (void)param;
    ORDER_LOG("sceImeKeyboardOpen -> 0");
    return 0;
}
/* sceImeKeyboardGetResourceId(userId, SceImeKeyboardResourceIdArray*): {s32 userId; u32 resourceId[5];} */
static ABI int32_t order_ime_kbd_resource(int32_t user, int32_t *ids) {
    ORDER_LOG("sceImeKeyboardGetResourceId -> tidak ada keyboard");
    if (!ids) return (int32_t)0x80BC0001; /* SCE_IME_ERROR_INVALID_ADDRESS (kode belum diverifikasi) */
    memset(ids, 0, 6 * sizeof(int32_t));
    ids[0] = user;
    return 0;
}
/* SaveDataDialog: dialog selalu langsung selesai (save/load berjalan tanpa jendela). */
static ABI int32_t order_save_dialog_ready(void) { return 1; }
static ABI int32_t order_save_dialog_result(void *result) {
    ORDER_LOG("sceSaveDataDialogGetResult -> OK");
    if (result) memset(result, 0, 16); /* mode, result=0 (OK), buttonId; sisanya tidak disentuh */
    return 0;
}
/* Add-on content: tidak ada DLC yang ter-mount (content_profile: mounted add-ons=0). */
#define ORDER_ADDCONT_NOT_FOUND ((int32_t)0x80D90005)
static ABI int32_t order_addcont_none(void) { ORDER_LOG("sceAppContentAddcont* -> NOT_FOUND"); return ORDER_ADDCONT_NOT_FOUND; }
/* select(nfds, r, w, e, timeout): tidak ada socket yang siap; tunggu sesuai timeout. */
typedef struct { int64_t sec, usec; } OrderTimeval;
static ABI int32_t order_select(int32_t nfds, void *r, void *w, void *e, const OrderTimeval *timeout) {
    (void)nfds; (void)r; (void)w; (void)e;
    ORDER_LOG("select -> 0 (timeout)");
    if (timeout && (timeout->sec > 0 || timeout->usec > 0)) {
        struct timespec ts = { (time_t)timeout->sec, (long)(timeout->usec * 1000) };
        if (ts.tv_sec > 1) ts.tv_sec = 1;
        nanosleep(&ts, NULL);
    }
    return 0;
}
/* sceKernelGetdents: direktori dianggap kosong (0 byte = akhir daftar). */
static ABI int32_t order_getdents(int32_t fd, char *buf, int32_t size) {
    (void)fd; (void)buf; (void)size;
    ORDER_LOG("sceKernelGetdents -> 0 (kosong)");
    return 0;
}
static ABI int32_t order_module_info_from_addr(const void *addr, int32_t flags, void *info) {
    (void)addr; (void)flags; (void)info;
    ORDER_LOG("sceKernelGetModuleInfoFromAddr -> ESRCH");
    return (int32_t)0x80020003; /* SCE_KERNEL_ERROR_ESRCH */
}
/* ---- akhir bbport-order ---- */
'''

TABLE = r'''    /* bbport-order: The Order: 1886 */
    {"sceImeUpdate",order_ok}, {"sceImeKeyboardOpen",order_ime_kbd_open},
    {"sceImeKeyboardGetResourceId",order_ime_kbd_resource}, {"sceImeKeyboardClose",order_ok},
    {"sceSaveDataDialogIsReadyToDisplay",order_save_dialog_ready},
    {"sceSaveDataDialogGetResult",order_save_dialog_result},
    {"sceSaveDataDialogClose",order_ok}, {"sceSaveDataDialogProgressBarSetValue",order_ok},
    {"sceMsgDialogClose",order_ok}, {"sceMsgDialogProgressBarSetMsg",order_ok},
    {"sceMsgDialogProgressBarSetValue",order_ok},
    {"sceAppContentAddcontMount",order_addcont_none}, {"sceAppContentAddcontUnmount",order_addcont_none},
    {"sceAppContentGetEntitlementKey",order_addcont_none},
    {"sceScreenShotEnable",order_ok}, {"sceScreenShotDisable",order_ok},
    {"sceVideoRecordingSetInfo",order_ok},
    {"select",order_select}, {"sceKernelGetdents",order_getdents},
    {"sceKernelChmod",order_ok}, {"sceKernelFutimes",order_ok},
    {"sceKernelGetModuleInfoFromAddr",order_module_info_from_addr},
'''


def runtime_kernel():
    path = BBPORT / 'src' / 'runtime_kernel.c'
    text = read(path)
    if MARK in text:
        # Perbaikan versi 1: GetResourceId salah tanda tangan (userId dipakai sebagai pointer -> crash 0x1).
        old = ('static ABI int32_t order_ime_kbd_resource(uint32_t *ids) {\n'
               '    if (ids) memset(ids, 0, 8 * sizeof(uint32_t)); /* SceImeKeyboardResourceIdArray: userId + 5 id */\n'
               '    return 0;\n}\n')
        if old in text:
            start = FUNCTIONS.index('/* sceImeKeyboardGetResourceId(')
            end = FUNCTIONS.index('}\n', FUNCTIONS.index('ids[0] = user;')) + 2
            write(path, text.replace(old, FUNCTIONS[start:end], 1))
            print('2. runtime_kernel.c: stub sceImeKeyboardGetResourceId diperbaiki')
        else:
            print('2. runtime_kernel.c: sudah dipatch')
        return
    anchor_fn = '/* bbport-dmc: the guest thread id'
    anchor_tab = '    {"sceGameLiveStreamingEnableLiveStreaming",shareplay_ok},\n'
    if text.count(anchor_fn) != 1 or text.count(anchor_tab) != 1:
        sys.exit('runtime_kernel.c: titik sisip tidak ditemukan (branch bukan order1886/dmc?)')
    if '#include <time.h>' not in text:
        text = '#include <time.h>\n' + text
    text = text.replace(anchor_fn, FUNCTIONS.lstrip('\n') + anchor_fn, 1)
    text = text.replace(anchor_tab, anchor_tab + TABLE, 1)
    write(path, text)
    print('2. runtime_kernel.c: 22 stub The Order ditambahkan')


OLD_QUEUE = 'static PendingHook pending[64]; static size_t pending_count;'
NEW_QUEUE = ('/* bbport-order: 64 tidak cukup: saat hook GPU didaftarkan, setiap VMA yang sudah ada diantrekan\n'
             ' * (The Order memetakan ratusan blok 2 MB sebelum GPU siap). */\n'
             'static PendingHook pending[16384]; static size_t pending_count;')
OLD_FLUSH = '''static void flush_hooks(void) {
    for (;;) {
        write_lock();
        if (!pending_count) { write_unlock(); return; }
        PendingHook h=pending[0];
        memmove(pending,pending+1,--pending_count*sizeof(*pending));
        GpuRange hook = h.kind==HOOK_MAP ? hook_map : h.kind==HOOK_UNMAP ? hook_unmap : hook_invalidate;
        write_unlock();
        if (hook) hook(h.address,h.size);
    }
}'''
NEW_FLUSH = '''static void flush_hooks(void) {
    /* bbport-order: ambil seluruh antrean sekaligus (urutan tetap), bukan memmove per entri. */
    for (;;) {
        write_lock();
        size_t n=pending_count;
        if (!n) { write_unlock(); return; }
        PendingHook *batch=malloc(n*sizeof(*batch));
        if (!batch) { write_unlock(); fputs("STOP: GPU hook batch allocation failed\\n",stderr); exit(21); }
        memcpy(batch,pending,n*sizeof(*batch));
        pending_count=0;
        write_unlock();
        for (size_t i=0;i<n;++i) {
            GpuRange hook = batch[i].kind==HOOK_MAP ? hook_map : batch[i].kind==HOOK_UNMAP ? hook_unmap : hook_invalidate;
            if (hook) hook(batch[i].address,batch[i].size);
        }
        free(batch);
    }
}'''


def runtime_memory():
    path = BBPORT / 'src' / 'runtime_memory.c'
    text = read(path)
    if MARK in text:
        print('3. runtime_memory.c: sudah dipatch')
        return
    if text.count(OLD_QUEUE) != 1 or text.count(OLD_FLUSH) != 1:
        sys.exit('runtime_memory.c: antrean hook GPU tidak sesuai yang diharapkan')
    text = text.replace(OLD_QUEUE, NEW_QUEUE, 1).replace(OLD_FLUSH, NEW_FLUSH, 1)
    write(path, text)
    print('3. runtime_memory.c: antrean hook GPU 64 -> 16384, flush per batch')


OLD_HEAP = '''    const uint8_t *stub=(const uint8_t *)(0x800000000ull+0x56e0000+0x1f8c0);
    if (stub[0]!=0xff || stub[1]!=0x25) return; /* another libc */'''
NEW_HEAP = '''    const uint8_t *stub=(const uint8_t *)(0x800000000ull+0x56e0000+0x1f8c0);
    /* bbport-order: alamat ini khusus libc Bloodborne. Di game lain (The Order: libc di +0x1770000)
     * halaman itu tidak dipetakan -> crash. msync gagal (ENOMEM) untuk halaman yang tidak dipetakan. */
    { static int mapped=-1;
      if (mapped<0) mapped=msync((void *)((uintptr_t)stub & ~(uintptr_t)4095),4096,MS_ASYNC)==0;
      if (!mapped) return; }
    if (stub[0]!=0xff || stub[1]!=0x25) return; /* another libc */'''


def runtime_pad():
    path = BBPORT / 'src' / 'runtime_pad.c'
    text = read(path)
    include = '#include "runtime.h"\n'
    if MARK in text:
        # Perbaikan versi 4: include di baris 1 mendahului #define _GNU_SOURCE -> st_mtim hilang.
        if text.startswith('#include <sys/mman.h>\n'):
            text = text[len('#include <sys/mman.h>\n'):]
            text = text.replace(include, include + '#include <sys/mman.h> /* bbport-order */\n', 1)
            write(path, text)
            print('4. runtime_pad.c: posisi #include <sys/mman.h> diperbaiki')
        else:
            print('4. runtime_pad.c: sudah dipatch')
        return
    if text.count(OLD_HEAP) != 1 or text.count(include) != 1:
        sys.exit('runtime_pad.c: report_guest_heap tidak sesuai yang diharapkan')
    text = text.replace(OLD_HEAP, NEW_HEAP, 1)
    text = text.replace(include, include + '#include <sys/mman.h> /* bbport-order */\n', 1)
    write(path, text)
    print('4. runtime_pad.c: statistik heap Bloodborne dilewati kalau alamatnya tidak dipetakan')


# --- 5. FMASK (metadata MSAA) sebagai texture: data_format 44..56 ---
FMASK_NAMES = {44: 'Fmask8_S2_F1', 45: 'Fmask8_S4_F1', 46: 'Fmask8_S8_F1', 47: 'Fmask8_S2_F2',
               48: 'Fmask8_S4_F2', 49: 'Fmask8_S4_F4', 50: 'Fmask16_S16_F1', 51: 'Fmask16_S8_F2',
               52: 'Fmask32_S16_F2', 53: 'Fmask32_S8_F4', 54: 'Fmask32_S8_F8', 55: 'Fmask64_S16_F4',
               56: 'Fmask64_S16_F8'}
FMASK_VK = {8: 'eR8Uint', 16: 'eR16Uint', 32: 'eR32Uint', 64: 'eR32G32Uint'}


def fmask_bits(i):
    name = FMASK_NAMES[i]
    return int(name[5:name.index('_')])


def fmask_formats():
    vc = BBPORT / 'gpu' / 'shadps4' / 'video_core'
    pf, lv = vc / 'amdgpu' / 'pixel_format.cpp', vc / 'renderer_vulkan' / 'liverpool_to_vk.cpp'
    a, b = read(pf), read(lv)
    if MARK in b:
        print('5. FMASK: sudah dipatch')
        return
    rng = range(44, 57)
    comp = ['    0, // 42', '    0, // 43'] + [
        f'    {2 if fmask_bits(i) == 64 else 1}, // {i} Format{FMASK_NAMES[i]}' for i in rng]
    bits = ['    -1,  // 42', '    -1,  // 43'] + [
        f'    {fmask_bits(i)},{" " * (4 - len(str(fmask_bits(i))))}// {i} Format{FMASK_NAMES[i]}' for i in rng]
    vk = ['        // bbport-order: FMASK (metadata MSAA) dibaca shader custom resolve The Order. bbport',
          '        // tidak mengompresi MSAA, jadi FMASK di memori tetap hasil clear (0 = semua sampel di',
          '        // fragment 0): resolve memakai sampel 0 (tanpa AA, gambar benar).']
    for i in rng:
        vk.append(f'        CreateSurfaceFormatInfo(AmdGpu::DataFormat::Format{FMASK_NAMES[i]}, '
                  f'AmdGpu::NumberFormat::Uint,')
        vk.append(f'                                vk::Format::{FMASK_VK[fmask_bits(i)]}),')
    ends = {'comp': '    4, // 41 FormatBc7\n};', 'block': '    128, // 41 FormatBc7\n};',
            'elem': '    8,   // 41 FormatBc7\n};'}
    vk_end = ('        CreateSurfaceFormatInfo(AmdGpu::DataFormat::FormatBc7, AmdGpu::NumberFormat::Srgb,\n'
              '                                vk::Format::eBc7SrgbBlock),\n')
    for key in ends.values():
        if a.count(key) != 1:
            sys.exit('FMASK: titik sisip pixel_format.cpp tidak ditemukan: ' + key.splitlines()[0])
    if b.count(vk_end) != 1:
        sys.exit('FMASK: titik sisip liverpool_to_vk.cpp tidak ditemukan')
    a = a.replace(ends['comp'], ends['comp'][:-2] + '\n'.join(comp) + '\n};', 1)
    a = a.replace(ends['block'], ends['block'][:-2] + '\n'.join(bits) + '\n};', 1)
    a = a.replace(ends['elem'], ends['elem'][:-2] + '\n'.join(bits) + '\n};', 1)
    b = b.replace(vk_end, vk_end + '\n'.join(vk) + '\n', 1)
    write(pf, a)
    write(lv, b)
    print('5. FMASK: 13 format (data_format 44..56) dipetakan ke R8/R16/R32/R32G32 Uint')


# --- 6. SurfaceFormat: kombinasi data/number format yang tidak dikenal -> format terdekat ---
OLD_SURFACE = '''vk::Format SurfaceFormat(AmdGpu::DataFormat data_format, AmdGpu::NumberFormat num_format) {
    vk::Format result = surface_format_table[GetSurfaceFormatTableIndex(data_format, num_format)];
    bool found ='''
NEW_SURFACE = '''vk::Format SurfaceFormat(AmdGpu::DataFormat data_format, AmdGpu::NumberFormat num_format) {
    vk::Format result = surface_format_table[GetSurfaceFormatTableIndex(data_format, num_format)];
    // bbport-order: The Order memakai descriptor dengan number format yang tidak ada di tabel
    // (mis. 5_9_9_9 + UbnormNz). Coba number format terdekat dulu; hanya kalau data format itu
    // sama sekali tidak dikenal baru berhenti.
    if (result == vk::Format::eUndefined && data_format != AmdGpu::DataFormat::FormatInvalid) {
        static constexpr AmdGpu::NumberFormat fallbacks[] = {
            AmdGpu::NumberFormat::Unorm, AmdGpu::NumberFormat::Float, AmdGpu::NumberFormat::Uint,
            AmdGpu::NumberFormat::Snorm, AmdGpu::NumberFormat::Sint, AmdGpu::NumberFormat::Srgb};
        for (const auto fallback : fallbacks) {
            result = surface_format_table[GetSurfaceFormatTableIndex(data_format, fallback)];
            if (result != vk::Format::eUndefined) {
                static std::atomic<u32> told{0};
                if (told.fetch_add(1) < 8) {
                    LOG_WARNING(Render_Vulkan,
                                "bbport-order: data_format={} num_format={} tidak dikenal, pakai num_format={}",
                                static_cast<u32>(data_format), static_cast<u32>(num_format),
                                static_cast<u32>(fallback));
                }
                return result;
            }
        }
    }
    bool found ='''


def surface_fallback():
    path = BBPORT / 'gpu' / 'shadps4' / 'video_core' / 'renderer_vulkan' / 'liverpool_to_vk.cpp'
    text = read(path)
    if 'bbport-order: The Order memakai descriptor' in text:
        print('6. SurfaceFormat fallback: sudah dipatch')
        return
    if text.count(OLD_SURFACE) != 1:
        sys.exit('SurfaceFormat: fungsi tidak sesuai yang diharapkan')
    text = text.replace(OLD_SURFACE, NEW_SURFACE, 1)
    if '#include <atomic>' not in text:
        text = text.replace('#include <magic_enum/magic_enum.hpp>\n',
                            '#include <magic_enum/magic_enum.hpp>\n#include <atomic>\n', 1)
    write(path, text)
    print('6. SurfaceFormat: format tidak dikenal -> number format terdekat (log 8x)')


# --- 7. T# dengan tile mode yang tidak ada (27..30) ditolak seperti T# tidak valid lainnya ---
TILE_FN_V1 = '''/// bbport-order: tile mode 27..30 tidak ada di GPU PS4; T# seperti itu berisi sampah
/// (The Order: "Unknown tile mode = 29" di GetArrayMode).
bool IsKnownTileMode(AmdGpu::TileMode mode) {
    const u32 m = static_cast<u32>(mode);
    return m <= static_cast<u32>(AmdGpu::TileMode::Thick3DXThick) ||
           mode == AmdGpu::TileMode::DisplayLinearGeneral;
}
'''
TILE_FN = '''/// bbport-order: tile mode 27..30 tidak ada di GPU PS4; T# seperti itu berisi sampah
/// (The Order: "Unknown tile mode = 29" di GetArrayMode). LinearGeneral (31) juga ditolak untuk
/// texture: ImageInfo::UpdateSize tidak bisa mengukurnya ("Unhandled array mode"), dan di The Order
/// yang memakainya hanya T# sampah (5_9_9_9 + UbnormNz).
bool IsKnownTileMode(AmdGpu::TileMode mode) {
    return static_cast<u32>(mode) <= static_cast<u32>(AmdGpu::TileMode::Thick3DXThick);
}
'''
TILE_DEF = '/// magic_enum::enum_contains, from a table: it scans every enumerator (per texture per draw).\n'
TILE_OLD = '!IsKnownFormat(data_fmt, num_fmt)) {'
TILE_NEW = '!IsKnownFormat(data_fmt, num_fmt) || !IsKnownTileMode(tsharp.GetTileMode())) {'


def tile_mode_check():
    path = BBPORT / 'gpu' / 'shadps4' / 'video_core' / 'renderer_vulkan' / 'vk_rasterizer.cpp'
    text = read(path)
    if TILE_FN_V1 in text:
        write(path, text.replace(TILE_FN_V1, TILE_FN, 1))
        print('7. vk_rasterizer.cpp: tile mode LinearGeneral (31) sekarang juga ditolak untuk texture')
        return
    if 'IsKnownTileMode' in text:
        print('7. vk_rasterizer.cpp tile mode: sudah dipatch')
        return
    if text.count(TILE_DEF) != 1 or text.count(TILE_OLD) != 2:
        sys.exit('vk_rasterizer.cpp: titik sisip IsKnownFormat tidak sesuai')
    text = text.replace(TILE_DEF, TILE_FN + TILE_DEF, 1).replace(TILE_OLD, TILE_NEW)
    write(path, text)
    print('7. vk_rasterizer.cpp: T# dengan tile mode 27..30 ditolak (2 tempat)')


# --- 8. ComponentSwizzle: nilai swizzle 2/3 (tidak ada) dari T# sampah -> identity, bukan crash ---
SWZ_OLD = '''    case AmdGpu::CompSwizzle::Alpha:
        return vk::ComponentSwizzle::eA;
    default:
        UNREACHABLE();
    }
}
'''
SWZ_NEW = '''    case AmdGpu::CompSwizzle::Alpha:
        return vk::ComponentSwizzle::eA;
    default: {
        // bbport-order: swizzle 2/3 tidak ada di GPU PS4; datang dari T# sampah (The Order).
        static std::atomic<u32> told{0};
        if (told.fetch_add(1) < 4) {
            LOG_WARNING(Render_Vulkan, "bbport-order: swizzle tidak valid {}, pakai identity",
                        static_cast<u32>(comp_swizzle));
        }
        return vk::ComponentSwizzle::eIdentity;
    }
    }
}
'''


def swizzle_fallback():
    path = BBPORT / 'gpu' / 'shadps4' / 'video_core' / 'renderer_vulkan' / 'liverpool_to_vk.cpp'
    text = read(path)
    if 'swizzle tidak valid' in text:
        print('8. ComponentSwizzle: sudah dipatch')
        return
    if text.count(SWZ_OLD) != 1:
        sys.exit('ComponentSwizzle: fungsi tidak sesuai yang diharapkan')
    if '#include <atomic>' not in text:
        sys.exit('ComponentSwizzle: jalankan bagian 6 dulu (#include <atomic>)')
    write(path, text.replace(SWZ_OLD, SWZ_NEW, 1))
    print('8. ComponentSwizzle: swizzle tidak valid -> identity (log 4x)')


# --- 9. T# dengan ukuran mustahil (> 1 GiB) ditolak; detail dicatat kalau vmaCreateImage gagal ---
SIZE_FN = '''/// bbport-order: T# sampah bisa berukuran raksasa (lebar/tinggi 16384, ribuan layer) sehingga
/// vmaCreateImage gagal dengan ErrorOutOfDeviceMemory. Texture asli PS4 jauh di bawah 1 GiB.
bool IsPlausibleImageSize(const AmdGpu::Image& t) {
    const u32 fmt = static_cast<u32>(t.GetDataFmt());
    const u64 bits = fmt <= 56 ? AmdGpu::NumBitsPerElement(t.GetDataFmt()) : 32;
    const u64 slices = t.GetType() == AmdGpu::ImageType::Color3D ? u64(t.depth) + 1 : t.NumLayers();
    const u64 bytes = (u64(t.width) + 1) * (u64(t.height) + 1) * slices * (bits ? bits : 32) / 8;
    return bytes <= (u64(1) << 30);
}
'''
SIZE_ANCHOR = '/// magic_enum::enum_contains, from a table: it scans every enumerator (per texture per draw).\n'
SIZE_OLD = '!IsKnownTileMode(tsharp.GetTileMode())) {'
SIZE_NEW = ('!IsKnownTileMode(tsharp.GetTileMode()) ||\n'
            '            !IsPlausibleImageSize(tsharp)) {')
IMG_OLD = '''    VkResult result = vmaCreateImage(allocator, &image_ci_unsafe, &alloc_ci, &unsafe_image,
                                     &allocation, &alloc_info);
    ASSERT_MSG('''
IMG_NEW = '''    VkResult result = vmaCreateImage(allocator, &image_ci_unsafe, &alloc_ci, &unsafe_image,
                                     &allocation, &alloc_info);
    if (result != VK_SUCCESS) { // bbport-order: detail image yang gagal, untuk diagnosis
        LOG_ERROR(Render_Vulkan, "vmaCreateImage gagal: {}x{}x{}, {} mip, {} layer, {} sampel, format {}",
                  image_ci.extent.width, image_ci.extent.height, image_ci.extent.depth,
                  image_ci.mipLevels, image_ci.arrayLayers, u32(image_ci.samples),
                  vk::to_string(image_ci.format));
    }
    ASSERT_MSG('''


def image_size_check():
    vc = BBPORT / 'gpu' / 'shadps4' / 'video_core'
    ras, img = vc / 'renderer_vulkan' / 'vk_rasterizer.cpp', vc / 'texture_cache' / 'image.cpp'
    r, i = read(ras), read(img)
    if 'IsPlausibleImageSize' in r:
        print('9. ukuran image: sudah dipatch')
        return
    if r.count(SIZE_ANCHOR) != 1 or r.count(SIZE_OLD) != 2 or i.count(IMG_OLD) != 1:
        sys.exit('ukuran image: titik sisip tidak ditemukan (bagian 7 harus sudah terpasang)')
    r = r.replace(SIZE_ANCHOR, SIZE_FN + SIZE_ANCHOR, 1).replace(SIZE_OLD, SIZE_NEW)
    write(ras, r)
    write(img, i.replace(IMG_OLD, IMG_NEW, 1))
    print('9. ukuran image: T# > 1 GiB ditolak; kegagalan vmaCreateImage dicatat lengkap')


# --- 10. SRT walker: Phi trivial (semua cabang membawa nilai yang sama) di perhitungan offset ---
PHI_HELPER = '''// bbport-order: shader The Order (yang tidak diawali s_mov vcc_hi) membawa pointer/offset
// descriptor melewati loop. SSA membuat Phi yang trivial: semua argumen di luar kelompok Phi itu
// adalah nilai yang sama (Braun dkk., "redundant phi SCC"). Phi seperti itu diganti nilainya;
// Phi yang benar-benar dinamis tetap gagal seperti sebelumnya.
static std::optional<IR::Value> ResolveTrivialPhi(IR::Inst* phi) {
    std::vector<IR::Inst*> stack{phi};
    std::vector<IR::Inst*> seen{phi};
    std::optional<IR::Value> found;
    while (!stack.empty()) {
        IR::Inst* p = stack.back();
        stack.pop_back();
        for (size_t i = 0; i < p->NumArgs(); ++i) {
            const IR::Value arg = p->Arg(i);
            if (arg.IsEmpty()) {
                continue;
            }
            if (!arg.IsImmediate() && arg.Inst()->GetOpcode() == IR::Opcode::Phi) {
                IR::Inst* q = arg.Inst();
                if (std::ranges::find(seen, q) == seen.end()) {
                    if (seen.size() >= 64) {
                        return std::nullopt;
                    }
                    seen.push_back(q);
                    stack.push_back(q);
                }
                continue;
            }
            if (!found) {
                found = arg;
            } else if (!(*found == arg)) {
                return std::nullopt;
            }
        }
    }
    return found;
}

static bool IsAllowedOffsetInstruction(const IR::Inst* inst) {'''
PHI_ALLOWED_OLD = '''    case IR::Opcode::BitFieldUExtract:
        return true;
    default:
        return false;'''
PHI_ALLOWED_NEW = '''    case IR::Opcode::BitFieldUExtract:
    case IR::Opcode::Phi: // bbport-order: diikuti agar ReadConstBuffer di baliknya ikut terkumpul
        return true;
    default:
        return false;'''
PHI_CASE_OLD = '''        ABORT_ON_FAILURE(EmitComputeOffsetBitFieldUExtract(c, reg, pass_info, inst));
        return true;
    default:
        LOG_ERROR(Render_Recompiler, "Unexpected instruction for offset computation, {}",'''
PHI_CASE_NEW = '''        ABORT_ON_FAILURE(EmitComputeOffsetBitFieldUExtract(c, reg, pass_info, inst));
        return true;
    case IR::Opcode::Phi:
        if (const auto value = ResolveTrivialPhi(inst)) { // bbport-order
            if (value->IsImmediate()) {
                c.mov(reg, value->U32());
                return true;
            }
            return ComputeOffset(c, reg, pass_info, *value);
        }
        LOG_ERROR(Render_Recompiler, "Unexpected instruction for offset computation, Phi (dinamis)");
        return false;
    default:
        LOG_ERROR(Render_Recompiler, "Unexpected instruction for offset computation, {}",'''


def srt_trivial_phi():
    path = BBPORT / 'gpu' / 'shadps4' / 'shader_recompiler' / 'ir' / 'passes' / 'flatten_extended_userdata_pass.cpp'
    text = read(path)
    if 'ResolveTrivialPhi' in text:
        print('10. SRT walker Phi: sudah dipatch')
        return
    head = 'static bool IsAllowedOffsetInstruction(const IR::Inst* inst) {'
    for key in (head, PHI_ALLOWED_OLD, PHI_CASE_OLD):
        if text.count(key) != 1:
            sys.exit('SRT walker: titik sisip tidak ditemukan: ' + key.splitlines()[0])
    text = text.replace(head, PHI_HELPER, 1)
    text = text.replace(PHI_ALLOWED_OLD, PHI_ALLOWED_NEW, 1).replace(PHI_CASE_OLD, PHI_CASE_NEW, 1)
    text = text.replace('#include <queue>\n', '#include <optional>\n#include <queue>\n#include <vector>\n', 1)
    write(path, text)
    print('10. SRT walker: Phi trivial diselesaikan (offset descriptor lewat loop)')


# --- 11. SRT walker: bacaan yang offset-nya tidak bisa dihitung (Phi dinamis) -> 0, bukan sampah ---
ZERO_HELPER = '''static inline void PopPtr(Xbyak::CodeGenerator& c) {
    c.pop(rdi);
}

// bbport-order: offset dinamis (indeks loop / bindless) tidak bisa dihitung di CPU. Dulu bacaan
// itu tidak mendapat slot sehingga shader dan CPU membaca user data dword 0 = descriptor sampah
// (tile mode 29, swizzle 2/3, image 1,6 GB, data_fmt 28 ...). Sekarang setiap bacaan seperti itu
// (dan seluruh sub-pohonnya) mendapat slot berisi 0: T# alamat 0 = texture kosong yang sah.
static void ZeroFillSubtree(IR::Inst* subtree, PassInfo& pass_info, Xbyak::CodeGenerator& c) {
    PassInfo::PtrUserList* use_list = pass_info.GetUsesAsPointer(subtree);
    if (!use_list) {
        return;
    }
    for (auto [src_off_dw, use] : *use_list) {
        c.mov(dword[rsi + (pass_info.dst_off_dw << 2)], 0);
        SetFlatbufOffset(use, pass_info.dst_off_dw);
        pass_info.dst_off_dw++;
    }
    for (auto [src_off_dw, use] : *use_list) {
        if (pass_info.GetUsesAsPointer(use)) {
            ZeroFillSubtree(use, pass_info, c);
        }
    }
}
'''
ZERO_PUSH_OLD = '''    if (!PushPtr(c, pass_info, off_dw)) {
        LOG_ERROR(Render_Recompiler, "Failed to compute offset for SRT walker");
        return;
    }'''
ZERO_PUSH_NEW = '''    if (!PushPtr(c, pass_info, off_dw)) {
        LOG_ERROR(Render_Recompiler, "Failed to compute offset for SRT walker");
        // bbport-order: PushPtr sudah mendorong rdi sebelum gagal; tanpa pop, stack walker
        // tidak seimbang dan `ret` di akhir melompat ke alamat sampah.
        PopPtr(c);
        ZeroFillSubtree(subtree, pass_info, c);
        return;
    }'''
ZERO_USE_OLD = '''            if (!ComputeOffset(c, r10d, pass_info, src_off_dw)) {
                LOG_ERROR(Render_Recompiler, "Failed to compute offset for SRT walker");
                continue;
            }
            c.shl(r10d, 2);
            c.mov(r10d, r10d);
            c.mov(r10d, dword[rdi + r10]);'''
ZERO_USE_NEW = '''            if (!ComputeOffset(c, r10d, pass_info, src_off_dw)) {
                LOG_ERROR(Render_Recompiler, "Failed to compute offset for SRT walker");
                c.xor_(r10d, r10d); // bbport-order: slot berisi 0, bukan dword 0 user data
            } else {
                c.shl(r10d, 2);
                c.mov(r10d, r10d);
                c.mov(r10d, dword[rdi + r10]);
            }'''
ZERO_POP_OLD = '''static inline void PopPtr(Xbyak::CodeGenerator& c) {
    c.pop(rdi);
}
'''


def srt_zero_fill():
    path = BBPORT / 'gpu' / 'shadps4' / 'shader_recompiler' / 'ir' / 'passes' / 'flatten_extended_userdata_pass.cpp'
    text = read(path)
    if 'ZeroFillSubtree' in text:
        print('11. SRT walker isi-nol: sudah dipatch')
        return
    for key in (ZERO_POP_OLD, ZERO_PUSH_OLD, ZERO_USE_OLD):
        if text.count(key) != 1:
            sys.exit('SRT walker isi-nol: titik sisip tidak ditemukan: ' + key.splitlines()[0])
    text = text.replace(ZERO_POP_OLD, ZERO_HELPER, 1)
    text = text.replace(ZERO_PUSH_OLD, ZERO_PUSH_NEW, 1).replace(ZERO_USE_OLD, ZERO_USE_NEW, 1)
    write(path, text)
    print('11. SRT walker: bacaan dengan offset dinamis diisi 0 (texture kosong, bukan sampah)')


# --- 12. Diagnosa save: log hasil Mount/Search/Delete dan isi SaveDataDialog (mode, pesan, kode) ---
SAVE_MOUNT_OLD = '''static ABI int32_t save_mount(const Mount1 *m, MountResult *result) {
    if (!m) return ERR_PARAMETER;
    return mount(m->user,m->title ? m->title->data : NULL,m->dir,m->mode,result);
}
static ABI int32_t save_mount2(const Mount2 *m, MountResult *result) {
    if (!m) return ERR_PARAMETER;
    return mount(m->user,NULL,m->dir,m->mode,result);
}'''
SAVE_MOUNT_NEW = '''static ABI int32_t save_mount(const Mount1 *m, MountResult *result) {
    if (!m) return ERR_PARAMETER;
    const int32_t r=mount(m->user,m->title ? m->title->data : NULL,m->dir,m->mode,result);
    if (r) printf("Runtime: bbport-order sceSaveDataMount user=%d dir='%.32s' mode=%#x blocks=%llu -> %#x\\n",
                  m->user,m->dir ? m->dir->data : "",m->mode,(unsigned long long)m->blocks,(unsigned)r);
    return r;
}
static ABI int32_t save_mount2(const Mount2 *m, MountResult *result) {
    if (!m) return ERR_PARAMETER;
    const int32_t r=mount(m->user,NULL,m->dir,m->mode,result);
    if (r) printf("Runtime: bbport-order sceSaveDataMount2 user=%d dir='%.32s' mode=%#x -> %#x\\n",
                  m->user,m->dir ? m->dir->data : "",m->mode,(unsigned)r);
    return r;
}'''
SAVE_DIALOG_OLD = 'DIALOG(msg,1) DIALOG(save,2) DIALOG(profile,3) DIALOG(commerce,4)'
SAVE_DIALOG_NEW = '''DIALOG(msg,1) DIALOG(profile,3) DIALOG(commerce,4)
/* bbport-order: SaveDataDialog dengan log isi parameternya (SDK: CommonDialog base 48 byte, lalu
 * size, mode, dispType, pointer anim/items/userMsg/sysMsg/errorCode/progBar). mode: 1 user msg,
 * 2 system msg, 3 kode error, 4 progress bar. */
static ABI int32_t save_init(void) { return dialog_init(2); }
static ABI int32_t save_open(const uint8_t *p) {
    static int told;
    if (p && told++ < 12) {
        const uint32_t mode=*(const uint32_t *)(p+52), disp=*(const uint32_t *)(p+56);
        const uint32_t *sys=*(const uint32_t *const *)(p+88);
        const int32_t *err=*(const int32_t *const *)(p+96);
        const uint32_t *user=*(const uint32_t *const *)(p+80);
        printf("Runtime: bbport-order SaveDataDialog mode=%u dispType=%u sysMsgType=%d errorCode=%#x userMsgButtons=%d\\n",
               mode,disp,sys ? (int)sys[0] : -1,err ? (unsigned)err[0] : 0u,user ? (int)user[0] : -1);
    }
    return dialog_open(2);
}
static ABI int32_t save_status(void) { return dialog_status(2); }
static ABI int32_t save_term(void) { return dialog_term(2); }'''


def save_diagnostics():
    src = BBPORT / 'src'
    sd, sv = src / 'runtime_savedata.c', src / 'runtime_services.c'
    a, b = read(sd), read(sv)
    if 'bbport-order sceSaveDataMount' in a:
        print('12. diagnosa save: sudah dipatch')
        return
    if a.count(SAVE_MOUNT_OLD) != 1 or b.count(SAVE_DIALOG_OLD) != 1:
        sys.exit('diagnosa save: titik sisip tidak ditemukan')
    write(sd, a.replace(SAVE_MOUNT_OLD, SAVE_MOUNT_NEW, 1))
    write(sv, b.replace(SAVE_DIALOG_OLD, SAVE_DIALOG_NEW, 1))
    print('12. diagnosa save: kegagalan Mount dan isi SaveDataDialog dicatat di log')


# --- 13. Diagnosa lag: kenapa shader yang sama terus mendapat permutasi baru ---
PERM_FN = '''// bbport-order: The Order terus meng-compile ulang shader yang sama (40-50 per 5 detik di layar
// diam). Catat bagian spesialisasi yang berbeda dari permutasi sebelumnya (permutasi ke-3 ke atas).
static void BbOrderLogPermutation(u64 hash, size_t perm_idx, const Shader::StageSpecialization& a,
                                  const Shader::StageSpecialization& b) {
    static std::atomic<u32> told{0};
    if (perm_idx < 3 || told.fetch_add(1) >= 60) {
        return;
    }
    std::string why;
    if (a.vs_attribs != b.vs_attribs) why += " vs_attribs";
    if (!(a.runtime_info == b.runtime_info)) why += " runtime_info";
    if (a.fetch_shader_data != b.fetch_shader_data) why += " fetch";
    if (a.fmasks != b.fmasks) why += " fmask";
    if (a.start != b.start) why += " start";
    for (size_t i = 0; i < a.buffers.size() && i < b.buffers.size(); ++i) {
        if (!(a.buffers[i] == b.buffers[i])) {
            why += fmt::format(" buf{}(stride {}->{} fmt {}->{} fmtd {})", i, b.buffers[i].stride,
                               a.buffers[i].stride, u32(b.buffers[i].data_format),
                               u32(a.buffers[i].data_format), u32(a.buffers[i].is_formatted));
        }
    }
    for (size_t i = 0; i < a.images.size() && i < b.images.size(); ++i) {
        if (!(a.images[i] == b.images[i])) {
            why += fmt::format(" img{}(type {}->{} int {}->{} cube {}->{} binds {}->{})", i,
                               u32(b.images[i].type), u32(a.images[i].type), b.images[i].is_integer,
                               a.images[i].is_integer, b.images[i].is_cube, a.images[i].is_cube,
                               b.images[i].num_bindings, a.images[i].num_bindings);
        }
    }
    for (size_t i = 0; i < a.samplers.size() && i < b.samplers.size(); ++i) {
        if (!(a.samplers[i] == b.samplers[i])) why += fmt::format(" smp{}", i);
    }
    LOG_WARNING(Render_Vulkan, "bbport-order: shader {:#x} permutasi ke-{}:{}", hash, perm_idx,
                why.empty() ? " (beda di bitset/jumlah resource)" : why);
}

PipelineCache::Result PipelineCache::GetProgram(PipelineSelection& sel, HwStage hw_stage,'''
PERM_HEAD = 'PipelineCache::Result PipelineCache::GetProgram(PipelineSelection& sel, HwStage hw_stage,'
PERM_OLD = '''    if (it == program->modules.end()) {
        auto new_info = Shader::Info(hw_stage, sw_stage, params);'''
PERM_NEW = '''    if (it == program->modules.end()) {
        if (!program->modules.empty()) { // bbport-order
            BbOrderLogPermutation(params.hash, perm_idx, spec, program->modules.back().spec);
        }
        auto new_info = Shader::Info(hw_stage, sw_stage, params);'''


def permutation_log():
    path = BBPORT / 'gpu' / 'shadps4' / 'video_core' / 'renderer_vulkan' / 'vk_pipeline_cache.cpp'
    text = read(path)
    if 'BbOrderLogPermutation' in text:
        print('13. log permutasi shader: sudah dipatch')
        return
    if text.count(PERM_HEAD) != 1 or text.count(PERM_OLD) != 1:
        sys.exit('log permutasi: titik sisip tidak ditemukan')
    text = text.replace(PERM_HEAD, PERM_FN, 1).replace(PERM_OLD, PERM_NEW, 1)
    if '#include <atomic>' not in text:
        text = '#include <atomic>\n' + text
    write(path, text)
    print('13. log permutasi shader: alasan compile ulang dicatat di log')


# --- 14. Image dengan alamat mustahil (< 256 MiB) ditolak; GetBarriers melewati subresource di luar batas ---
LOWADDR_OLD = '''    return bytes <= (u64(1) << 30);
}'''
LOWADDR_NEW = '''    // bbport-order: memori guest PS4 jauh di atas 256 MiB; T# di 0x1000 dsb. adalah sampah
    // (The Order: image 530 MB di 0x1000 -> GetBarriers assertion).
    return bytes <= (u64(1) << 30) && t.Address() >= (u64(1) << 28);
}'''
BARRIER_OLD = '''                const auto subres_idx = mip * info.resources.layers + layer;
                ASSERT(subres_idx < subresource_states.size());'''
BARRIER_NEW = '''                const auto subres_idx = mip * info.resources.layers + layer;
                if (subres_idx >= subresource_states.size()) { // bbport-order: view di luar image
                    continue;
                }'''


def image_guard2():
    vc = BBPORT / 'gpu' / 'shadps4' / 'video_core'
    ras, img = vc / 'renderer_vulkan' / 'vk_rasterizer.cpp', vc / 'texture_cache' / 'image.cpp'
    r, i = read(ras), read(img)
    if 'GetBarriers assertion' in r:
        print('14. alamat image rendah / GetBarriers: sudah dipatch')
        return
    if r.count(LOWADDR_OLD) != 1 or i.count(BARRIER_OLD) != 1:
        sys.exit('bagian 14: titik sisip tidak ditemukan (bagian 9 harus sudah terpasang)')
    write(ras, r.replace(LOWADDR_OLD, LOWADDR_NEW, 1))
    write(img, i.replace(BARRIER_OLD, BARRIER_NEW, 1))
    print('14. T# di bawah 256 MiB ditolak; GetBarriers melewati subresource di luar batas')


# --- 15. V# (buffer) raksasa > 256 MiB: dicatat, lalu diikat sebagai buffer kosong ---
BIGBUF_OLD = '''            } else {
                const u64 size = memory->ClampRangeSize(vsharp.base_address, vsharp.GetSize());
                if (size != vsharp.GetSize()) {'''
BIGBUF_NEW = '''            } else if (BbOrderRejectBigBuffer(vsharp.GetSize())) {
                // bbport-order: The Order macet di menu karena satu binding ±1,5 GB di-upload
                // tiap frame. Buffer asli game jauh lebih kecil; yang sebesar ini dianggap sampah
                // (BB_ORDER_BIG_BUFFER=1 mematikan pengaman ini untuk perbandingan).
                static std::atomic<u32> told{0};
                if (told.fetch_add(1) < 8) {
                    LOG_WARNING(Render_Vulkan,
                                "bbport-order: V# raksasa ditolak: shader {:#x} slot {} alamat {:#x} "
                                "ukuran {} MB stride {} tulis {}",
                                stage.pgm_hash, binding.buffer, vsharp.base_address,
                                vsharp.GetSize() >> 20, vsharp.GetStride(), desc.is_written);
                }
                buffer_infos.emplace_back(VK_NULL_HANDLE, 0, VK_WHOLE_SIZE);
            } else {
                const u64 size = memory->ClampRangeSize(vsharp.base_address, vsharp.GetSize());
                if (size != vsharp.GetSize()) {'''


BIGBUF_FN = '''/// bbport-order: V# lebih dari 256 MiB (BB_ORDER_BIG_BUFFER=1: pengaman mati).
bool BbOrderRejectBigBuffer(u64 size) {
    static const bool allow_big = std::getenv("BB_ORDER_BIG_BUFFER") != nullptr;
    return !allow_big && size > (u64(256) << 20);
}
'''
BIGBUF_ANCHOR = '/// magic_enum::enum_contains, from a table: it scans every enumerator (per texture per draw).\n'


def big_buffer_guard():
    path = BBPORT / 'gpu' / 'shadps4' / 'video_core' / 'renderer_vulkan' / 'vk_rasterizer.cpp'
    text = read(path)
    if 'V# raksasa ditolak' in text:
        print('15. V# raksasa: sudah dipatch')
        return
    if text.count(BIGBUF_OLD) != 1 or text.count(BIGBUF_ANCHOR) != 1:
        sys.exit('V# raksasa: titik sisip tidak ditemukan')
    text = text.replace(BIGBUF_ANCHOR, BIGBUF_FN + BIGBUF_ANCHOR, 1)
    write(path, text.replace(BIGBUF_OLD, BIGBUF_NEW, 1))
    print('15. V# > 256 MiB ditolak dan dicatat (BB_ORDER_BIG_BUFFER=1 untuk mematikan)')


# --- 16. SaveDataDialog progress bar (mode 5): RUNNING sampai sceSaveDataDialogClose, baru FINISHED ---
PB_OPEN_OLD = '''    return dialog_open(2);
}
static ABI int32_t save_status(void) { return dialog_status(2); }'''
PB_OPEN_NEW = '''    const int32_t r=dialog_open(2);
    /* bbport-order: mode 5 = progress bar. Game menunggu RUNNING, menyimpan, lalu memanggil
     * sceSaveDataDialogClose dan menunggu FINISHED. Langsung FINISHED membuatnya membuka ulang
     * dialog tanpa henti (The Order: 1281 kali, save tidak pernah di-mount). */
    if (!r && p && *(const uint32_t *)(p+52)==5) dialogs[2].status=2;
    return r;
}
static ABI int32_t save_close(const void *param) {
    (void)param;
    if (dialogs[2].status==2) dialogs[2].status=3;
    return 0;
}
static ABI int32_t save_status(void) { return dialog_status(2); }'''
PB_TABLE_OLD = '    {"sceSaveDataDialogUpdateStatus",save_status}, {"sceSaveDataDialogTerminate",save_term},\n'
PB_TABLE_NEW = ('    {"sceSaveDataDialogUpdateStatus",save_status}, {"sceSaveDataDialogTerminate",save_term},\n'
                '    {"sceSaveDataDialogClose",save_close}, {"sceSaveDataDialogGetStatus",save_status}, /* bbport-order */\n')
PB_KERNEL_OLD = '    {"sceSaveDataDialogClose",order_ok}, {"sceSaveDataDialogProgressBarSetValue",order_ok},\n'
PB_KERNEL_NEW = '    {"sceSaveDataDialogProgressBarSetValue",order_ok}, /* Close: runtime_services.c */\n'


def save_progress_dialog():
    src = BBPORT / 'src'
    sv, kn = src / 'runtime_services.c', src / 'runtime_kernel.c'
    a, b = read(sv), read(kn)
    if 'save_close' in a:
        print('16. SaveDataDialog progress bar: sudah dipatch')
        return
    if a.count(PB_OPEN_OLD) != 1 or a.count(PB_TABLE_OLD) != 1 or b.count(PB_KERNEL_OLD) != 1:
        sys.exit('progress bar: titik sisip tidak ditemukan (bagian 2 dan 12 harus sudah terpasang)')
    write(sv, a.replace(PB_OPEN_OLD, PB_OPEN_NEW, 1).replace(PB_TABLE_OLD, PB_TABLE_NEW, 1))
    write(kn, b.replace(PB_KERNEL_OLD, PB_KERNEL_NEW, 1))
    print('16. SaveDataDialog progress bar: RUNNING sampai Close, lalu FINISHED')


# --- 17. Permutasi shader: slot kosong di modul lama boleh melayani texture 2D biasa ---
PERM_LOOP_OLD = '''        for (u32 i = 0; i < images.size(); i++) {
            if (other.bitset[binding++] && images[i] != other.images[i]) {
                return false;
            }
        }'''
PERM_LOOP_NEW = '''        for (u32 i = 0; i < images.size(); i++) {
            const u32 slot = binding++;
            if (!other.bitset[slot]) {
                continue; // slot baru kosong: modul mana pun bisa melayaninya
            }
            // bbport-order: slot kosong di modul ini di-compile sebagai Image::Null = 2D float,
            // non-array (spirv ImageType). Texture 2D biasa yang sekarang mengisi slot itu bisa
            // memakai modul yang sama. Compute shader The Order 0x804aeead (streaming texture,
            // +-30 slot) tanpa aturan ini membuat >1000 permutasi. BB_ORDER_STRICT_PERM=1: aturan lama.
            if (!bitset[slot] && IsPlainNull2DCompatible(other.images[i], info ? info->pgm_hash : 0)) {
                continue;
            }
            if (images[i] != other.images[i]) {
                return false;
            }
        }'''
PERM_HELPER_V1 = '''/// bbport-order: apakah texture ini cocok dengan slot yang di-compile kosong (Image::Null:
/// 2D, float, non-array, bukan storage/cube/srgb, tanpa konversi angka, satu binding).
inline bool IsPlainNull2DCompatible(const ImageSpecialization& s) {
    static const bool strict = std::getenv("BB_ORDER_STRICT_PERM") != nullptr;
    return !strict && s.type == AmdGpu::ImageType::Color2D && !s.is_integer && !s.is_storage &&
           !s.is_cube && !s.is_srgb && s.num_bindings <= 1 &&
           s.num_conversion == AmdGpu::NumberConversion::None;
}

struct StageSpecialization {
'''
PERM_HELPER_ANCHOR = 'struct StageSpecialization {\n'
PERM_HELPER = '''/// bbport-order: apakah texture ini cocok dengan slot yang di-compile kosong (Image::Null:
/// 2D, float, non-array, bukan storage/cube/srgb, tanpa konversi angka, satu binding).
/// Hanya untuk shader yang disebut BB_ORDER_LOOSE_SHADER (hex, bawaan 804aeead): aturan untuk
/// semua shader membuat The Order macet di layar hitam saat boot.
inline bool IsPlainNull2DCompatible(const ImageSpecialization& s, u64 pgm_hash) {
    static const bool strict = std::getenv("BB_ORDER_STRICT_PERM") != nullptr;
    static const u64 only = [] {
        const char* e = std::getenv("BB_ORDER_LOOSE_SHADER");
        return e ? u64(std::strtoull(e, nullptr, 16)) : u64(0x804aeead);
    }();
    return !strict && only != 0 && pgm_hash == only && s.type == AmdGpu::ImageType::Color2D &&
           !s.is_integer && !s.is_storage && !s.is_cube && !s.is_srgb && s.num_bindings <= 1 &&
           s.num_conversion == AmdGpu::NumberConversion::None;
}

struct StageSpecialization {
'''


def loose_permutations():
    path = BBPORT / 'gpu' / 'shadps4' / 'shader_recompiler' / 'specialization.h'
    text = read(path)
    if 'IsPlainNull2DCompatible' in text:
        if 'BB_ORDER_LOOSE_SHADER' in text:
            print('17. permutasi longgar (slot kosong): sudah dipatch')
            return
        # Versi 1 (semua shader) membuat layar hitam saat boot: batasi ke satu shader.
        v1_helper = PERM_HELPER_V1.split('struct StageSpecialization {')[0]
        v2_helper = PERM_HELPER.split('struct StageSpecialization {')[0]
        v1_call = 'if (!bitset[slot] && IsPlainNull2DCompatible(other.images[i])) {'
        v2_call = 'if (!bitset[slot] && IsPlainNull2DCompatible(other.images[i], info ? info->pgm_hash : 0)) {'
        if text.count(v1_helper) != 1 or text.count(v1_call) != 1:
            sys.exit('permutasi longgar: versi lama tidak dikenali')
        write(path, text.replace(v1_helper, v2_helper, 1).replace(v1_call, v2_call, 1))
        print('17. permutasi longgar: sekarang hanya untuk shader 0x804aeead (BB_ORDER_LOOSE_SHADER)')
        return
    if text.count(PERM_LOOP_OLD) != 1 or text.count(PERM_HELPER_ANCHOR) != 1:
        sys.exit('permutasi longgar: titik sisip tidak ditemukan')
    text = text.replace(PERM_HELPER_ANCHOR, PERM_HELPER, 1).replace(PERM_LOOP_OLD, PERM_LOOP_NEW, 1)
    if '#include <cstdlib>' not in text:
        text = text.replace('#pragma once\n', '#pragma once\n\n#include <cstdlib>\n', 1)
    write(path, text)
    print('17. permutasi: slot kosong melayani texture 2D biasa (BB_ORDER_STRICT_PERM=1: aturan lama)')


# --- 18. Percobaan: lewati dispatch satu compute shader (BB_ORDER_SKIP_SHADER=hex, bawaan mati) ---
SKIP_OLD = '''    const auto cs_params = AmdGpu::GetParams(cs_pgm);
    std::tie(sel.infos[0], sel.modules[0], sel.fetch_shader, compute_key.value) ='''
SKIP_NEW = '''    const auto cs_params = AmdGpu::GetParams(cs_pgm);
    // bbport-order: percobaan diagnosa. BB_ORDER_SKIP_SHADER=804aeead melewati dispatch compute
    // shader itu (tanpa compile) untuk melihat apakah stutter hilang dan apa yang rusak.
    static const u64 skip_hash = [] {
        const char* e = std::getenv("BB_ORDER_SKIP_SHADER");
        return e ? u64(std::strtoull(e, nullptr, 16)) : u64(0);
    }();
    if (skip_hash != 0 && cs_params.hash == skip_hash) {
        return false;
    }
    std::tie(sel.infos[0], sel.modules[0], sel.fetch_shader, compute_key.value) ='''


def skip_compute():
    path = BBPORT / 'gpu' / 'shadps4' / 'video_core' / 'renderer_vulkan' / 'vk_pipeline_cache.cpp'
    text = read(path)
    if 'BB_ORDER_SKIP_SHADER' in text:
        print('18. lewati compute shader (percobaan): sudah dipatch')
        return
    if text.count(SKIP_OLD) != 1:
        sys.exit('lewati compute: titik sisip tidak ditemukan')
    write(path, text.replace(SKIP_OLD, SKIP_NEW, 1))
    print('18. lewati compute shader: BB_ORDER_SKIP_SHADER=804aeead (bawaan mati)')


# --- 19. Shader 0x804aeead: hanya texture 2D; selain itu (1D/3D/cube/MSAA/array) dianggap kosong ---
FLAT_HELPER_ANCHOR = 'static constexpr u32 NUM_USER_DATA_REGS = 16;\n'
FLAT_HELPER = '''/// bbport-order: compute shader The Order 0x804aeead mengambil sampel dari +-30 texture per dispatch
/// dengan tipe acak (1D/2D/3D/cube/MSAA) -> ratusan permutasi dan stutter. Untuk shader ini hanya
/// texture 2D yang dipakai; tipe lain dibaca sebagai T# kosong (sampel 0) di SEMUA tahap (spesialisasi,
/// recompiler, binding), jadi cukup satu permutasi. BB_ORDER_FLAT2D_SHADER=hex (0 = mati).
inline bool BbOrderFlat2D(u64 pgm_hash) {
    static const u64 only = [] {
        const char* e = std::getenv("BB_ORDER_FLAT2D_SHADER");
        return e ? u64(std::strtoull(e, nullptr, 16)) : u64(0x804aeead);
    }();
    return only != 0 && pgm_hash == only;
}

static constexpr u32 NUM_USER_DATA_REGS = 16;
'''
FLAT_GETSHARP_OLD = '''                image = AmdGpu::Image::Null(true);
            }
        }
        return image;
    }'''
FLAT_GETSHARP_NEW = '''                image = AmdGpu::Image::Null(true);
            }
        }
        if (BbOrderFlat2D(info.pgm_hash) && image.base_address != 0 &&
            (image.GetViewType(is_array) != AmdGpu::ImageType::Color2D || image.IsCube())) {
            image = AmdGpu::Image::Null(is_depth); // bbport-order: lihat BbOrderFlat2D
        }
        return image;
    }'''


def flat2d_shader():
    path = BBPORT / 'gpu' / 'shadps4' / 'shader_recompiler' / 'resource.h'
    text = read(path)
    if 'BbOrderFlat2D' in text:
        print('19. shader 0x804aeead hanya 2D: sudah dipatch')
        return
    if text.count(FLAT_HELPER_ANCHOR) != 1 or text.count(FLAT_GETSHARP_OLD) != 1:
        sys.exit('flat 2D: titik sisip resource.h tidak ditemukan')
    text = text.replace(FLAT_HELPER_ANCHOR, FLAT_HELPER, 1).replace(FLAT_GETSHARP_OLD, FLAT_GETSHARP_NEW, 1)
    if '#include <cstdlib>' not in text:
        text = text.replace('#pragma once\n', '#pragma once\n\n#include <cstdlib>\n', 1)
    write(path, text)
    print('19. shader 0x804aeead: texture non-2D dianggap kosong (BB_ORDER_FLAT2D_SHADER=0: mati)')


# --- 20. Dari DmC (dmc_windows_patch.py): SearchBinaryInfo hanya percaya offset vcc_hi di dalam jendela ---
SBI_OLD = '''    if (code[0] == token_mov_vcchi) {
        const auto* info = std::bit_cast<const BinaryInfo*>(code + (code[1] + 1) * 2);'''
SBI_NEW = '''    // bbport-dmc (dibawa ke order1886): offset di literal hanya dipercaya di dalam jendela pencarian;
    // offset palsu (DmC di Windows: baca di luar memori guest) jatuh ke pencarian biasa.
    if (code[0] == token_mov_vcchi && (u64(code[1]) + 1) * 2 < 0x4000) {
        const auto* info = std::bit_cast<const BinaryInfo*>(code + (code[1] + 1) * 2);'''


def search_binary_info():
    path = BBPORT / 'gpu' / 'shadps4' / 'video_core' / 'amdgpu' / 'regs_shader.h'
    text = read(path)
    if '(u64(code[1]) + 1) * 2 < 0x4000' in text:
        print('20. SearchBinaryInfo (dari DmC): sudah dipatch')
        return
    if text.count(SBI_OLD) != 1:
        sys.exit('SearchBinaryInfo: titik sisip tidak ditemukan')
    write(path, text.replace(SBI_OLD, SBI_NEW, 1))
    print('20. SearchBinaryInfo: perbaikan DmC dibawa ke order1886')


# --- 21. Batas ukuran texture 1 GiB -> 256 MiB (texture sampah 16384x16384 + mip lolos di 1 GiB) ---
SIZE21_OLD = '    return bytes <= (u64(1) << 30) && t.Address() >= (u64(1) << 28);'
SIZE21_NEW = ('    // bbport-order (21): 256 MiB = texture 8192x8192 RGBA8; 1 GiB meloloskan T# sampah 16384x16384\n'
              '    // yang dengan mip menjadi +-1,6 GB (freeze: "1 images registered, 1635 MB image uploads").\n'
              '    return bytes <= (u64(1) << 28) && t.Address() >= (u64(1) << 28);')


def image_size_256():
    path = BBPORT / 'gpu' / 'shadps4' / 'video_core' / 'renderer_vulkan' / 'vk_rasterizer.cpp'
    text = read(path)
    if 'bbport-order (21)' in text:
        print('21. batas texture 256 MiB: sudah dipatch')
        return
    if text.count(SIZE21_OLD) != 1:
        sys.exit('batas texture: titik sisip tidak ditemukan (bagian 14 harus sudah terpasang)')
    write(path, text.replace(SIZE21_OLD, SIZE21_NEW, 1))
    print('21. batas ukuran texture: 1 GiB -> 256 MiB')


# --- 22. Diagnosa: catat setiap image > 256 MiB yang didaftarkan texture cache ---
REG_OLD = '''    image.flags |= ImageFlagBits::Registered;
    ++registry_generation;'''
REG_NEW = '''    image.flags |= ImageFlagBits::Registered;
    ++registry_generation;
    if (image.info.guest_size > (256u << 20)) { // bbport-order: asal image raksasa (freeze)
        static std::atomic<u32> told{0};
        if (told.fetch_add(1) < 16) {
            LOG_WARNING(Render_Vulkan,
                        "bbport-order: image raksasa {} MB di {:#x}: {}x{}x{} pitch {} layer {} mip {} "
                        "sampel {} format {} tipe {} tile {} depth {}",
                        image.info.guest_size >> 20, image.info.guest_address, image.info.size.width,
                        image.info.size.height, image.info.size.depth, image.info.pitch,
                        image.info.resources.layers, image.info.resources.levels,
                        image.info.num_samples, vk::to_string(image.info.pixel_format),
                        u32(image.info.type), u32(image.info.tile_mode), u32(image.info.props.is_depth));
        }
    }'''


def giant_image_log():
    path = BBPORT / 'gpu' / 'shadps4' / 'video_core' / 'texture_cache' / 'texture_cache.cpp'
    text = read(path)
    if 'asal image raksasa' in text:
        print('22. log image raksasa: sudah dipatch')
        return
    if text.count(REG_OLD) != 1:
        sys.exit('log image raksasa: titik sisip tidak ditemukan')
    text = text.replace(REG_OLD, REG_NEW, 1)
    if '#include <atomic>' not in text:
        text = '#include <atomic>\n' + text
    write(path, text)
    print('22. log image raksasa (> 256 MiB) di texture cache')


# --- 23. Aturan 17 & 19 untuk DAFTAR shader material (bukan hanya 0x804aeead) ---
# Log 16 Okt 00:30: setelah 0x804aeead beres, shader material lain (c75dd317, a8792bbb, 8c8a4817,
# ad441fb1) meledak dengan pola sama (slot kosong/terisi, tipe 1D/2D/cube acak) -> 15-25 compile/s, 2-4 FPS.
ORDER_SHADERS = '804aeead,c75dd317,a8792bbb,8c8a4817,ad441fb1'
LIST_HELPER_ANCHOR = '/// bbport-order: compute shader The Order 0x804aeead mengambil sampel'
LIST_HELPER = '''/// bbport-order: daftar hash shader dari env (hex, dipisah koma; "0" = kosong), bawaan = shader
/// material The Order yang diketahui meledak permutasinya.
inline bool BbOrderHashListed(const char* env, u64 pgm_hash) {
    struct List {
        u64 h[32]{};
        u32 n = 0;
    };
    static List lists[2];
    static const char* names[2] = {"BB_ORDER_LOOSE_SHADER", "BB_ORDER_FLAT2D_SHADER"};
    static const bool ready = [] {
        for (int k = 0; k < 2; k++) {
            const char* e = std::getenv(names[k]);
            const char* p = e ? e : "%s";
            while (*p && lists[k].n < 32) {
                char* end = nullptr;
                const u64 v = std::strtoull(p, &end, 16);
                if (end == p) {
                    break;
                }
                if (v != 0) {
                    lists[k].h[lists[k].n++] = v;
                }
                p = (*end == ',') ? end + 1 : end;
            }
        }
        return true;
    }();
    (void)ready;
    const List& l = lists[env[9] == 'L' ? 0 : 1]; // "BB_ORDER_L..." atau "BB_ORDER_F..."
    for (u32 i = 0; i < l.n; i++) {
        if (l.h[i] == pgm_hash) {
            return true;
        }
    }
    return false;
}

''' % ORDER_SHADERS
FLAT_ONLY_OLD = '''    static const u64 only = [] {
        const char* e = std::getenv("BB_ORDER_FLAT2D_SHADER");
        return e ? u64(std::strtoull(e, nullptr, 16)) : u64(0x804aeead);
    }();
    return only != 0 && pgm_hash == only;'''
FLAT_ONLY_NEW = '''    return BbOrderHashListed("BB_ORDER_FLAT2D_SHADER", pgm_hash);'''
LOOSE_ONLY_OLD = '''    static const u64 only = [] {
        const char* e = std::getenv("BB_ORDER_LOOSE_SHADER");
        return e ? u64(std::strtoull(e, nullptr, 16)) : u64(0x804aeead);
    }();
    return !strict && only != 0 && pgm_hash == only && s.type'''
LOOSE_ONLY_NEW = '''    return !strict && BbOrderHashListed("BB_ORDER_LOOSE_SHADER", pgm_hash) && s.type'''


def shader_list():
    res = BBPORT / 'gpu' / 'shadps4' / 'shader_recompiler' / 'resource.h'
    spec = BBPORT / 'gpu' / 'shadps4' / 'shader_recompiler' / 'specialization.h'
    rt, st = read(res), read(spec)
    if 'BbOrderHashListed' in rt and 'BbOrderHashListed' in st:
        print('23. daftar shader material: sudah dipatch')
        return
    if rt.count(LIST_HELPER_ANCHOR) != 1 or rt.count(FLAT_ONLY_OLD) != 1 or st.count(LOOSE_ONLY_OLD) != 1:
        sys.exit('daftar shader: titik sisip tidak ditemukan (bagian 17/19 belum terpasang?)')
    rt = rt.replace(LIST_HELPER_ANCHOR, LIST_HELPER + LIST_HELPER_ANCHOR, 1).replace(FLAT_ONLY_OLD, FLAT_ONLY_NEW, 1)
    st = st.replace(LOOSE_ONLY_OLD, LOOSE_ONLY_NEW, 1)
    write(res, rt)
    write(spec, st)
    print('23. aturan 17 & 19 untuk shader material: ' + ORDER_SHADERS)


def perm_log_cap():
    path = BBPORT / 'gpu' / 'shadps4' / 'video_core' / 'renderer_vulkan' / 'vk_pipeline_cache.cpp'
    text = read(path)
    old = 'if (perm_idx < 3 || told.fetch_add(1) >= 60) {'
    new = 'if (perm_idx < 3 || told.fetch_add(1) >= 400) { // bbport-order: batas log 60 -> 400'
    if new in text:
        print('23b. batas log permutasi 400: sudah dipatch')
        return
    if text.count(old) != 1:
        sys.exit('batas log permutasi: titik sisip tidak ditemukan')
    write(path, text.replace(old, new, 1))
    print('23b. batas log permutasi 60 -> 400 (untuk menemukan shader lain yang meledak)')


# --- 24. Shader material: texture integer (Uint/Sint) juga dianggap kosong ---
# Sesudah bagian 23 sisa permutasi c75dd317 dkk. hanya karena "int false<->true": slot kosong
# (Image::Null = float) tidak bisa melayani texture integer. BB_ORDER_FLAT_INT=0 mematikan.
FLAT_INT_OLD = '''            (image.GetViewType(is_array) != AmdGpu::ImageType::Color2D || image.IsCube())) {'''
FLAT_INT_NEW = '''            (image.GetViewType(is_array) != AmdGpu::ImageType::Color2D || image.IsCube() ||
             (BbOrderFlatInt() && AmdGpu::IsInteger(image.GetNumberFmt())))) {'''
FLAT_INT_HELPER_ANCHOR = 'inline bool BbOrderFlat2D(u64 pgm_hash) {'
FLAT_INT_HELPER = '''/// bbport-order (24): texture integer di shader material juga dianggap kosong (BB_ORDER_FLAT_INT=0: mati).
inline bool BbOrderFlatInt() {
    static const bool on = [] {
        const char* e = std::getenv("BB_ORDER_FLAT_INT");
        return !e || e[0] != '0';
    }();
    return on;
}

'''


def flat_integer():
    path = BBPORT / 'gpu' / 'shadps4' / 'shader_recompiler' / 'resource.h'
    text = read(path)
    if 'BbOrderFlatInt' in text:
        print('24. shader material: texture integer kosong: sudah dipatch')
        return
    if text.count(FLAT_INT_OLD) != 1 or text.count(FLAT_INT_HELPER_ANCHOR) != 1:
        sys.exit('texture integer: titik sisip tidak ditemukan (bagian 19 harus sudah terpasang)')
    text = text.replace(FLAT_INT_HELPER_ANCHOR, FLAT_INT_HELPER + FLAT_INT_HELPER_ANCHOR, 1)
    text = text.replace(FLAT_INT_OLD, FLAT_INT_NEW, 1)
    if 'video_core/amdgpu/pixel_format.h' not in text:
        text = text.replace('#include "video_core/amdgpu/resource.h"\n',
                            '#include "video_core/amdgpu/pixel_format.h"\n#include "video_core/amdgpu/resource.h"\n', 1)
    write(path, text)
    print('24. shader material: texture integer dianggap kosong (BB_ORDER_FLAT_INT=0: mati)')


# --- 25. Ukuran T# dihitung dengan pitch + padding tile (freeze 16 Okt 00:40) ---
# Log: "image raksasa 1215 MB: 60x25 pitch 10945 layer 3953 R8Unorm tile 14". Hitungan lama
# (lebar x tinggi x layer) hanya +-6 MB sehingga lolos, padahal texture cache memakai pitch -> 1,2 GB.
SIZE25_OLD = '    return bytes <= (u64(1) << 28) && t.Address() >= (u64(1) << 28);'
SIZE25_NEW = ('''    // bbport-order (25): perkiraan memakai pitch dan padding tile; T# sampah 60x25 pitch 10945,
    // 3953 layer (1,2 GB di texture cache) membuat game freeze.
    const u64 row = std::max<u64>(u64(t.width) + 1, t.Pitch());
    const u64 padded = ((row + 63) & ~u64(63)) * ((u64(t.height) + 8) & ~u64(7)) * slices *
                       (bits ? bits : 32) / 8;
    return bytes <= (u64(1) << 28) && padded <= (u64(1) << 29) && t.Address() >= (u64(1) << 28);''')


def image_size_pitch():
    path = BBPORT / 'gpu' / 'shadps4' / 'video_core' / 'renderer_vulkan' / 'vk_rasterizer.cpp'
    text = read(path)
    if 'bbport-order (25)' in text:
        print('25. ukuran texture dengan pitch: sudah dipatch')
        return
    if text.count(SIZE25_OLD) != 1:
        sys.exit('ukuran pitch: titik sisip tidak ditemukan (bagian 21 harus sudah terpasang)')
    write(path, text.replace(SIZE25_OLD, SIZE25_NEW, 1))
    print('25. ukuran texture memakai pitch + padding (batas 512 MiB)')


# --- 26. T# ditolak bila ukuran SEBENARNYA (guest_size hitungan texture cache) > 512 MiB ---
# Log 00:52: "image raksasa 1920 MB: 8x8 pitch 10945 layer 2048 BC3" dan "343 MB 512x512 pitch 719
# layer 512" masih lolos perkiraan bagian 25. Pakai ukuran dari ImageInfo itu sendiri.
GUEST_OLD = '''        auto& desc_entry =
            prepared ? CachedImageDescEntry(tsharp, image_desc, prepared->image_hashes[image_index])
                     : CachedImageDescEntry(tsharp, image_desc);
'''
GUEST_NEW = GUEST_OLD + '''        if (desc_entry.desc.info.guest_size > (512u << 20)) { // bbport-order (26): T# sampah
            static std::atomic<u32> told{0};
            if (told.fetch_add(1) < 8) {
                LOG_WARNING(Render_Vulkan,
                            "bbport-order: T# raksasa ditolak {} MB di {:#x}: {}x{} pitch {} layer {} "
                            "data_format {}",
                            desc_entry.desc.info.guest_size >> 20, tsharp.Address(), tsharp.width + 1,
                            tsharp.height + 1, tsharp.Pitch(), tsharp.NumLayers(), u32(data_fmt));
            }
            image_bindings.emplace_back(VideoCore::ImageId{}, &image_desc_storage.emplace_back());
            image_binding_entries.push_back(nullptr);
            binding_proxy_ok.push_back(false);
            image_descriptor_array_sizes.push_back(1);
            continue;
        }
'''


def guest_size_guard():
    path = BBPORT / 'gpu' / 'shadps4' / 'video_core' / 'renderer_vulkan' / 'vk_rasterizer.cpp'
    text = read(path)
    if 'bbport-order (26)' in text:
        print('26. T# raksasa (guest_size): sudah dipatch')
        return
    if text.count(GUEST_OLD) != 1:
        sys.exit('T# raksasa: titik sisip tidak ditemukan')
    if '#include <atomic>' not in text:
        text = '#include <atomic>\n' + text
    write(path, text.replace(GUEST_OLD, GUEST_NEW, 1))
    print('26. T# dengan guest_size > 512 MiB ditolak (ukuran hitungan texture cache)')


# --- 27. Matematika "legacy" GCN: MAD/MAC_LEGACY (0 * x = 0) dan RSQ_CLAMP (tanpa inf) ---
# Bintik hitam yang bergerak di wajah = NaN di shading kulit yang menyebar lewat filter temporal.
# shadPS4 menerjemahkan V_MAD_LEGACY_F32/V_MAC_LEGACY_F32 sebagai MAD biasa (0 * inf = NaN, di PS4 = 0)
# dan V_RSQ_CLAMP_F32 tanpa clamp (rsq(0) = inf, di PS4 = +-FLT_MAX).
LEGACY_MAC_OLD = """    case Opcode::V_MAC_LEGACY_F32:
        return V_MAC_F32(inst);"""
LEGACY_MAC_NEW = """    case Opcode::V_MAC_LEGACY_F32: { // bbport-order (27): legacy, 0 * x = +0 (juga NaN/inf)
        const IR::F32 a{GetSrc<IR::F32>(inst.src[0])};
        const IR::F32 b{GetSrc<IR::F32>(inst.src[1])};
        const IR::F32 acc{GetSrc<IR::F32>(inst.dst[0])};
        const IR::F32 zero{ir.Imm32(0.0f)};
        const IR::U1 any_zero{ir.LogicalOr(ir.FPEqual(a, zero), ir.FPEqual(b, zero))};
        SetDst(inst.dst[0], ir.FPAdd(IR::F32{ir.Select(any_zero, zero, ir.FPMul(a, b))}, acc));
        return;
    }"""
LEGACY_MAD_OLD = """    case Opcode::V_MAD_LEGACY_F32:
        return V_MAD_F32(inst);"""
LEGACY_MAD_NEW = """    case Opcode::V_MAD_LEGACY_F32: { // bbport-order (27): legacy, 0 * x = +0 (juga NaN/inf)
        const IR::F32 a{GetSrc<IR::F32>(inst.src[0])};
        const IR::F32 b{GetSrc<IR::F32>(inst.src[1])};
        const IR::F32 c{GetSrc<IR::F32>(inst.src[2])};
        const IR::F32 zero{ir.Imm32(0.0f)};
        const IR::U1 any_zero{ir.LogicalOr(ir.FPEqual(a, zero), ir.FPEqual(b, zero))};
        SetDst(inst.dst[0], ir.FPAdd(IR::F32{ir.Select(any_zero, zero, ir.FPMul(a, b))}, c));
        return;
    }"""
RSQ_CLAMP_OLD = """    case Opcode::V_RSQ_CLAMP_F32:
        return V_RSQ_F32(inst);"""
RSQ_CLAMP_NEW = """    case Opcode::V_RSQ_CLAMP_F32: { // bbport-order (27): hasil di-clamp ke +-FLT_MAX (tanpa inf)
        const IR::F32 r{ir.FPRecipSqrt(GetSrc<IR::F32>(inst.src[0]))};
        SetDst(inst.dst[0], ir.FPClamp(r, ir.Imm32(-3.402823466e+38f), ir.Imm32(3.402823466e+38f)));
        return;
    }"""


LEGACY_HELPER_ANCHOR = 'namespace Shader::Gcn {\n'
LEGACY_HELPER = """namespace Shader::Gcn {

// bbport-order (27b): BB_ORDER_LEGACY berisi huruf: d = V_MAD_LEGACY, c = V_MAC_LEGACY, r = V_RSQ_CLAMP.
// Semua aktif bersamaan membuat layar hitam saat boot (16 Okt 01:30), jadi bawaan mati.
static bool BbOrderLegacy(char k) {
    static const char* e = std::getenv("BB_ORDER_LEGACY");
    return e != nullptr && std::strchr(e, k) != nullptr;
}
"""
LEGACY_GATES = [
    ("    case Opcode::V_MAC_LEGACY_F32: { // bbport-order (27): legacy, 0 * x = +0 (juga NaN/inf)\n",
     "        if (!BbOrderLegacy('c')) return V_MAC_F32(inst);\n"),
    ("    case Opcode::V_MAD_LEGACY_F32: { // bbport-order (27): legacy, 0 * x = +0 (juga NaN/inf)\n",
     "        if (!BbOrderLegacy('d')) return V_MAD_F32(inst);\n"),
    ("    case Opcode::V_RSQ_CLAMP_F32: { // bbport-order (27): hasil di-clamp ke +-FLT_MAX (tanpa inf)\n",
     "        if (!BbOrderLegacy('r')) return V_RSQ_F32(inst);\n"),
]


def legacy_math():
    path = BBPORT / 'gpu' / 'shadps4' / 'shader_recompiler' / 'frontend' / 'translate' / 'vector_alu.cpp'
    text = read(path)
    if 'bbport-order (27b)' in text:
        print('27. matematika legacy (BB_ORDER_LEGACY=dcr): sudah dipatch')
        return
    if 'bbport-order (27)' not in text:
        for old in (LEGACY_MAC_OLD, LEGACY_MAD_OLD, RSQ_CLAMP_OLD):
            if text.count(old) != 1:
                sys.exit('matematika legacy: titik sisip tidak ditemukan')
        text = (text.replace(LEGACY_MAC_OLD, LEGACY_MAC_NEW, 1).replace(LEGACY_MAD_OLD, LEGACY_MAD_NEW, 1)
                .replace(RSQ_CLAMP_OLD, RSQ_CLAMP_NEW, 1))
    # 27b: tiap perbaikan hanya aktif lewat BB_ORDER_LEGACY (versi 27 tanpa saklar = layar hitam)
    if text.count(LEGACY_HELPER_ANCHOR) != 1:
        sys.exit('matematika legacy: namespace tidak ditemukan')
    for head, gate in LEGACY_GATES:
        if text.count(head) != 1:
            sys.exit('matematika legacy: blok 27 tidak dikenali')
        text = text.replace(head, head + gate, 1)
    text = text.replace(LEGACY_HELPER_ANCHOR, LEGACY_HELPER, 1)
    for inc in ('#include <cstdlib>', '#include <cstring>'):
        if inc not in text:
            text = inc + '\n' + text
    write(path, text)
    print('27. matematika legacy: saklar BB_ORDER_LEGACY (d=MAD, c=MAC, r=RSQ_CLAMP), bawaan mati')


# --- 28. SRT walker: Phi dinamis (indeks loop) -> pakai nilai AWAL loop (BB_ORDER_PHI_INIT=1) ---
# Bintik hitam di wajah tidak berubah oleh bagian 27 (bukan NaN). Dugaan berikut: decal darah/kotoran
# membaca descriptor/konstanta lewat indeks loop (Phi dinamis); bagian 11 mengisinya 0 -> warna/texture
# kosong -> hitam. Percobaan: Phi dihitung dengan nilai awalnya (biasanya imm, mis. i = 0), jadi elemen
# pertama yang dipakai untuk semua iterasi (decal biasanya satu atlas texture yang sama).
PHI_INIT_OLD = """        LOG_ERROR(Render_Recompiler, "Unexpected instruction for offset computation, Phi (dinamis)");
        return false;"""
PHI_INIT_NEW = """        if (BbOrderPhiInit()) { // bbport-order (28): nilai awal loop
            if (const auto init = PhiInitialImmediate(inst)) {
                c.mov(reg, *init);
                return true;
            }
        }
        LOG_ERROR(Render_Recompiler, "Unexpected instruction for offset computation, Phi (dinamis)");
        return false;"""
PHI_INIT_HELPER_ANCHOR = 'static bool IsAllowedOffsetInstruction(const IR::Inst* inst) {'
PHI_INIT_HELPER = """// bbport-order (28): BB_ORDER_PHI_INIT=1 -> Phi dinamis memakai argumen immediate pertamanya
// (nilai awal loop, mis. i = 0). Bawaan mati.
static bool BbOrderPhiInit() {
    static const bool on = [] {
        const char* e = std::getenv("BB_ORDER_PHI_INIT");
        return e != nullptr && e[0] == '1';
    }();
    return on;
}

static std::optional<u32> PhiInitialImmediate(IR::Inst* phi) {
    std::vector<IR::Inst*> stack{phi};
    std::vector<IR::Inst*> seen{phi};
    while (!stack.empty()) {
        IR::Inst* p = stack.back();
        stack.pop_back();
        for (size_t i = 0; i < p->NumArgs(); ++i) {
            const IR::Value arg = p->Arg(i);
            if (arg.IsEmpty()) {
                continue;
            }
            if (arg.IsImmediate()) {
                if (arg.Type() == IR::Type::U32) {
                    return arg.U32();
                }
                continue;
            }
            if (arg.Inst()->GetOpcode() == IR::Opcode::Phi &&
                std::ranges::find(seen, arg.Inst()) == seen.end() && seen.size() < 64) {
                seen.push_back(arg.Inst());
                stack.push_back(arg.Inst());
            }
        }
    }
    return std::nullopt;
}

static bool IsAllowedOffsetInstruction(const IR::Inst* inst) {"""


def phi_initial_value():
    path = BBPORT / 'gpu' / 'shadps4' / 'shader_recompiler' / 'ir' / 'passes' / 'flatten_extended_userdata_pass.cpp'
    text = read(path)
    if 'bbport-order (28)' in text:
        print('28. SRT Phi dinamis -> nilai awal (BB_ORDER_PHI_INIT=1): sudah dipatch')
        return
    if text.count(PHI_INIT_OLD) != 1 or text.count(PHI_INIT_HELPER_ANCHOR) != 1:
        sys.exit('Phi nilai awal: titik sisip tidak ditemukan (bagian 10 harus sudah terpasang)')
    text = text.replace(PHI_INIT_HELPER_ANCHOR, PHI_INIT_HELPER, 1).replace(PHI_INIT_OLD, PHI_INIT_NEW, 1)
    if '#include <cstdlib>' not in text:
        text = '#include <cstdlib>\n' + text
    write(path, text)
    print('28. SRT Phi dinamis -> nilai awal loop, saklar BB_ORDER_PHI_INIT=1 (bawaan mati)')


# --- 29. Diagnosa: T# selebar layar (>= 512 px) yang ditolak, lengkap dengan alasan (16 Okt 13:15) ---
# Di 1440p muncul kedipan pixel pink; log 1440p menolak T# 2560/1280 px RGBA16F (pitch 10945).
# Log lama hanya mencetak pitch/width mentah. Bagian ini mencetak tinggi, layer, tipe, tile, mip
# dan cek mana yang gagal (map/format/tile/ukuran), maksimal 64 baris per run.
REJECT29_OLD = '''            LOG_WARNING(Render_Vulkan,
                        "Rejecting invalid T# address={:#x}, pitch={}, width={}, "
                        "data_format={}, num_format={}",'''
REJECT29_NEW = '''            if (u32(tsharp.width) + 1 >= 512) { // bbport-order (29): diagnosa T# lebar yang ditolak
                static std::atomic<u32> told29{0};
                if (told29.fetch_add(1) < 64) {
                    LOG_WARNING(Render_Vulkan,
                                "bbport-order (29): T# lebar ditolak {:#x}: {}x{} pitch {} depth {} "
                                "layer {} array {}..{} type {} tile {} fmt {}/{} mip {}..{} pow2pad {} | "
                                "map={} fmt_ok={} tile_ok={} size_ok={}",
                                tsharp.Address(), u32(tsharp.width) + 1, u32(tsharp.height) + 1,
                                tsharp.Pitch(), u32(tsharp.depth) + 1, tsharp.NumLayers(),
                                u32(tsharp.base_array), u32(tsharp.last_array), u32(tsharp.GetType()),
                                u32(tsharp.GetTileMode()), u32(data_fmt), u32(num_fmt),
                                u32(tsharp.base_level), u32(tsharp.last_level), u32(tsharp.pow2pad),
                                memory->IsValidGpuMapping(tsharp.Address(), 0),
                                IsKnownFormat(data_fmt, num_fmt), IsKnownTileMode(tsharp.GetTileMode()),
                                IsPlausibleImageSize(tsharp));
                }
            }
''' + REJECT29_OLD


def wide_reject_log():
    path = BBPORT / 'gpu' / 'shadps4' / 'video_core' / 'renderer_vulkan' / 'vk_rasterizer.cpp'
    text = read(path)
    if 'bbport-order (29)' in text:
        print('29. log T# lebar yang ditolak: sudah dipatch')
        return
    if text.count(REJECT29_OLD) != 1:
        sys.exit('log T# lebar: titik sisip tidak ditemukan')
    write(path, text.replace(REJECT29_OLD, REJECT29_NEW, 1))
    print('29. log T# lebar (>= 512 px) yang ditolak + alasannya (maks 64 baris)')


# --- 30. Percobaan pita pink 1440p/4K: render target baru tidak diisi dari memori (16 Okt 13:45) ---
# GpuStack dipakai bergantian: target baru di alamat target lama (format/ukuran lain). Saat dibuat,
# texture cache mengunggah isi memori itu (data format lain = blok pink/hijau). Tata letak sama
# persis dengan heap 1164 MB maupun 2046 MB, jadi bukan soal ukuran heap.
# BB_ORDER_RT_NOREFRESH=1: image besar (>= 1280x720) bertile 14 (render target) yang BELUM pernah
# digambar GPU (bukan GpuModified) dilewati unggahannya. Bawaan mati.
NOREFRESH_OLD = '''void TextureCache::RefreshImage(Image& image) {
    WatchImage(image, "refresh entered");
    if (False(image.flags & ImageFlagBits::Dirty) || image.info.num_samples > 1) {
        return;
    }
'''
NOREFRESH_NEW = NOREFRESH_OLD + '''    { // bbport-order (30): render target baru tidak diisi dari memori lama (BB_ORDER_RT_NOREFRESH=1)
        static const bool no_refresh = [] {
            const char* e = std::getenv("BB_ORDER_RT_NOREFRESH");
            return e != nullptr && e[0] == '1';
        }();
        if (no_refresh && False(image.flags & ImageFlagBits::GpuModified) &&
            u32(image.info.tile_mode) == 14 && image.info.size.width >= 1280 &&
            image.info.size.height >= 720) {
            static std::atomic<u32> told30{0};
            if (told30.fetch_add(1) < 32) {
                std::printf("bbport-order (30): unggahan dilewati %#llx %ux%u fmt %u flags %#x\\n",
                            (unsigned long long)image.info.guest_address, image.info.size.width,
                            image.info.size.height, u32(image.info.pixel_format), u32(image.flags));
            }
            image.flags &= ~ImageFlagBits::Dirty;
            return;
        }
    }
'''


# --- 31. Pita pink 1440p/4K: tulisan CPU di dalam render target layar (16 Okt 14:10) ---
# Rekaman frame 1440p: target akhir LDR 0x105be50000 (R8G8B8A8Srgb 2560x1440, pass tonemap) menutupi
# area konstanta per-frame yang ditulis CPU (+0x8e3997, +0x81f528, +0xcc8791 di 0x105c1bec10..
# 0x105c1d2414, +3,6 MB dari awal target = baris ~352 = posisi pita di screenshot). Di 900p/1080p
# area itu tidak tertutup target. Setiap tulisan CPU membuat texture cache menandai target CpuDirty
# lalu mengunggah ulang 15 MB memori guest (bukan hasil GPU) -> pita sampah. Di PS4 asli tulisan
# kecil itu langsung ditimpa pass tonemap berikutnya.
# BB_ORDER_RT_IGNORE_CPU=1: tulisan CPU ke render target besar (tile 14, >= 1280x720) yang sudah
# digambar GPU tidak membuat target kotor; halaman hanya dibuka proteksinya. Bawaan mati.
IGNCPU_OLD = '''        if (image.Overlaps(addr, size)) {
            // Modified region overlaps image, so the image was definitely accessed by this fault.
            // Untrack the image, so that the range is unprotected and the guest can write freely.
            image.flags |= ImageFlagBits::CpuDirty;'''
IGNCPU_NEW = '''        if (image.Overlaps(addr, size)) {
            { // bbport-order (31): tulisan CPU di dalam render target layar (BB_ORDER_RT_IGNORE_CPU=1)
                static const bool ignore_cpu = [] {
                    const char* e = std::getenv("BB_ORDER_RT_IGNORE_CPU");
                    return e != nullptr && e[0] == '1';
                }();
                if (ignore_cpu && True(image.flags & ImageFlagBits::GpuModified) &&
                    u32(image.info.tile_mode) == 14 && image.info.size.width >= 1280 &&
                    image.info.size.height >= 720) {
                    static std::atomic<u32> told31{0};
                    if (told31.fetch_add(1) < 32) {
                        std::printf("bbport-order (31): tulisan CPU %#llx+%#zx di target %#llx %ux%u "
                                    "fmt %u diabaikan\\n",
                                    (unsigned long long)addr, size,
                                    (unsigned long long)image.info.guest_address,
                                    image.info.size.width, image.info.size.height,
                                    u32(image.info.pixel_format));
                    }
                    UntrackImage(image_id);
                    return;
                }
            }
            // Modified region overlaps image, so the image was definitely accessed by this fault.
            // Untrack the image, so that the range is unprotected and the guest can write freely.
            image.flags |= ImageFlagBits::CpuDirty;'''


def rt_ignore_cpu():
    path = BBPORT / 'gpu' / 'shadps4' / 'video_core' / 'texture_cache' / 'texture_cache.cpp'
    text = read(path)
    if 'bbport-order (31)' in text:
        print('31. tulisan CPU di render target layar: sudah dipatch')
        return
    if text.count(IGNCPU_OLD) != 1:
        sys.exit('tulisan CPU di render target: titik sisip tidak ditemukan')
    for inc in ('#include <cstdio>', '#include <cstdlib>'):
        if inc not in text:
            text = inc + '\n' + text
    write(path, text.replace(IGNCPU_OLD, IGNCPU_NEW, 1))
    print('31. tulisan CPU di render target layar diabaikan, saklar BB_ORDER_RT_IGNORE_CPU=1 (bawaan mati)')


def rt_no_refresh():
    path = BBPORT / 'gpu' / 'shadps4' / 'video_core' / 'texture_cache' / 'texture_cache.cpp'
    text = read(path)
    if 'bbport-order (30)' in text:
        print('30. render target baru tanpa unggahan: sudah dipatch')
        return
    if text.count(NOREFRESH_OLD) != 1:
        sys.exit('render target tanpa unggahan: titik sisip tidak ditemukan')
    for inc in ('#include <cstdio>', '#include <cstdlib>'):
        if inc not in text:
            text = inc + '\n' + text
    write(path, text.replace(NOREFRESH_OLD, NOREFRESH_NEW, 1))
    print('30. render target baru tanpa unggahan, saklar BB_ORDER_RT_NOREFRESH=1 (bawaan mati)')


# --- 32. 4K: render target kebal terhadap tulisan buffer GPU yang menumpang (16 Okt 18:10) ---
# Di 4K tata letak GpuStack game (dihitung untuk 1080p) membuat render target dan buffer saling
# menumpang. Tulisan buffer GPU yang kebetulan mulai di alamat sebuah render target membuat target itu
# GpuDirty -> diisi ulang dari memori (bukan hasil render) -> karakter hitam / distorsi air liar.
# BB_ORDER_RT_IGNORE_GPUBUF=1: render target besar (tile 14, >= 1280x720) yang sudah digambar GPU
# tidak ditandai GpuDirty oleh tulisan buffer. Bawaan mati.
GPUBUF_OLD = """        // Ensure image is reuploaded when accessed again.
        WatchImage(image, "GPU write (marked for refresh)");
        image.flags |= ImageFlagBits::GpuDirty;"""
GPUBUF_NEW = """        { // bbport-order (32): render target layar kebal tulisan buffer GPU (BB_ORDER_RT_IGNORE_GPUBUF=1)
            static const bool ignore_gpubuf = [] {
                const char* e = std::getenv("BB_ORDER_RT_IGNORE_GPUBUF");
                return e != nullptr && e[0] == '1';
            }();
            if (ignore_gpubuf && True(image.flags & ImageFlagBits::GpuModified) &&
                u32(image.info.tile_mode) == 14 && image.info.size.width >= 1280 &&
                image.info.size.height >= 720) {
                static std::atomic<u32> told32{0};
                if (told32.fetch_add(1) < 32) {
                    std::printf("bbport-order (32): tulisan buffer GPU %#llx di target %ux%u fmt %u "
                                "diabaikan\\n",
                                (unsigned long long)address, image.info.size.width,
                                image.info.size.height, u32(image.info.pixel_format));
                }
                return;
            }
        }
""" + GPUBUF_OLD


def rt_ignore_gpubuf():
    path = BBPORT / 'gpu' / 'shadps4' / 'video_core' / 'texture_cache' / 'texture_cache.cpp'
    text = read(path)
    if 'bbport-order (32)' in text:
        print('32. render target kebal tulisan buffer GPU: sudah dipatch')
        return
    if text.count(GPUBUF_OLD) != 1:
        sys.exit('render target kebal tulisan buffer GPU: titik sisip tidak ditemukan')
    write(path, text.replace(GPUBUF_OLD, GPUBUF_NEW, 1))
    print('32. render target kebal tulisan buffer GPU, saklar BB_ORDER_RT_IGNORE_GPUBUF=1 (bawaan mati)')


# --- 33. Bagian 31 dan 32 juga untuk render target depth (16 Okt 18:15) ---
# 4K in-game: depth 3840x2160 (tile 0, bukan 14) di 0x10629a0000 diisi ulang dari memori SETIAP frame
# (2 GB/s, CpuDirty dari data CPU yang menumpang) -> depth salah = karakter hitam / kedip.
D33_OLD = ("ImageFlagBits::GpuModified) &&\n                    u32(image.info.tile_mode) == 14 &&",
           "ImageFlagBits::GpuModified) &&\n                u32(image.info.tile_mode) == 14 &&")
D33_NEW = ("ImageFlagBits::GpuModified) &&\n                    (u32(image.info.tile_mode) == 14 || image.info.props.is_depth) && "
           "/* bbport-order (33) */",
           "ImageFlagBits::GpuModified) &&\n                (u32(image.info.tile_mode) == 14 || image.info.props.is_depth) && "
           "/* bbport-order (33) */")


def rt_depth_too():
    path = BBPORT / 'gpu' / 'shadps4' / 'video_core' / 'texture_cache' / 'texture_cache.cpp'
    text = read(path)
    if 'bbport-order (33)' in text:
        print('33. bagian 31/32 untuk depth: sudah dipatch')
        return
    for old in D33_OLD:
        if text.count(old) != 1:
            sys.exit('bagian 33: titik sisip tidak ditemukan (bagian 31 dan 32 harus sudah terpasang)')
    for old, new in zip(D33_OLD, D33_NEW):
        text = text.replace(old, new, 1)
    write(path, text)
    print('33. bagian 31/32 juga untuk render target depth')


# --- 34. Bagian 31/32: batas ukuran 1280x720 -> 256x256 (16 Okt 18:20) ---
# 4K in-game sesudah 33: kedip hilang, tapi karakter tetap hitam. Target 512x512 R16G16B16A16 di
# 0x10677d0000 (dan 0x1056dd0000) diisi ulang dari memori ~230x per detik (CpuDirty+GpuModified).
D34_OLD = ("(33) */ image.info.size.width >= 1280 &&\n                    image.info.size.height >= 720)",
           "(33) */ image.info.size.width >= 1280 &&\n                image.info.size.height >= 720)")
D34_NEW = ("(33) */ image.info.size.width >= 256 && /* bbport-order (34) */\n                    image.info.size.height >= 256)",
           "(33) */ image.info.size.width >= 256 && /* bbport-order (34) */\n                image.info.size.height >= 256)")


def rt_small_too():
    path = BBPORT / 'gpu' / 'shadps4' / 'video_core' / 'texture_cache' / 'texture_cache.cpp'
    text = read(path)
    if 'bbport-order (34)' in text:
        print('34. batas ukuran 256x256: sudah dipatch')
        return
    for old in D34_OLD:
        if text.count(old) != 1:
            sys.exit('bagian 34: titik sisip tidak ditemukan (bagian 33 harus sudah terpasang)')
    for old, new in zip(D34_OLD, D34_NEW):
        text = text.replace(old, new, 1)
    write(path, text)
    print('34. bagian 31/32: render target mulai 256x256')


# --- 35. Diagnosa bintik wajah: shader mana yang SRT walker-nya gagal (16 Okt 18:35) ---
# Log lama "Failed to compute offset for SRT walker" (1386x per run) tanpa nomor shader. Sekarang
# nomor shader (pgm_hash) ikut dicatat, supaya bisa dicocokkan dengan pass karakter di rekaman frame.
SRT35_DECL_OLD = "using namespace Xbyak::util;\n"
SRT35_DECL_NEW = SRT35_DECL_OLD + ("// bbport-order (35): shader yang sedang diproses, untuk log kegagalan SRT walker.\n"
                                   "static thread_local unsigned long long bb_order_srt_hash = 0;\n")
SRT35_SET_OLD = """void FlattenExtendedUserdataPass(IR::Program& program) {
    auto& post_order = program.post_order_blocks;
    PassInfo pass_info;
"""
SRT35_SET_NEW = SRT35_SET_OLD + "    bb_order_srt_hash = program.info.pgm_hash; // bbport-order (35)\n"
SRT35_LOG_OLD = 'LOG_ERROR(Render_Recompiler, "Failed to compute offset for SRT walker");'
SRT35_LOG_NEW = ('LOG_ERROR(Render_Recompiler, "Failed to compute offset for SRT walker (shader {:#018x})", '
                 'bb_order_srt_hash);')


def srt_fail_hash():
    path = (BBPORT / 'gpu' / 'shadps4' / 'shader_recompiler' / 'ir' / 'passes' /
            'flatten_extended_userdata_pass.cpp')
    text = read(path)
    if 'bbport-order (35)' in text:
        print('35. nomor shader di log SRT walker: sudah dipatch')
        return
    if (text.count(SRT35_DECL_OLD) != 1 or text.count(SRT35_SET_OLD) != 1 or
            text.count(SRT35_LOG_OLD) != 2):
        sys.exit('bagian 35: titik sisip tidak ditemukan')
    text = text.replace(SRT35_DECL_OLD, SRT35_DECL_NEW, 1).replace(SRT35_SET_OLD, SRT35_SET_NEW, 1)
    write(path, text.replace(SRT35_LOG_OLD, SRT35_LOG_NEW))
    print('35. nomor shader di log kegagalan SRT walker')


# --- 36. Percobaan bintik wajah: lewati draw dengan pixel shader tertentu (16 Okt 18:50) ---
# Screenshot: bintik = tetesan (keringat/air) hitam pekat bertepi tajam di dahi dan hidung. Kandidat:
# pass kecil "3 draws, 204 indices" (~34 quad) dengan ps eb420c6b / bca0d024, keduanya SRT walker gagal.
# BB_ORDER_SKIP_PS=eb420c6b,bca0d024 (hex dipisah koma) melewati draw dengan pixel shader itu.
SKIPPS_OLD = "    bind_stage(HwStage::Fragment, SwStage::Fragment);\n"
SKIPPS_NEW = SKIPPS_OLD + """    { // bbport-order (36): BB_ORDER_SKIP_PS=hex,hex melewati draw dengan pixel shader itu (diagnosa)
        static const std::vector<u64> skip_ps = [] {
            std::vector<u64> out;
            if (const char* e = std::getenv("BB_ORDER_SKIP_PS")) {
                std::string s{e};
                size_t pos = 0;
                while (pos < s.size()) {
                    const size_t comma = s.find(',', pos);
                    const std::string item = s.substr(pos, comma == std::string::npos ? std::string::npos
                                                                                        : comma - pos);
                    if (!item.empty()) {
                        out.push_back(std::strtoull(item.c_str(), nullptr, 16));
                    }
                    if (comma == std::string::npos) {
                        break;
                    }
                    pos = comma + 1;
                }
            }
            return out;
        }();
        if (!skip_ps.empty()) {
            const auto* ps = regs.ProgramForStage(static_cast<u32>(HwStage::Fragment));
            if (ps && ps->Address<u32*>()) {
                const u64 h = AmdGpu::GetParams(*ps).hash;
                if (std::find(skip_ps.begin(), skip_ps.end(), h) != skip_ps.end()) {
                    return false;
                }
            }
        }
    }
"""


def skip_pixel_shader():
    path = BBPORT / 'gpu' / 'shadps4' / 'video_core' / 'renderer_vulkan' / 'vk_pipeline_cache.cpp'
    text = read(path)
    if 'bbport-order (36)' in text:
        print('36. lewati pixel shader (BB_ORDER_SKIP_PS): sudah dipatch')
        return
    if text.count(SKIPPS_OLD) != 1:
        sys.exit('bagian 36: titik sisip tidak ditemukan')
    for inc in ('#include <vector>', '#include <algorithm>'):
        if inc not in text:
            text = inc + '\n' + text
    write(path, text.replace(SKIPPS_OLD, SKIPPS_NEW, 1))
    print('36. lewati draw per pixel shader, saklar BB_ORDER_SKIP_PS=hex,hex (bawaan mati)')


# --- 37. Bintik wajah: indeks texture dari ReadLane/ReadFirstLane -> entri pertama (16 Okt 20:15) ---
# Bisection BB_ORDER_SKIP_PS: pixel shader kulit/wajah = f5c17eec (dilewati -> hanya wajah hitam).
# Shader ini membaca descriptor dari tabel dengan indeks per piksel (pola waterfall v_readfirstlane):
# "Unexpected instruction for offset computation, ReadLane" -> slot texture kosong -> bintik hitam.
# BB_ORDER_LANE0=1: indeks ReadLane/ReadFirstLane dianggap 0 (entri pertama tabel, texture sah).
LANE_OLD = """        LOG_ERROR(Render_Recompiler, "Unexpected instruction for offset computation, Phi (dinamis)");
        return false;
    default:"""
LANE_NEW = """        LOG_ERROR(Render_Recompiler, "Unexpected instruction for offset computation, Phi (dinamis)");
        return false;
    case IR::Opcode::ReadLane:
    case IR::Opcode::ReadFirstLane: { // bbport-order (37): BB_ORDER_LANE0=1 -> indeks 0
        static const bool lane0 = std::getenv("BB_ORDER_LANE0") != nullptr;
        if (lane0) {
            c.mov(reg, 0);
            return true;
        }
        LOG_ERROR(Render_Recompiler, "Unexpected instruction for offset computation, {}",
                  magic_enum::enum_name(inst->GetOpcode()));
        return false;
    }
    default:"""


def lane_zero():
    path = (BBPORT / 'gpu' / 'shadps4' / 'shader_recompiler' / 'ir' / 'passes' /
            'flatten_extended_userdata_pass.cpp')
    text = read(path)
    if 'bbport-order (37)' in text:
        print('37. indeks ReadLane -> 0 (BB_ORDER_LANE0): sudah dipatch')
        return
    if text.count(LANE_OLD) != 1:
        sys.exit('bagian 37: titik sisip tidak ditemukan (bagian 28 harus sudah terpasang)')
    if '#include <cstdlib>' not in text:
        text = '#include <cstdlib>\n' + text
    write(path, text.replace(LANE_OLD, LANE_NEW, 1))
    print('37. indeks ReadLane/ReadFirstLane -> 0, saklar BB_ORDER_LANE0=1 (bawaan mati)')


# --- 38. Bintik wajah: SRT walker dua tahap (indeks texture dari konstanta yang belum dibaca) ---
# 16 Okt 20:30. Sesudah 37, shader kulit f5c17eec masih gagal 13x TANPA pesan "Unexpected": offset
# texture bergantung pada ReadConst yang slot flatbuf-nya belum terisi (konstanta itu ada di cabang SRT
# lain yang dikunjungi belakangan). Solusi: kegagalan seperti itu ditunda; pointer cabang (rdi) disimpan
# di slot cadangan flatbuf, lalu sesudah semua cabang dikunjungi offset dihitung ulang dan dword T#
# ditulis ke slot aslinya. BB_ORDER_SRT_FIXUP=1 (bawaan mati; cache shader harus dihapus).
SRT38_DECL_OLD = "static void VisitPointer(const IR::Value& off_dw, IR::Inst* subtree, PassInfo& pass_info,\n"
SRT38_DECL_NEW = """// bbport-order (38): kegagalan offset yang ditunda sampai semua cabang SRT selesai dikunjungi.
struct BbOrderSrtDeferred {
    u32 scratch_dw;
    IR::Value off;
    u32 dst_dw;
};
static thread_local std::vector<BbOrderSrtDeferred> bb_order_srt_deferred;
static bool BbOrderSrtFixup() {
    static const bool on = std::getenv("BB_ORDER_SRT_FIXUP") != nullptr;
    return on;
}

""" + SRT38_DECL_OLD
SRT38_LOCAL_OLD = """    PassInfo::PtrUserList* use_list = pass_info.GetUsesAsPointer(subtree);
    ASSERT(use_list);

    // First copy all the src data from this tree level"""
SRT38_LOCAL_NEW = """    PassInfo::PtrUserList* use_list = pass_info.GetUsesAsPointer(subtree);
    ASSERT(use_list);
    u32 bb_scratch_dw = 0; // bbport-order (38): slot cadangan pointer cabang ini (0 = belum)

    // First copy all the src data from this tree level"""
SRT38_FAIL_OLD = """            if (!ComputeOffset(c, r10d, pass_info, src_off_dw)) {
                LOG_ERROR(Render_Recompiler, "Failed to compute offset for SRT walker (shader {:#018x})", bb_order_srt_hash);
                c.xor_(r10d, r10d); // bbport-order: slot berisi 0, bukan dword 0 user data
            } else {"""
SRT38_FAIL_NEW = """            if (!ComputeOffset(c, r10d, pass_info, src_off_dw)) {
                LOG_ERROR(Render_Recompiler, "Failed to compute offset for SRT walker (shader {:#018x})", bb_order_srt_hash);
                c.xor_(r10d, r10d); // bbport-order: slot berisi 0, bukan dword 0 user data
                if (BbOrderSrtFixup()) { // bbport-order (38): coba lagi sesudah semua cabang
                    if (bb_scratch_dw == 0) {
                        bb_scratch_dw = pass_info.dst_off_dw;
                        pass_info.dst_off_dw += 2;
                        c.mov(qword[rsi + (bb_scratch_dw << 2)], rdi);
                    }
                    bb_order_srt_deferred.push_back({bb_scratch_dw, src_off_dw, pass_info.dst_off_dw});
                }
            } else {"""
SRT38_END_OLD = """    for (const auto& [sgpr_base, root] : pass_info.srt_roots) {
        VisitPointer(IR::Value(static_cast<u32>(sgpr_base)), root, pass_info, c);
    }

    c.ret();"""
SRT38_END_NEW = """    bb_order_srt_deferred.clear(); // bbport-order (38)
    for (const auto& [sgpr_base, root] : pass_info.srt_roots) {
        VisitPointer(IR::Value(static_cast<u32>(sgpr_base)), root, pass_info, c);
    }
    for (const auto& d : bb_order_srt_deferred) { // bbport-order (38): offset yang ditunda
        c.mov(rdi, qword[rsi + (d.scratch_dw << 2)]);
        if (ComputeOffset(c, r10d, pass_info, d.off)) {
            c.shl(r10d, 2);
            c.mov(r10d, r10d);
            c.mov(r10d, dword[rdi + r10]);
            c.mov(dword[rsi + (d.dst_dw << 2)], r10d);
        } else {
            LOG_ERROR(Render_Recompiler, "bbport-order (38): offset tetap gagal (shader {:#018x})",
                      bb_order_srt_hash);
        }
    }
    if (!bb_order_srt_deferred.empty()) {
        LOG_WARNING(Render_Recompiler, "bbport-order (38): {} offset SRT ditunda (shader {:#018x})",
                    bb_order_srt_deferred.size(), bb_order_srt_hash);
    }
    bb_order_srt_deferred.clear();

    c.ret();"""


def srt_two_pass():
    path = (BBPORT / 'gpu' / 'shadps4' / 'shader_recompiler' / 'ir' / 'passes' /
            'flatten_extended_userdata_pass.cpp')
    text = read(path)
    if 'bbport-order (38)' in text:
        print('38. SRT walker dua tahap: sudah dipatch')
        return
    pairs = ((SRT38_DECL_OLD, SRT38_DECL_NEW), (SRT38_LOCAL_OLD, SRT38_LOCAL_NEW),
             (SRT38_FAIL_OLD, SRT38_FAIL_NEW), (SRT38_END_OLD, SRT38_END_NEW))
    for old, _ in pairs:
        if text.count(old) != 1:
            sys.exit('bagian 38: titik sisip tidak ditemukan (bagian 35 harus sudah terpasang)')
    for old, new in pairs:
        text = text.replace(old, new, 1)
    for inc in ('#include <cstdlib>', '#include <vector>'):
        if inc not in text:
            text = inc + '\n' + text
    write(path, text)
    print('38. SRT walker dua tahap, saklar BB_ORDER_SRT_FIXUP=1 (bawaan mati)')


# --- 39. Bintik wajah: RCP/RSQ tanpa tak hingga (16 Okt 20:35) ---
# Shader kulit f5c17eec = sumber bintik (dilewati -> wajah hitam), texture-nya sudah benar (bagian 38)
# -> tersangka: NaN dari 1/0 atau 1/sqrt(0) = inf, lalu inf * 0 = NaN (tampil hitam). Di bbport
# V_RCP_CLAMP_F32 dan V_RSQ_LEGACY_F32 masih diterjemahkan tanpa clamp.
# BB_ORDER_FPCLAMP berisi huruf: c = V_RCP_CLAMP, l = V_RSQ_LEGACY, a = juga V_RCP/V_RSQ/V_RCP_IFLAG biasa.
# Hasil di-clamp ke +-FLT_MAX. Bawaan mati; cache shader harus dihapus.
FPC_HELPER_OLD = "static bool BbOrderLegacy(char k) {"
FPC_HELPER_NEW = """// bbport-order (39): BB_ORDER_FPCLAMP: c = V_RCP_CLAMP, l = V_RSQ_LEGACY, a = semua RCP/RSQ.
static bool BbOrderFpClamp(char k) {
    static const char* e = std::getenv("BB_ORDER_FPCLAMP");
    return e != nullptr && std::strchr(e, k) != nullptr;
}

""" + FPC_HELPER_OLD
FPC_CASES = [
    ("    case Opcode::V_RCP_F32:\n        return V_RCP_F32(inst);\n", 'a', 'FPRecip'),
    ("    case Opcode::V_RCP_IFLAG_F32:\n        return V_RCP_F32(inst);\n", 'a', 'FPRecip'),
    ("    case Opcode::V_RCP_CLAMP_F32:\n        return V_RCP_F32(inst);\n", 'c', 'FPRecip'),
    ("    case Opcode::V_RSQ_LEGACY_F32:\n        return V_RSQ_F32(inst);\n", 'l', 'FPRecipSqrt'),
    ("    case Opcode::V_RSQ_F32:\n        return V_RSQ_F32(inst);\n", 'a', 'FPRecipSqrt'),
]


def _fpc_case(old, letter, fn):
    head = old.split('\n')[0].rstrip(':')
    plain = old.split('\n')[1].strip()
    return (f"{head}: {{ // bbport-order (39): BB_ORDER_FPCLAMP '{letter}'\n"
            f"        if (!BbOrderFpClamp('{letter}')) {{\n"
            f"            {plain}\n"
            f"        }}\n"
            f"        const IR::F32 r{{ir.{fn}(GetSrc<IR::F32>(inst.src[0]))}};\n"
            f"        SetDst(inst.dst[0], ir.FPClamp(r, ir.Imm32(-3.402823466e+38f), ir.Imm32(3.402823466e+38f)));\n"
            f"        return;\n"
            f"    }}\n")


def fp_clamp():
    path = BBPORT / 'gpu' / 'shadps4' / 'shader_recompiler' / 'frontend' / 'translate' / 'vector_alu.cpp'
    text = read(path)
    if 'bbport-order (39)' in text:
        print('39. RCP/RSQ clamp (BB_ORDER_FPCLAMP): sudah dipatch')
        return
    if text.count(FPC_HELPER_OLD) != 1 or any(text.count(o) != 1 for o, _, _ in FPC_CASES):
        sys.exit('bagian 39: titik sisip tidak ditemukan (bagian 27 harus sudah terpasang)')
    text = text.replace(FPC_HELPER_OLD, FPC_HELPER_NEW, 1)
    for old, letter, fn in FPC_CASES:
        text = text.replace(old, _fpc_case(old, letter, fn), 1)
    write(path, text)
    print('39. RCP/RSQ di-clamp tanpa inf, saklar BB_ORDER_FPCLAMP=cla (bawaan mati)')


# --- 40. Bintik wajah: NaN di output shader kulit (16 Okt 20:50) ---
# Dump IR f5c17eec: shader kulit menulis 2 MRT (cahaya kulit) yang lalu di-blur (subsurface
# scattering/TAA). Satu piksel NaN menyebar jadi noda hitam berbentuk tetesan. Clamp RCP/RSQ (39)
# tidak cukup; asal NaN-nya banyak kemungkinan (normal dari turunan quad, log2/exp2, sqrt).
# Perbaikan: saat ekspor render target, NaN -> 0 dan nilai di-clamp ke +-65504 (batas float16).
# BB_ORDER_NANFIX = all (semua pixel shader) atau daftar hash hex (f5c17eec,...).
# BB_ORDER_NANFIX_DEBUG=1: NaN diganti magenta (diagnosa). Bawaan mati; cache shader harus dihapus.
NAN_HELPER_OLD = "namespace Shader::Gcn {\n"
NAN_HELPER_NEW = """namespace Shader::Gcn {

// bbport-order (40): BB_ORDER_NANFIX = all | hash,hash (hex). NaN di ekspor MRT -> 0, clamp +-65504.
static bool BbOrderNanFix(u64 hash) {
    static const char* e = std::getenv("BB_ORDER_NANFIX");
    if (e == nullptr || *e == 0) {
        return false;
    }
    if (std::strcmp(e, "all") == 0 || std::strcmp(e, "1") == 0) {
        return true;
    }
    const char* p = e;
    while (*p != 0) {
        char* end = nullptr;
        const unsigned long long v = std::strtoull(p, &end, 16);
        if (end == p) {
            break;
        }
        if (v == hash) {
            return true;
        }
        p = (*end == ',') ? end + 1 : end;
    }
    return false;
}
"""
NAN_INC_OLD = '#include "shader_recompiler/frontend/translate/translate.h"\n'
NAN_INC_NEW = '#include <cstdlib>\n#include <cstring>\n' + NAN_INC_OLD
NAN_EXP_OLD = "        ir.SetAttribute(mrt, converted, i);\n    }\n}\n"
NAN_EXP_NEW = """        if (color_buffer.num_format != AmdGpu::NumberFormat::Uint &&
            color_buffer.num_format != AmdGpu::NumberFormat::Sint &&
            BbOrderNanFix(info.pgm_hash)) { // bbport-order (40): hanya RT float/unorm
            static const bool dbg = std::getenv("BB_ORDER_NANFIX_DEBUG") != nullptr;
            const IR::F32 v{converted};
            const IR::F32 repl{ir.Imm32((dbg && i != 1 && i != 3) ? 1.0f : 0.0f)};
            const IR::F32 clean{ir.Select(ir.FPIsNan(v), repl, v)};
            converted = IR::F32{ir.FPClamp(clean, ir.Imm32(-65504.0f), ir.Imm32(65504.0f))};
        }
""" + NAN_EXP_OLD


def nan_fix():
    path = BBPORT / 'gpu' / 'shadps4' / 'shader_recompiler' / 'frontend' / 'translate' / 'export.cpp'
    text = read(path)
    if 'bbport-order (40)' in text:
        print('40. NaN fix ekspor MRT (BB_ORDER_NANFIX): sudah dipatch')
        return
    for old in (NAN_HELPER_OLD, NAN_INC_OLD, NAN_EXP_OLD):
        if text.count(old) != 1:
            sys.exit('bagian 40: titik sisip tidak ditemukan di export.cpp')
    text = text.replace(NAN_INC_OLD, NAN_INC_NEW, 1)
    text = text.replace(NAN_HELPER_OLD, NAN_HELPER_NEW, 1)
    text = text.replace(NAN_EXP_OLD, NAN_EXP_NEW, 1)
    write(path, text)
    print('40. NaN di ekspor render target -> 0 (BB_ORDER_NANFIX=all atau hash, bawaan mati)')


# --- 41. Bintik wajah: diagnosa image GPU yang dibaca ulang dari memori basi (16 Okt 21:15) ---
# Port GoW3 (cuesta4 eltutz 189ca3b6) menambah "image aliasing": memori yang sama dipakai dua
# image (format/ukuran lain) -> isinya disalin. bbport belum: kalau tekstur yang diminta tidak cocok
# dengan render target yang baru digambar GPU di alamat itu, dibuat image baru yang diisi dari
# memori guest (basi, hasil GPU tidak pernah ditulis ke sana). Bintik yang hanya muncul di sebagian
# scene dan tidak berubah walau pass droplet dimatikan cocok dengan pola ini.
# BB_ORDER_ALIAS_LOG=1: setiap image baru yang menimpa image hasil GPU dicatat (maks 400 baris).
ALIAS_INC_OLD = "#include <cstdio>\n"
ALIAS_INC_NEW = "#include <cstdio>\n#include <mutex>\n#include <unordered_set>\n#include <vector>\n"
ALIAS_HELPER_OLD = "ImageId TextureCache::FindImage("
ALIAS_HELPER_NEW = """// bbport-order (41): BB_ORDER_ALIAS_LOG=1 -> image baru di atas image hasil GPU dicatat.
struct BbOrderGpuOverlap {
    VAddr addr;
    u64 size;
    u32 w, h, tile, bits, levels, layers;
    vk::Format fmt;
};
static bool BbOrderAliasLogOn() {
    static const bool on = [] {
        const char* e = std::getenv("BB_ORDER_ALIAS_LOG");
        return e != nullptr && e[0] == '1';
    }();
    return on;
}
static void BbOrderAliasReport(const ImageInfo& info, u32 binding,
                               const std::vector<BbOrderGpuOverlap>& overlaps) {
    static std::mutex m;
    static std::unordered_set<u64> seen;
    const u64 key = info.guest_address ^ (u64(info.pixel_format) << 44) ^ (u64(binding) << 60) ^
                    (overlaps[0].addr << 7);
    {
        std::scoped_lock lock{m};
        if (seen.size() >= 400 || !seen.insert(key).second) {
            return;
        }
    }
    std::printf("bbport-order (41): image baru bind %u %#llx %ux%u mip %u layer %u fmt %s tile %u "
                "bits %u size %#llx menimpa %zu image GPU:\\n",
                binding, (unsigned long long)info.guest_address, info.size.width, info.size.height,
                info.resources.levels, info.resources.layers,
                vk::to_string(info.pixel_format).c_str(), u32(info.tile_mode), info.num_bits,
                (unsigned long long)info.guest_size, overlaps.size());
    for (const auto& o : overlaps) {
        std::printf("    gpu %#llx (%+lld) %ux%u mip %u layer %u fmt %s tile %u bits %u size %#llx\\n",
                    (unsigned long long)o.addr, (long long)(o.addr - info.guest_address), o.w, o.h,
                    o.levels, o.layers, vk::to_string(o.fmt).c_str(), o.tile, o.bits,
                    (unsigned long long)o.size);
    }
    std::fflush(stdout);
}

""" + ALIAS_HELPER_OLD
ALIAS_SNAP_OLD = "    ImageId image_id{};\n\n    // Check for a perfect match first"
ALIAS_SNAP_NEW = """    std::vector<BbOrderGpuOverlap> bb_gpu_overlaps; // bbport-order (41)
    if (BbOrderAliasLogOn()) {
        for (const auto& id : image_ids) {
            const auto& ci = slot_images[id];
            if (True(ci.flags & ImageFlagBits::GpuModified)) {
                bb_gpu_overlaps.push_back({ci.info.guest_address, ci.info.guest_size,
                                           ci.info.size.width, ci.info.size.height,
                                           u32(ci.info.tile_mode), ci.info.num_bits,
                                           ci.info.resources.levels, ci.info.resources.layers,
                                           ci.info.pixel_format});
            }
        }
    }

""" + ALIAS_SNAP_OLD
ALIAS_NEW_OLD = """    // Create and register a new image
    if (!image_id) {
        image_id = slot_images.insert(instance, runtime, slot_image_views, info);"""
ALIAS_NEW_NEW = """    // Create and register a new image
    if (!image_id) {
        if (!bb_gpu_overlaps.empty()) { // bbport-order (41)
            BbOrderAliasReport(info, u32(desc.type), bb_gpu_overlaps);
        }
        image_id = slot_images.insert(instance, runtime, slot_image_views, info);"""


def alias_log():
    path = BBPORT / 'gpu' / 'shadps4' / 'video_core' / 'texture_cache' / 'texture_cache.cpp'
    text = read(path)
    if 'bbport-order (41)' in text:
        print('41. log image baru di atas image GPU (BB_ORDER_ALIAS_LOG): sudah dipatch')
        return
    for old in (ALIAS_INC_OLD, ALIAS_HELPER_OLD, ALIAS_SNAP_OLD, ALIAS_NEW_OLD):
        if text.count(old) != 1:
            sys.exit('bagian 41: titik sisip tidak ditemukan di texture_cache.cpp')
    text = text.replace(ALIAS_INC_OLD, ALIAS_INC_NEW, 1)
    text = text.replace(ALIAS_HELPER_OLD, ALIAS_HELPER_NEW, 1)
    text = text.replace(ALIAS_SNAP_OLD, ALIAS_SNAP_NEW, 1)
    text = text.replace(ALIAS_NEW_OLD, ALIAS_NEW_NEW, 1)
    write(path, text)
    print('41. image baru di atas image hasil GPU dicatat, saklar BB_ORDER_ALIAS_LOG=1 (bawaan mati)')


# --- 42. Bintik wajah: tekstur mana di shader kulit (16 Okt 21:30) ---
# Bintik hanya di karakter utama (NPC dengan shader kulit yang sama bersih), tetap ada dengan semua
# optimasi bbport mati (BB_TOGGLE_FILE) -> data khusus karakter itu: tekstur (mask darah/luka,
# detail wajah) atau konstanta. Bagian ini mencatat semua T# yang dipakai shader tertentu dan bisa
# mematikan (null) tekstur pilihan SAAT GAME BERJALAN.
# BB_ORDER_NULLTEX_FILE=path, isi: "<hash hex> <mask hex>", dibaca ulang tiap 0,5 detik.
# Bit N dari mask = image N shader itu diikat null (sampel = 0). Mask 0 = hanya mencatat.
NULLTEX_HELPER_OLD = "void Rasterizer::BindTextures(const Shader::Info& stage,"
NULLTEX_HELPER_NEW = """// bbport-order (42): BB_ORDER_NULLTEX_FILE = file berisi "<hash hex> <mask hex>".
static std::atomic<unsigned long long> bb_order_nt_hash{0}, bb_order_nt_mask{0};
static void BbOrderNullTexReload() {
    static const char* path = std::getenv("BB_ORDER_NULLTEX_FILE");
    if (path == nullptr) {
        return;
    }
    static std::atomic<long long> next{0};
    const long long now = std::chrono::duration_cast<std::chrono::milliseconds>(
                              std::chrono::steady_clock::now().time_since_epoch())
                              .count();
    long long expected = next.load(std::memory_order_relaxed);
    if (now < expected || !next.compare_exchange_strong(expected, now + 500)) {
        return;
    }
    unsigned long long h = 0, m = 0;
    if (FILE* f = std::fopen(path, "r")) {
        if (std::fscanf(f, "%llx %llx", &h, &m) < 1) {
            h = 0;
        }
        std::fclose(f);
    }
    if (bb_order_nt_hash.exchange(h) != h || bb_order_nt_mask.exchange(m) != m) {
        std::printf("bbport-order (42): null tekstur shader %llx mask %#llx\\n", h, m);
        std::fflush(stdout);
    }
}
static bool BbOrderNullTexActive(u64 hash) {
    BbOrderNullTexReload();
    const auto h = bb_order_nt_hash.load(std::memory_order_relaxed);
    return h != 0 && h == hash;
}

""" + NULLTEX_HELPER_OLD
NULLTEX_MEMO_OLD = "    if (!on_helper && BindTexturesFromSet(stage, prepared, first_image_idx, barrier, set_slot)) {"
NULLTEX_MEMO_NEW = ("    const bool bb_order_nt = BbOrderNullTexActive(stage.pgm_hash); // bbport-order (42)\n"
                    "    if (!on_helper && !bb_order_nt &&\n"
                    "        BindTexturesFromSet(stage, prepared, first_image_idx, barrier, set_slot)) {")
NULLTEX_LOOP_OLD = '''            LOG_WARNING(Render_Vulkan, "Unexpected metadata read by a shader (texture)");
        }

        const auto data_fmt = tsharp.GetDataFmt();'''
NULLTEX_LOOP_NEW = '''            LOG_WARNING(Render_Vulkan, "Unexpected metadata read by a shader (texture)");
        }

        if (bb_order_nt) { // bbport-order (42): catat T#, ikat null kalau bit-nya di mask
            static std::mutex told_m;
            static std::unordered_set<unsigned long long> told;
            const unsigned long long key = (stage.pgm_hash << 8) ^ image_index ^
                                           (unsigned long long)(tsharp.Address() << 20);
            bool first;
            {
                std::scoped_lock lock{told_m};
                first = told.size() < 2000 && told.insert(key).second;
            }
            if (first) {
                std::printf("bbport-order (42): ps %llx img %u %#llx %ux%u depth %u type %u tile %u "
                            "fmt %u/%u mip %u..%u array %u..%u pitch %u written %d\\n",
                            (unsigned long long)stage.pgm_hash, image_index,
                            (unsigned long long)tsharp.Address(), u32(tsharp.width) + 1,
                            u32(tsharp.height) + 1, u32(tsharp.depth) + 1, u32(tsharp.GetType()),
                            u32(tsharp.GetTileMode()), u32(tsharp.GetDataFmt()),
                            u32(tsharp.GetNumberFmt()), u32(tsharp.base_level),
                            u32(tsharp.last_level), u32(tsharp.base_array), u32(tsharp.last_array),
                            u32(tsharp.Pitch()), int(image_desc.is_written));
                std::fflush(stdout);
            }
            if (image_index < 64 && ((bb_order_nt_mask.load() >> image_index) & 1) != 0) {
                image_bindings.emplace_back(VideoCore::ImageId{}, &image_desc_storage.emplace_back());
                image_binding_entries.push_back(nullptr);
                binding_proxy_ok.push_back(false);
                image_descriptor_array_sizes.push_back(1);
                continue;
            }
        }

        const auto data_fmt = tsharp.GetDataFmt();'''
NULLTEX_INC_OLD = "#include <unordered_set>\n"
NULLTEX_INC_NEW = "#include <unordered_set>\n#include <chrono>\n#include <cstdio>\n#include <mutex>\n"


def null_tex():
    path = BBPORT / 'gpu' / 'shadps4' / 'video_core' / 'renderer_vulkan' / 'vk_rasterizer.cpp'
    text = read(path)
    if 'bbport-order (42)' in text:
        print('42. null tekstur per shader (BB_ORDER_NULLTEX_FILE): sudah dipatch')
        return
    for old in (NULLTEX_INC_OLD, NULLTEX_HELPER_OLD, NULLTEX_MEMO_OLD, NULLTEX_LOOP_OLD):
        if text.count(old) != 1:
            sys.exit('bagian 42: titik sisip tidak ditemukan di vk_rasterizer.cpp')
    text = text.replace(NULLTEX_INC_OLD, NULLTEX_INC_NEW, 1)
    text = text.replace(NULLTEX_HELPER_OLD, NULLTEX_HELPER_NEW, 1)
    text = text.replace(NULLTEX_MEMO_OLD, NULLTEX_MEMO_NEW, 1)
    text = text.replace(NULLTEX_LOOP_OLD, NULLTEX_LOOP_NEW, 1)
    write(path, text)
    print('42. T# shader dicatat dan bisa di-null saat main, saklar BB_ORDER_NULLTEX_FILE (bawaan mati)')


# --- 43. Bintik wajah: alpha-to-coverage (DB_ALPHA_TO_MASK) tidak diemulasikan (16 Okt 21:45) ---
# Titik hitam berkedip hanya di karakter utama, di garis rambut, alis, telinga, jambang: tempat
# kartu rambut halus (alis, bulu halus, jambang). Kartu seperti itu digambar dengan alpha-to-coverage:
# piksel dengan alpha kecil tidak ditulis. shadPS4/bbport tidak membaca register DB_ALPHA_TO_MASK
# (0xA2DC bit 0), jadi bagian kartu yang seharusnya transparan ikut digambar (warnanya gelap).
# Mematikan tekstur shader kulit (bagian 42) tidak mengubah titiknya -> titik dari draw lain.
# Sekarang alphaToCoverageEnable mengikuti register. Bawaan NYALA; BB_ORDER_A2C=0 mematikan.
# Kunci pipeline berubah: cache shader harus dihapus.
A2C_KEY_OLD = "    u32 motion_vectors = 0;\n"
A2C_KEY_NEW = "    u32 motion_vectors = 0;\n    u32 alpha_to_coverage = 0; // bbport-order (43): DB_ALPHA_TO_MASK\n"
A2C_FILL_OLD = "    key.cb_shader_mask = regs.color_shader_mask;\n"
A2C_FILL_NEW = """    key.cb_shader_mask = regs.color_shader_mask;
    { // bbport-order (43): DB_ALPHA_TO_MASK (context reg 0xA2DC) bit 0 = ALPHA_TO_MASK_ENABLE
        static const bool a2c_on = [] {
            const char* e = std::getenv("BB_ORDER_A2C");
            return e == nullptr || e[0] != '0';
        }();
        key.alpha_to_coverage = (a2c_on && (regs.reg_array[0xA2DC] & 1u) != 0) ? 1u : 0u;
    }
"""
A2C_MS_OLD = """            .sampleShadingEnable =
                fs_info.addr_flags.persp_sample_ena || fs_info.addr_flags.linear_sample_ena,
        };
    }
"""
A2C_MS_NEW = """            .sampleShadingEnable =
                fs_info.addr_flags.persp_sample_ena || fs_info.addr_flags.linear_sample_ena,
            .alphaToCoverageEnable = key.alpha_to_coverage != 0, // bbport-order (43)
        };
        if (key.alpha_to_coverage != 0) {
            LOG_WARNING(Render_Vulkan, "bbport-order (43): alpha-to-coverage {} samples {}",
                        debug_str, u32(key.num_samples));
        }
    }
"""


def alpha_to_coverage():
    rv = BBPORT / 'gpu' / 'shadps4' / 'video_core' / 'renderer_vulkan'
    files = [(rv / 'vk_graphics_pipeline.h', A2C_KEY_OLD, A2C_KEY_NEW),
             (rv / 'vk_pipeline_cache.cpp', A2C_FILL_OLD, A2C_FILL_NEW),
             (rv / 'vk_graphics_pipeline.cpp', A2C_MS_OLD, A2C_MS_NEW)]
    texts = [read(p) for p, _, _ in files]
    if all('bbport-order (43)' in t for t in texts):
        print('43. alpha-to-coverage (BB_ORDER_A2C): sudah dipatch')
        return
    for (p, old, _), t in zip(files, texts):
        if 'bbport-order (43)' not in t and t.count(old) != 1:
            sys.exit(f'bagian 43: titik sisip tidak ditemukan di {p.name}')
    for (p, old, new), t in zip(files, texts):
        if 'bbport-order (43)' not in t:
            write(p, t.replace(old, new, 1))
    print('43. alpha-to-coverage dari DB_ALPHA_TO_MASK (bawaan nyala, BB_ORDER_A2C=0 mematikan)')


# --- 44. Bintik wajah: cari draw/dispatch pembuat titik, langsung saat main (16 Okt 21:55) ---
# Alpha-to-coverage (43) tidak dipakai game sama sekali (0 pipeline). Titik bergerak sangat cepat,
# hanya di karakter utama, tidak berubah walau tekstur shader kulit dimatikan -> dibuat pass lain
# (rambut, efek wajah, SSS/blur compute, TAA). Alat:
#  - BB_ORDER_SKIP_FILE=path: daftar hash hex (vs, ps atau cs), dipisah spasi/baris, dibaca ulang
#    tiap 0,5 detik; draw/dispatch dengan hash itu tidak dijalankan.
#  - Frame capture mencatat sampai 64 shader per pass (sebelumnya 8).
SKIP_INC_OLD = "#include <unordered_set>\n#include <chrono>\n#include <cstdio>\n#include <mutex>\n"
SKIP_INC_NEW = SKIP_INC_OLD + """#include <vector>

// bbport-order (44): BB_ORDER_SKIP_FILE = daftar hash shader (hex) yang tidak dijalankan.
static bool BbOrderSkipLive(unsigned long long hash) {
    static const char* path = std::getenv("BB_ORDER_SKIP_FILE");
    if (path == nullptr || hash == 0) {
        return false;
    }
    static std::mutex m;
    static std::vector<unsigned long long> list;
    static long long next = 0;
    std::scoped_lock lock{m};
    const long long now = std::chrono::duration_cast<std::chrono::milliseconds>(
                              std::chrono::steady_clock::now().time_since_epoch())
                              .count();
    if (now >= next) {
        next = now + 500;
        std::vector<unsigned long long> fresh;
        if (FILE* f = std::fopen(path, "r")) {
            unsigned long long h = 0;
            while (std::fscanf(f, " %llx%*[ ,\\n\\t]", &h) == 1) {
                fresh.push_back(h);
            }
            std::fclose(f);
        }
        if (fresh != list) {
            list = fresh;
            std::printf("bbport-order (44): skip %zu shader:", list.size());
            for (const auto x : list) {
                std::printf(" %llx", x);
            }
            std::printf("\\n");
            std::fflush(stdout);
        }
    }
    for (const auto x : list) {
        if (x == hash) {
            return true;
        }
    }
    return false;
}
"""
SKIP_REC_OLD = "    scheduler.RecordCrumb(crumb, [=](vk::CommandBuffer cmdbuf) {\n        cmdbuf.bindPipeline(vk::PipelineBindPoint::e"
SKIP_REC_NEW = ("    const bool bb_skip = BbOrderSkipLive(crumb.hash[0]) || BbOrderSkipLive(crumb.hash[1]); // bbport-order (44)\n"
                "    scheduler.RecordCrumb(crumb, [=](vk::CommandBuffer cmdbuf) {\n"
                "        if (bb_skip) {\n"
                "            return;\n"
                "        }\n"
                "        cmdbuf.bindPipeline(vk::PipelineBindPoint::e")
CAP_OLD = "    if (entry.shaders.size() < 8 && "
CAP_NEW = "    if (entry.shaders.size() < 64 /* bbport-order (44) */ && "


def skip_live():
    rv = BBPORT / 'gpu' / 'shadps4' / 'video_core' / 'renderer_vulkan'
    ras = rv / 'vk_rasterizer.cpp'
    cap = rv / 'vk_frame_capture.cpp'
    t = read(ras)
    if 'bbport-order (44)' not in t:
        if t.count(SKIP_INC_OLD) != 1 or t.count(SKIP_REC_OLD) != 3:
            sys.exit('bagian 44: titik sisip tidak ditemukan di vk_rasterizer.cpp (bagian 42 dulu)')
        t = t.replace(SKIP_INC_OLD, SKIP_INC_NEW, 1).replace(SKIP_REC_OLD, SKIP_REC_NEW)
        write(ras, t)
    c = read(cap)
    if 'bbport-order (44)' not in c:
        if c.count(CAP_OLD) != 1:
            sys.exit('bagian 44: titik sisip tidak ditemukan di vk_frame_capture.cpp')
        write(cap, c.replace(CAP_OLD, CAP_NEW, 1))
    print('44. skip draw/dispatch per hash saat main (BB_ORDER_SKIP_FILE), capture 64 shader/pass')


# --- 45. Bintik wajah: warnai piksel NaN/negatif/raksasa di output pixel shader (16 Okt 22:05) ---
# Semua pass lain sudah dilewati saat main (44) tanpa efek; tekstur shader kulit (42) juga. Sisa:
# nilai yang dihitung shader kulit sendiri. Bagian 40 hanya mengganti NaN per komponen.
# BB_ORDER_NANFIX_DEBUG=2 (dengan BB_ORDER_NANFIX=all/hash): per PIKSEL, kalau ada komponen
#   NaN -> magenta, negatif -> hijau, > 65504 -> biru (terang, mudah dilihat).
# BB_ORDER_NANFIX_MIN0=1: nilai negatif di-clamp ke 0 (perbaikan kalau penyebabnya negatif).
EXPLOOP_OLD = """        if (color_buffer.num_format != AmdGpu::NumberFormat::Uint &&
            color_buffer.num_format != AmdGpu::NumberFormat::Sint &&
            BbOrderNanFix(info.pgm_hash)) { // bbport-order (40): hanya RT float/unorm
            static const bool dbg = std::getenv("BB_ORDER_NANFIX_DEBUG") != nullptr;
            const IR::F32 v{converted};
            const IR::F32 repl{ir.Imm32((dbg && i != 1 && i != 3) ? 1.0f : 0.0f)};
            const IR::F32 clean{ir.Select(ir.FPIsNan(v), repl, v)};
            converted = IR::F32{ir.FPClamp(clean, ir.Imm32(-65504.0f), ir.Imm32(65504.0f))};
        }
        ir.SetAttribute(mrt, converted, i);
    }
}
"""
EXPLOOP_NEW = """        if (color_buffer.num_format != AmdGpu::NumberFormat::Uint &&
            color_buffer.num_format != AmdGpu::NumberFormat::Sint &&
            BbOrderNanFix(info.pgm_hash)) { // bbport-order (40): hanya RT float/unorm
            static const int dbg = [] { // bbport-order (45): 1 = NaN magenta per komponen, 2 = per piksel
                const char* e = std::getenv("BB_ORDER_NANFIX_DEBUG");
                return e == nullptr ? 0 : (e[0] == '2' ? 2 : 1);
            }();
            static const bool min0 = std::getenv("BB_ORDER_NANFIX_MIN0") != nullptr;
            const IR::F32 v{converted};
            if (dbg == 2) {
                // Status per piksel dari semua komponen warna (bukan alpha).
                const IR::F32 zero{ir.Imm32(0.0f)};
                const IR::F32 big{ir.Imm32(65504.0f)};
                IR::U1 any_nan{ir.Imm1(false)}, any_neg{ir.Imm1(false)}, any_big{ir.Imm1(false)};
                for (u32 k = 0; k < 3; ++k) {
                    const auto ck = components[color_buffer.swizzle.Map(k)];
                    if (ck.IsEmpty()) {
                        continue;
                    }
                    const IR::F32 vk{ApplyWriteNumberConversion(ir, ck, color_buffer.num_conversion)};
                    any_nan = ir.LogicalOr(any_nan, ir.FPIsNan(vk));
                    any_neg = ir.LogicalOr(any_neg, ir.FPLessThan(vk, zero));
                    any_big = ir.LogicalOr(any_big, ir.FPGreaterThan(IR::F32{ir.FPAbs(vk)}, big));
                }
                const float mag = (i == 0 || i == 2) ? 8.0f : 0.0f;
                const float grn = (i == 1) ? 8.0f : 0.0f;
                const float blu = (i == 2) ? 8.0f : 0.0f;
                const IR::F32 keep{i == 3 ? IR::F32{ir.Select(ir.FPIsNan(v), zero, v)} : v};
                IR::F32 out{ir.Select(any_big, ir.Imm32(blu), keep)};
                out = IR::F32{ir.Select(any_neg, ir.Imm32(grn), out)};
                out = IR::F32{ir.Select(any_nan, ir.Imm32(mag), out)};
                converted = i == 3 ? keep : out;
            } else {
                const IR::F32 repl{ir.Imm32((dbg == 1 && i != 1 && i != 3) ? 1.0f : 0.0f)};
                IR::F32 clean{ir.Select(ir.FPIsNan(v), repl, v)};
                if (min0) {
                    clean = IR::F32{ir.FPMax(clean, ir.Imm32(0.0f))};
                }
                converted = IR::F32{ir.FPClamp(clean, ir.Imm32(-65504.0f), ir.Imm32(65504.0f))};
            }
        }
        ir.SetAttribute(mrt, converted, i);
    }
}
"""


def nan_debug():
    path = BBPORT / 'gpu' / 'shadps4' / 'shader_recompiler' / 'frontend' / 'translate' / 'export.cpp'
    text = read(path)
    if 'bbport-order (45)' in text:
        print('45. diagnosa NaN/negatif per piksel (BB_ORDER_NANFIX_DEBUG=2): sudah dipatch')
        return
    if text.count(EXPLOOP_OLD) != 1:
        sys.exit('bagian 45: titik sisip tidak ditemukan di export.cpp (bagian 40 dulu)')
    write(path, text.replace(EXPLOOP_OLD, EXPLOOP_NEW, 1))
    print('45. NaN/negatif/raksasa per piksel: BB_ORDER_NANFIX_DEBUG=2, clamp negatif: BB_ORDER_NANFIX_MIN0=1')


# --- 46. Bintik wajah: NaN di tulisan image compute (efek kulit 92311aca) (16 Okt 22:10) ---
# Output semua pixel shader bersih (45: tidak ada magenta/hijau/biru di titik). Compute #79
# 92311aca (subsurface scattering: warna adegan + normal/mask kulit -> 1920x800 RGBA16F, dicampur
# ke layar oleh 574764e2) tidak tercakup bagian 40. Melewatinya membekukan gambar, jadi ganti
# dengan pembersih: IMAGE_STORE dari shader di BB_ORDER_STORENAN (hash hex, dipisah koma) -> NaN = 0,
# nilai di-clamp ke +-65504. BB_ORDER_STORENAN_DEBUG=1: piksel NaN jadi magenta terang.
# Hanya untuk shader yang disebut (tulisan integer bisa rusak kalau dipakai sembarangan).
STORE_OLD = """    const IR::Value value = ir.CompositeConstruct(comps[0], comps[1], comps[2], comps[3]);
    ir.ImageWrite(ir.ImageHandle(tsharp_low, tsharp_high), body, {}, {}, value, info);
}
"""
STORE_NEW = """    { // bbport-order (46): BB_ORDER_STORENAN = hash,hash -> NaN di image store compute dibersihkan
        static const char* list = std::getenv("BB_ORDER_STORENAN");
        bool hit = false;
        if (list != nullptr) {
            const char* p = list;
            while (*p != 0) {
                char* end = nullptr;
                const unsigned long long v = std::strtoull(p, &end, 16);
                if (end == p) {
                    break;
                }
                hit |= v == this->info.pgm_hash;
                p = (*end == ',' || *end == ' ') ? end + 1 : end;
            }
        }
        if (hit) {
            static const bool dbg = std::getenv("BB_ORDER_STORENAN_DEBUG") != nullptr;
            IR::U1 any_nan{ir.Imm1(false)};
            for (u32 i = 0; i < 4; i++) {
                if (((mimg.dmask >> i) & 1) != 0) {
                    any_nan = ir.LogicalOr(any_nan, ir.FPIsNan(comps[i]));
                }
            }
            for (u32 i = 0; i < 4; i++) {
                if (((mimg.dmask >> i) & 1) == 0) {
                    continue;
                }
                const float repl = (dbg && (i == 0 || i == 2)) ? 8.0f : 0.0f;
                const IR::F32 clean{ir.Select(dbg ? any_nan : ir.FPIsNan(comps[i]),
                                              ir.Imm32(repl), comps[i])};
                comps[i] = IR::F32{ir.FPClamp(clean, ir.Imm32(-65504.0f), ir.Imm32(65504.0f))};
            }
        }
    }
""" + STORE_OLD


def store_nan():
    path = BBPORT / 'gpu' / 'shadps4' / 'shader_recompiler' / 'frontend' / 'translate' / 'vector_memory.cpp'
    text = read(path)
    if 'bbport-order (46)' in text:
        print('46. NaN di image store compute (BB_ORDER_STORENAN): sudah dipatch')
        return
    if text.count(STORE_OLD) != 1:
        sys.exit('bagian 46: titik sisip tidak ditemukan di vector_memory.cpp')
    if '#include <cstdlib>' not in text:
        text = '#include <cstdlib>\n' + text
    write(path, text.replace(STORE_OLD, STORE_NEW, 1))
    print('46. NaN di image store compute dibersihkan: BB_ORDER_STORENAN=hash (debug: BB_ORDER_STORENAN_DEBUG=1)')


# --- 47. Bintik wajah: posisi vertex tidak invariant (depth prepass vs forward) (16 Okt 22:25) ---
# Video 60 fps: titik hitam acak tiap frame, tajam, hanya di kulit karakter utama (wajah beranimasi).
# Compute 92311aca = TAA dengan input MSAA (img 2 warna adegan 2 sampel, img 3 history): mematikan
# history (img 3) membuat titik makin banyak -> titik ada di SAMPEL MSAA frame ini, bukan dibuat
# TAA. Pass forward (#65) menggambar di atas depth prepass (#2) dengan VS lain dan tes depth tanpa
# tulis: kalau posisi dari dua VS beda sedikit saja, sebagian sampel gagal tes -> sampel itu tetap
# warna clear (hitam). Di PS4 hasilnya identik bit per bit; di NVIDIA dua program berbeda boleh
# beda hasil kecuali gl_Position dideklarasikan Invariant. Bawaan NYALA, BB_ORDER_INVARIANT=0 mematikan.
INV_OLD = "    output_position = DefineVariable(F32[4], spv::BuiltIn::Position, spv::StorageClass::Output);\n"
INV_NEW = INV_OLD + """    { // bbport-order (47): posisi identik antara depth prepass dan pass warna
        static const bool inv = [] {
            const char* e = std::getenv("BB_ORDER_INVARIANT");
            return e == nullptr || e[0] != '0';
        }();
        if (inv) {
            Decorate(output_position, spv::Decoration::Invariant);
        }
    }
"""


def invariant_position():
    path = BBPORT / 'gpu' / 'shadps4' / 'shader_recompiler' / 'backend' / 'spirv' / 'spirv_emit_context.cpp'
    text = read(path)
    if 'bbport-order (47)' in text:
        print('47. gl_Position invariant (BB_ORDER_INVARIANT): sudah dipatch')
        return
    if text.count(INV_OLD) != 1:
        sys.exit('bagian 47: titik sisip tidak ditemukan di spirv_emit_context.cpp')
    if '#include <cstdlib>' not in text:
        text = '#include <cstdlib>\n' + text
    write(path, text.replace(INV_OLD, INV_NEW, 1))
    print('47. gl_Position Invariant (bawaan nyala, BB_ORDER_INVARIANT=0 mematikan)')


# --- 48. Bintik wajah: tes depth EQUAL pass warna dilonggarkan, bisa diganti saat main (16 Okt 23:00) ---
# Invariant (47) tidak cukup. Pass warna (#65) memakai depth EQUAL tanpa tulis di atas prepass.
# BB_ORDER_DEPTHEQ_FILE=path, isi angka (dibaca ulang tiap 0,5 detik):
#   0 = asli, 1 = LESS_OR_EQUAL, 2 = GREATER_OR_EQUAL, 3 = ALWAYS (hanya draw EQUAL tanpa tulis depth).
DEQ_OLD = "        dynamic_state.SetDepthCompareOp(LiverpoolToVK::CompareOp(regs.depth_control.depth_func));\n"
DEQ_NEW = """        auto bb_cmp = LiverpoolToVK::CompareOp(regs.depth_control.depth_func);
        { // bbport-order (48): BB_ORDER_DEPTHEQ_FILE -> EQUAL tanpa tulis depth diganti
            static const char* path = std::getenv("BB_ORDER_DEPTHEQ_FILE");
            static std::atomic<int> mode{0};
            static std::atomic<long long> next{0};
            static std::atomic<bool> told{false};
            if (path != nullptr) {
                const long long now = std::chrono::duration_cast<std::chrono::milliseconds>(
                                          std::chrono::steady_clock::now().time_since_epoch())
                                          .count();
                long long expected = next.load(std::memory_order_relaxed);
                if (now >= expected && next.compare_exchange_strong(expected, now + 500)) {
                    int m = 0;
                    if (FILE* f = std::fopen(path, "r")) {
                        if (std::fscanf(f, "%d", &m) != 1) {
                            m = 0;
                        }
                        std::fclose(f);
                    }
                    if (mode.exchange(m) != m) {
                        std::printf("bbport-order (48): depth EQUAL mode %d\\n", m);
                        std::fflush(stdout);
                    }
                }
                const bool writes = regs.depth_control.depth_write_enable &&
                                    !regs.depth_render_control.depth_clear_enable;
                if (bb_cmp == vk::CompareOp::eEqual && !writes) {
                    if (!told.exchange(true)) {
                        std::printf("bbport-order (48): game memakai depth EQUAL tanpa tulis\\n");
                        std::fflush(stdout);
                    }
                    switch (mode.load(std::memory_order_relaxed)) {
                    case 1: bb_cmp = vk::CompareOp::eLessOrEqual; break;
                    case 2: bb_cmp = vk::CompareOp::eGreaterOrEqual; break;
                    case 3: bb_cmp = vk::CompareOp::eAlways; break;
                    default: break;
                    }
                }
            }
        }
        dynamic_state.SetDepthCompareOp(bb_cmp);
"""


def depth_equal():
    path = BBPORT / 'gpu' / 'shadps4' / 'video_core' / 'renderer_vulkan' / 'vk_rasterizer.cpp'
    text = read(path)
    if 'bbport-order (48)' in text:
        print('48. depth EQUAL dilonggarkan (BB_ORDER_DEPTHEQ_FILE): sudah dipatch')
        return
    if text.count(DEQ_OLD) != 1:
        sys.exit('bagian 48: titik sisip tidak ditemukan di vk_rasterizer.cpp')
    write(path, text.replace(DEQ_OLD, DEQ_NEW, 1))
    print('48. depth EQUAL tanpa tulis bisa diganti saat main (BB_ORDER_DEPTHEQ_FILE, 0..3)')


# --- 49. Bintik wajah: MSAA game dibuat 1 sampel (port GOW3_NO_MSAA) (16 Okt 23:15) ---
# Dari port God of War III (github.com/FelipePrado0/gow3_pc, gpu/shadps4/video_core/amdgpu/
# gow3_msaa.h, GPL-2.0-or-later): image multisample game dibuat dan dibaca sebagai 1 sampel.
# Ukuran/alamat di memori guest tetap memakai jumlah sampel asli (GuestNumSamples / guest_samples).
# The Order: depth 4 sampel + warna 2 sampel (EQAA), TAA 92311aca membaca tiap sampel; titik hitam
# sudah ada di sampel MSAA sebelum TAA (bagian 42, img 3). Saklar BB_ORDER_NO_MSAA=1 (bawaan mati).
# Cache shader harus dihapus.
NOMSAA_HDR = """// SPDX-License-Identifier: GPL-2.0-or-later
// bbport-order (49): image multisample game dibuat 1 sampel (BB_ORDER_NO_MSAA=1).
// Diadaptasi dari port God of War III (FelipePrado0/gow3_pc, gow3_msaa.h, GPL-2.0-or-later).
#pragma once

#include <cstdlib>

namespace AmdGpu {

inline bool NoMsaa() {
    static const bool value = [] {
        const char* e = std::getenv("BB_ORDER_NO_MSAA");
        return e != nullptr && e[0] == '1';
    }();
    return value;
}

} // namespace AmdGpu
"""
NOMSAA_INC = '#include "video_core/amdgpu/bbport_order_msaa.h" // bbport-order (49)\n'
NOMSAA_EDITS = {
    'video_core/amdgpu/regs_color.h': [
        ('#include "video_core/amdgpu/tiling.h"\n', '#include "video_core/amdgpu/tiling.h"\n' + NOMSAA_INC, 1),
        ("    u32 NumSamples() const {\n        return 1 << attrib.num_fragments_log2;\n    }\n",
         "    u32 GuestNumSamples() const { // bbport-order (49)\n        return 1 << attrib.num_fragments_log2;\n    }\n"
         "    u32 NumSamples() const {\n        return NoMsaa() ? 1 : GuestNumSamples();\n    }\n", 1),
        ("* 64u * NumSamples();", "* 64u * GuestNumSamples();", 1)],
    'video_core/amdgpu/regs_depth.h': [
        ('#include "video_core/amdgpu/tiling.h"\n', '#include "video_core/amdgpu/tiling.h"\n' + NOMSAA_INC, 1),
        ("    u32 NumSamples() const {\n        return 1u << z_info.num_samples; // spec doesn't say it is a log2\n    }\n",
         "    u32 GuestNumSamples() const { // bbport-order (49)\n        return 1u << z_info.num_samples; // spec doesn't say it is a log2\n    }\n"
         "    u32 NumSamples() const {\n        return NoMsaa() ? 1 : GuestNumSamples();\n    }\n", 1),
        ("* bpe * NumSamples();", "* bpe * GuestNumSamples();", 1)],
    'video_core/amdgpu/regs_primitive.h': [
        ('#include "common/types.h"\n', '#include "common/types.h"\n' + NOMSAA_INC, 1),
        ("        return 1 << msaa_num_samples;\n",
         "        return NoMsaa() ? 1 : 1 << msaa_num_samples; // bbport-order (49)\n", 1)],
    'video_core/amdgpu/resource.h': [
        ('#include "video_core/amdgpu/pixel_format.h"\n', '#include "video_core/amdgpu/pixel_format.h"\n' + NOMSAA_INC, 1),
        ("    u32 NumLevels() const {\n        if (GetType() == ImageType::Color2DMsaa || GetType() == ImageType::Color2DMsaaArray) {\n            return 1;\n        }\n        return last_level + 1;\n    }\n\n"
         "    u32 NumSamples() const {\n        if (GetType() == ImageType::Color2DMsaa || GetType() == ImageType::Color2DMsaaArray) {\n            return 1u << last_level;\n        }\n        return 1;\n    }\n",
         "    // bbport-order (49): tipe multisample milik guest (last_level = jumlah sampel)\n"
         "    bool IsGuestMsaa() const noexcept {\n        return static_cast<ImageType>(type) == ImageType::Color2DMsaa ||\n"
         "               static_cast<ImageType>(type) == ImageType::Color2DMsaaArray;\n    }\n\n"
         "    u32 NumLevels() const {\n        if (IsGuestMsaa()) {\n            return 1;\n        }\n        return last_level + 1;\n    }\n\n"
         "    u32 GuestNumSamples() const {\n        return IsGuestMsaa() ? 1u << last_level : 1;\n    }\n\n"
         "    u32 NumSamples() const {\n        return NoMsaa() ? 1 : GuestNumSamples();\n    }\n", 1),
        ("    ImageType GetType() const noexcept {\n        return IsCube() ? ImageType::Color2DArray : static_cast<ImageType>(type);\n    }\n",
         "    ImageType GetType() const noexcept {\n        if (NoMsaa() && IsGuestMsaa()) { // bbport-order (49): dibaca tanpa indeks sampel\n"
         "            return static_cast<ImageType>(type) == ImageType::Color2DMsaa ? ImageType::Color2D\n"
         "                                                                          : ImageType::Color2DArray;\n        }\n"
         "        return IsCube() ? ImageType::Color2DArray : static_cast<ImageType>(type);\n    }\n", 1),
        ("CalculateMacrotileMode(tile_mode, bpp, NumSamples())", "CalculateMacrotileMode(tile_mode, bpp, GuestNumSamples())", 1)],
    'video_core/texture_cache/image_info.h': [
        ("    u32 num_samples = 1;\n",
         "    u32 num_samples = 1;\n    u32 guest_samples = 1; // bbport-order (49): jumlah sampel di memori guest\n", 1)],
    'video_core/texture_cache/image_info.cpp': [
        ("num_samples = buffer.NumSamples();\n", "num_samples = buffer.NumSamples();\n    guest_samples = buffer.GuestNumSamples(); // bbport-order (49)\n", 2),
        ("num_samples = image.NumSamples();\n", "num_samples = image.NumSamples();\n    guest_samples = image.GuestNumSamples(); // bbport-order (49)\n", 1),
        ("num_bits, num_samples", "num_bits, guest_samples", 6)],
    'shader_recompiler/backend/spirv/emit_spirv_image.cpp': [
        ("            operands.Add(spv::ImageOperandsMask::Lod, lod);\n            operands.Add(spv::ImageOperandsMask::Sample, ms);\n",
         "            operands.Add(spv::ImageOperandsMask::Lod, lod);\n"
         "            // bbport-order (49): image non-multisample tidak boleh diberi operand Sample\n", 1)],
}


def no_msaa():
    root = BBPORT / 'gpu' / 'shadps4'
    hdr = root / 'video_core' / 'amdgpu' / 'bbport_order_msaa.h'
    texts = {f: read(root / f) for f in NOMSAA_EDITS}
    if hdr.exists() and all('bbport-order (49)' in t for t in texts.values()):
        print('49. MSAA game 1 sampel (BB_ORDER_NO_MSAA): sudah dipatch')
        return
    for f, edits in NOMSAA_EDITS.items():
        if 'bbport-order (49)' in texts[f]:
            continue
        for old, _, n in edits:
            if texts[f].count(old) != n:
                sys.exit(f'bagian 49: titik sisip tidak ditemukan di {f}')
    write(hdr, NOMSAA_HDR)
    for f, edits in NOMSAA_EDITS.items():
        if 'bbport-order (49)' in texts[f]:
            continue
        t = texts[f]
        for old, new, _ in edits:
            t = t.replace(old, new)
        write(root / f, t)
    print('49. MSAA game dibuat 1 sampel, saklar BB_ORDER_NO_MSAA=1 (bawaan mati, port dari GoW3)')


# --- 50. Bintik wajah: matikan stencil / depth bounds / depth test saat main (16 Okt 23:20) ---
# MSAA 1 sampel (49) tidak berubah. Titik hitam = piksel yang TIDAK digambar pass warna (tetap warna
# clear; output PS yang tergambar bersih, bagian 45). Penolak per piksel yang tersisa: stencil (kulit
# biasanya ditandai stencil untuk efek kulit), depth bounds, depth test. Isi stencil/HTILE yang
# acak tiap frame akan memberi pola acak seperti di video.
# BB_ORDER_DSFLAGS_FILE=path, angka bit (dibaca ulang tiap 0,5 detik): 1 = stencil test mati,
# 2 = depth bounds mati, 4 = depth test mati untuk draw yang tidak menulis depth, 8 = depth bias mati.
DS_HELPER_OLD = "void Rasterizer::UpdateDepthStencilState() const {\n"
DS_HELPER_NEW = """// bbport-order (50): BB_ORDER_DSFLAGS_FILE -> bit 1 stencil, 2 depth bounds, 4 depth test (tanpa
// tulis), 8 depth bias dimatikan.
static int BbOrderDsFlags() {
    static const char* path = std::getenv("BB_ORDER_DSFLAGS_FILE");
    static std::atomic<int> flags{0};
    static std::atomic<long long> next{0};
    if (path == nullptr) {
        return 0;
    }
    const long long now = std::chrono::duration_cast<std::chrono::milliseconds>(
                              std::chrono::steady_clock::now().time_since_epoch())
                              .count();
    long long expected = next.load(std::memory_order_relaxed);
    if (now >= expected && next.compare_exchange_strong(expected, now + 500)) {
        int v = 0;
        if (FILE* f = std::fopen(path, "r")) {
            if (std::fscanf(f, "%d", &v) != 1) {
                v = 0;
            }
            std::fclose(f);
        }
        if (flags.exchange(v) != v) {
            std::printf("bbport-order (50): depth/stencil flags %d\\n", v);
            std::fflush(stdout);
        }
    }
    return flags.load(std::memory_order_relaxed);
}

""" + DS_HELPER_OLD
DS_EDITS = [
    ("    const auto depth_test_enabled =\n        regs.depth_control.depth_enable && regs.depth_buffer.DepthValid();\n",
     "    const auto depth_test_enabled =\n        regs.depth_control.depth_enable && regs.depth_buffer.DepthValid() &&\n"
     "        !((BbOrderDsFlags() & 4) != 0 && !regs.depth_control.depth_write_enable); // bbport-order (50)\n"),
    ("    const auto depth_bounds_test_enabled = regs.depth_control.depth_bounds_enable;\n",
     "    const auto depth_bounds_test_enabled =\n        regs.depth_control.depth_bounds_enable && (BbOrderDsFlags() & 2) == 0; // bbport-order (50)\n"),
    ("    const auto depth_bias_enabled = regs.polygon_control.NeedsBias();\n",
     "    const auto depth_bias_enabled =\n        regs.polygon_control.NeedsBias() && (BbOrderDsFlags() & 8) == 0; // bbport-order (50)\n"),
    ("    const auto stencil_test_enabled =\n        regs.depth_control.stencil_enable && regs.depth_buffer.StencilValid();\n",
     "    const auto stencil_test_enabled = regs.depth_control.stencil_enable &&\n"
     "                                      regs.depth_buffer.StencilValid() &&\n"
     "                                      (BbOrderDsFlags() & 1) == 0; // bbport-order (50)\n"),
]


def ds_flags():
    path = BBPORT / 'gpu' / 'shadps4' / 'video_core' / 'renderer_vulkan' / 'vk_rasterizer.cpp'
    text = read(path)
    if 'bbport-order (50)' in text:
        print('50. stencil/depth bounds/depth test saat main (BB_ORDER_DSFLAGS_FILE): sudah dipatch')
        return
    for old in [DS_HELPER_OLD] + [o for o, _ in DS_EDITS]:
        if text.count(old) != 1:
            sys.exit('bagian 50: titik sisip tidak ditemukan di vk_rasterizer.cpp')
    text = text.replace(DS_HELPER_OLD, DS_HELPER_NEW, 1)
    for old, new in DS_EDITS:
        text = text.replace(old, new, 1)
    write(path, text)
    print('50. stencil/depth bounds/depth test/bias bisa dimatikan saat main (BB_ORDER_DSFLAGS_FILE)')


# --- 51. Bintik wajah: barycentric I/J salah komponen di jalur VK_KHR_fragment_shader_barycentric ---
# (16 Okt 23:35) Shader kulit f5c17eec menginterpolasi sendiri atribut f16 yang dipaket (lihat juga
# shadPS4 PR #4798, "The Order: 1886 relies on this to unpack f16-packed attributes"):
#   v = P0 + I * (P1 - P0) + J * (P2 - P0)        (IR: %181 = v1 - v0; %182 = %123(I) * %181; ...)
# Di GCN, I menimbang verteks 1 dan J verteks 2 (V_INTERP_P1: VDST = P10 * I + P0). BaryCoordKHR
# (NVIDIA) adalah vec3 (b0, b1, b2) untuk verteks 0, 1, 2, jadi I = b1 dan J = b2. shadPS4/bbport
# mengambil komponen `comp` (I = b0, J = b1): bobotnya terputar, nilai salah dan patah di tepi
# segitiga. Jalur pull-model di file yang sama sudah memakai comp + 1. HASIL: layar rusak total ->
# bawaan MATI, BB_ORDER_BARYFIX=1 untuk mencoba. Cache shader harus dihapus.
BARY_HELPER_OLD = "Id EmitGetAttribute(EmitContext& ctx, IR::Attribute attr, u32 comp, u32 index) {\n"
BARY_HELPER_NEW = """// bbport-order (51): BaryCoordKHR = (b0, b1, b2); GCN I/J = bobot verteks 1/2 -> komponen comp + 1.
static u32 BbOrderBaryComp(const EmitContext& ctx, u32 comp) {
    static const bool fix = [] { // bawaan MATI: dengan ini layar rusak total (16 Okt 23:21)
        const char* e = std::getenv("BB_ORDER_BARYFIX");
        return e != nullptr && e[0] == '1';
    }();
    return (fix && !ctx.profile.supports_amd_shader_explicit_vertex_parameter) ? comp + 1 : comp;
}

""" + BARY_HELPER_OLD
BARY_EDITS = [
    ("            return ctx.OpCompositeExtract(ctx.F32[1], ctx.OpLoad(ctx.F32[3], ctx.bary_coord), comp);\n",
     "            return ctx.OpCompositeExtract(ctx.F32[1], ctx.OpLoad(ctx.F32[3], ctx.bary_coord),\n"
     "                                          BbOrderBaryComp(ctx, comp)); // bbport-order (51)\n"),
    ("                ctx.F32[1], ctx.OpInterpolateAtCentroid(ctx.F32[3], ctx.bary_coord), comp);\n",
     "                ctx.F32[1], ctx.OpInterpolateAtCentroid(ctx.F32[3], ctx.bary_coord),\n"
     "                BbOrderBaryComp(ctx, comp)); // bbport-order (51)\n"),
    ("                                          ctx.OpLoad(ctx.U32[1], ctx.sample_index)),\n                comp);\n",
     "                                          ctx.OpLoad(ctx.U32[1], ctx.sample_index)),\n"
     "                BbOrderBaryComp(ctx, comp)); // bbport-order (51)\n"),
    ("        return ctx.OpLoad(ctx.F32[1], ctx.OpAccessChain(ctx.input_f32, ctx.bary_coord_nopersp,\n"
     "                                                        ctx.ConstU32(comp)));\n",
     "        return ctx.OpLoad(ctx.F32[1], ctx.OpAccessChain(ctx.input_f32, ctx.bary_coord_nopersp,\n"
     "                                                        ctx.ConstU32(BbOrderBaryComp(ctx, comp)))); // bbport-order (51)\n"),
    ("            ctx.OpAccessChain(ctx.input_f32, ctx.bary_coord_nopersp_sample, ctx.ConstU32(comp)));\n",
     "            ctx.OpAccessChain(ctx.input_f32, ctx.bary_coord_nopersp_sample,\n"
     "                              ctx.ConstU32(BbOrderBaryComp(ctx, comp)))); // bbport-order (51)\n"),
]


BARY_OFF_LINES = (
    '''    static const bool fix = [] {
        const char* e = std::getenv("BB_ORDER_BARYFIX");
        return e == nullptr || e[0] != '0';
    }();''',
    '''    static const bool fix = [] { // bawaan MATI: dengan ini layar rusak total (16 Okt 23:21)
        const char* e = std::getenv("BB_ORDER_BARYFIX");
        return e != nullptr && e[0] == '1';
    }();''')


def bary_fix():
    path = BBPORT / 'gpu' / 'shadps4' / 'shader_recompiler' / 'backend' / 'spirv' / 'emit_spirv_context_get_set.cpp'
    text = read(path)
    old_on = BARY_HELPER_NEW.replace(BARY_OFF_LINES[1], BARY_OFF_LINES[0])
    if old_on in text:  # versi pertama (bawaan nyala) -> bawaan mati
        write(path, text.replace(old_on, BARY_HELPER_NEW, 1))
        print('51. barycentric fix diubah ke bawaan MATI (BB_ORDER_BARYFIX=1 untuk menyalakan)')
        return
    if 'bbport-order (51)' in text:
        print('51. barycentric I/J = b1/b2 (BB_ORDER_BARYFIX): sudah dipatch')
        return
    for old in [BARY_HELPER_OLD] + [o for o, _ in BARY_EDITS]:
        if text.count(old) != 1:
            sys.exit('bagian 51: titik sisip tidak ditemukan di emit_spirv_context_get_set.cpp')
    text = text.replace(BARY_HELPER_OLD, BARY_HELPER_NEW, 1)
    for old, new in BARY_EDITS:
        text = text.replace(old, new, 1)
    if '#include <cstdlib>' not in text:
        text = '#include <cstdlib>\n' + text
    write(path, text)
    print('51. barycentric I/J b1/b2 di jalur KHR (bawaan MATI, BB_ORDER_BARYFIX=1)')


# --- 52. Bintik wajah: dump isi image yang dipakai compute tertentu (16 Okt 23:45) ---
# Diadaptasi dari diagnosa port God of War III (GOW3_DIAG_IMAGES, texture_cache.cpp DiagDumpImage,
# FelipePrado0/gow3_pc, GPL-2.0-or-later). Saat frame capture merekam (BB_CAPTURE_TRIGGER), sesudah
# dispatch compute yang hash-nya ada di BB_ORDER_DIAG_CS (hex, dipisah koma), semua image yang
# terikat ditulis mentah ke BB_ORDER_DIAG_DIR: <no>_<tag>_<alamat>_<WxH>_p<pitch>_b<bpp>_f<format>.raw
# Image MSAA tidak bisa disalin -> pakai bersama BB_ORDER_NO_MSAA=1.
DIAG_H_OLD = "    void DownloadImageMemory(ImageId image_id, bool sync = false);\n"
DIAG_H_NEW_V1 = DIAG_H_OLD + """
    /// bbport-order (52): level 0 image warna ditulis mentah ke BB_ORDER_DIAG_DIR (diagnosa).
    void BbOrderDumpImage(ImageId image_id, const char* tag);
"""
DIAG_H_NEW = DIAG_H_OLD + """
public:
    /// bbport-order (52): level 0 image warna ditulis mentah ke BB_ORDER_DIAG_DIR (diagnosa).
    void BbOrderDumpImage(ImageId image_id, const char* tag);

private:
"""
DIAG_CPP_OLD = "void TextureCache::DownloadImageMemory(ImageId image_id, bool sync) {\n"
DIAG_CPP_NEW = """// bbport-order (52): dari diagnosa port GoW3 (DiagDumpImage, GPL-2.0-or-later).
void TextureCache::BbOrderDumpImage(ImageId image_id, const char* tag) {
    Image& image = slot_images[image_id];
    const u32 bytes_per_pixel = image.info.num_bits / 8;
    if (image.info.props.is_depth || image.info.props.is_block || bytes_per_pixel == 0 ||
        image.info.num_samples > 1) {
        return;
    }
    const u32 size = image.info.pitch * image.info.size.height * bytes_per_pixel;
    const auto download = runtime.GetStagingPool().Request(size, MemoryType::HostCached, 16);
    const vk::BufferImageCopy copy = {
        .bufferOffset = download.offset,
        .bufferRowLength = image.info.pitch,
        .bufferImageHeight = image.info.size.height,
        .imageSubresource = {vk::ImageAspectFlagBits::eColor, 0, 0, 1},
        .imageOffset = {0, 0, 0},
        .imageExtent = {image.info.size.width, image.info.size.height, 1},
    };
    runtime.DownloadImage(&image, download.buffer, std::span{&copy, 1});
    scheduler.Finish();
    download.Invalidate();
    static int sequence = 0;
    const char* dir = std::getenv("BB_ORDER_DIAG_DIR");
    const char* dir_path = dir && *dir ? dir : ".";
    char path[512];
    std::snprintf(path, sizeof(path), "%s/%03d_%s_%llx_%ux%u_p%u_b%u_f%d.raw", dir_path, sequence++,
                  tag, static_cast<unsigned long long>(image.info.guest_address),
                  image.info.size.width, image.info.size.height, image.info.pitch, bytes_per_pixel,
                  static_cast<int>(image.info.pixel_format));
    if (FILE* f = std::fopen(path, "wb")) {
        std::fwrite(download.mapped, 1, size, f);
        std::fclose(f);
        std::printf("bbport-order (52): dump %s\\n", path);
    } else {
        std::printf("bbport-order (52): gagal menulis %s\\n", path);
    }
    std::fflush(stdout);
}

""" + DIAG_CPP_OLD
DIAG_RAS_OLD = "        cmdbuf.dispatch(dim_x, dim_y, dim_z);\n    });\n    DebugState.IncDispatch();\n"
DIAG_RAS_NEW = DIAG_RAS_OLD + """    { // bbport-order (52): BB_ORDER_DIAG_CS -> image dispatch ini ditulis saat frame capture
        static const char* list = std::getenv("BB_ORDER_DIAG_CS");
        if (list != nullptr && FrameCapture::Active()) {
            bool hit = false;
            const char* p = list;
            while (*p != 0) {
                char* end = nullptr;
                const unsigned long long v = std::strtoull(p, &end, 16);
                if (end == p) {
                    break;
                }
                hit |= v == cs.pgm_hash;
                p = (*end == ',') ? end + 1 : end;
            }
            if (hit) {
                char tag[32];
                std::snprintf(tag, sizeof(tag), "cs%08x", static_cast<u32>(cs.pgm_hash));
                const auto images = bound_images;
                for (const auto image_id : images) {
                    texture_cache.BbOrderDumpImage(image_id, tag);
                }
            }
        }
    }
"""


def diag_dump():
    root = BBPORT / 'gpu' / 'shadps4' / 'video_core'
    files = [(root / 'texture_cache' / 'texture_cache.h', DIAG_H_OLD, DIAG_H_NEW),
             (root / 'texture_cache' / 'texture_cache.cpp', DIAG_CPP_OLD, DIAG_CPP_NEW),
             (root / 'renderer_vulkan' / 'vk_rasterizer.cpp', DIAG_RAS_OLD, DIAG_RAS_NEW)]
    texts = [read(p) for p, _, _ in files]
    if DIAG_H_NEW_V1 in texts[0] and DIAG_H_NEW not in texts[0]:  # versi pertama: fungsi private
        texts[0] = texts[0].replace(DIAG_H_NEW_V1, DIAG_H_NEW, 1)
        write(files[0][0], texts[0])
        print('52. BbOrderDumpImage dijadikan public')
    if all('bbport-order (52)' in t for t in texts):
        print('52. dump image compute (BB_ORDER_DIAG_CS): sudah dipatch')
        return
    for (p, old, _), t in zip(files, texts):
        if 'bbport-order (52)' not in t and t.count(old) != 1:
            sys.exit(f'bagian 52: titik sisip tidak ditemukan di {p.name}')
    for (p, old, new), t in zip(files, texts):
        if 'bbport-order (52)' not in t:
            write(p, t.replace(old, new, 1))
    print('52. dump image compute saat capture (BB_ORDER_DIAG_CS=hash, BB_ORDER_DIAG_DIR=folder)')


# --- 53. Bintik wajah: emulasi clip distance NVIDIA bisa dimatikan (17 Okt 00:00) ---
# Dump bagian 52 (frame berbintik): di warna adegan sebelum TAA, piksel titik punya alpha 0 dan warna
# hampir nol (0.00056, 0.0007, 0.00077), tetangganya alpha 1 (shader kulit selalu menulis alpha 1).
# Velocity dari prepass ADA di piksel itu -> prepass menggambar, pass warna TIDAK (fragmen dibuang).
# Penolak yang belum diuji: emulasi clip distance bbport di NVIDIA (fragment discard bila jarak < 0).
# BB_ORDER_CLIPEMU=0 -> clip distance asli Vulkan (tanpa emulasi). Log: pipeline yang memakai emulasi.
CLIP_PROFILE_OLD = "        .needs_clip_distance_emulation = instance.GetDriverID() == vk::DriverId::eNvidiaProprietary,\n"
CLIP_PROFILE_NEW = """        .needs_clip_distance_emulation = // bbport-order (53): BB_ORDER_CLIPEMU=0 mematikan
            instance.GetDriverID() == vk::DriverId::eNvidiaProprietary && [] {
                const char* e = std::getenv("BB_ORDER_CLIPEMU");
                return e == nullptr || e[0] != '0';
            }(),
"""
CLIP_LOG_OLD = "            profile.needs_clip_distance_emulation;\n        break;\n"
CLIP_LOG_NEW = """            profile.needs_clip_distance_emulation;
        if (info.hw.fs.clip_distance_emulation) { // bbport-order (53)
            static std::atomic<u32> told53{0};
            if (told53.fetch_add(1) < 32) {
                std::printf("bbport-order (53): emulasi clip distance (clip_distance_enable %u, user "
                            "plane %u)\\n",
                            u32(regs.vs_output_control.clip_distance_enable),
                            u32(regs.clipper_control.user_clip_plane_enable));
                std::fflush(stdout);
            }
        }
        break;
"""


def clip_emu():
    path = BBPORT / 'gpu' / 'shadps4' / 'video_core' / 'renderer_vulkan' / 'vk_pipeline_cache.cpp'
    text = read(path)
    if 'bbport-order (53)' in text:
        print('53. emulasi clip distance (BB_ORDER_CLIPEMU): sudah dipatch')
        return
    for old in (CLIP_PROFILE_OLD, CLIP_LOG_OLD):
        if text.count(old) != 1:
            sys.exit('bagian 53: titik sisip tidak ditemukan di vk_pipeline_cache.cpp')
    text = text.replace(CLIP_PROFILE_OLD, CLIP_PROFILE_NEW, 1).replace(CLIP_LOG_OLD, CLIP_LOG_NEW, 1)
    if '#include <cstdio>' not in text:
        text = '#include <cstdio>\n' + text
    if '#include <atomic>' not in text:
        text = '#include <atomic>\n' + text
    write(path, text)
    print('53. emulasi clip distance bisa dimatikan (BB_ORDER_CLIPEMU=0), pemakaiannya dicatat')


# --- 54. Bintik wajah: backport shadPS4 c34ca21 "Preserve EXEC scope after empty branch" (#5220) ---
# (17 Okt 00:00) Upstream shadPS4 (2026-10-05, sesudah b4e7ae7 yang di-vendor bbport). Kalau sebuah
# scope EXEC kosong ditutup oleh instruksi yang sekaligus membuka scope baru, scope baru itu hilang:
# instruksi sesudahnya jalan untuk lane yang seharusnya mati (atau sebaliknya). Dump bagian 52:
# piksel titik tidak pernah ditulis pass warna (alpha 0), bentuknya seukuran gelombang (wave) dan
# berubah tiap frame -> cocok dengan EXEC per lane yang salah. Perbaikan upstream 1 baris.
# BB_ORDER_EXECSCOPE=0 kembali ke perilaku lama. Cache shader harus dihapus.
EXEC_OLD = """                if (index - curr_begin == 1 && is_close) {
                    curr_begin = -1;
                    continue;
                }
"""
EXEC_NEW = """                if (index - curr_begin == 1 && is_close) {
                    // bbport-order (54): shadPS4 c34ca21 (#5220), instruksi penutup bisa membuka scope baru
                    static const bool keep = [] {
                        const char* e = std::getenv("BB_ORDER_EXECSCOPE");
                        return e == nullptr || e[0] != '0';
                    }();
                    curr_begin = (keep && is_open_scope(inst)) ? static_cast<s32>(index) : -1;
                    continue;
                }
"""


def exec_scope():
    path = BBPORT / 'gpu' / 'shadps4' / 'shader_recompiler' / 'frontend' / 'control_flow_graph.cpp'
    text = read(path)
    if 'bbport-order (54)' in text:
        print('54. EXEC scope sesudah cabang kosong (shadPS4 #5220): sudah dipatch')
        return
    if text.count(EXEC_OLD) != 1:
        sys.exit('bagian 54: titik sisip tidak ditemukan di control_flow_graph.cpp')
    text = text.replace(EXEC_OLD, EXEC_NEW, 1)
    if '#include <cstdlib>' not in text:
        text = '#include <cstdlib>\n' + text
    write(path, text)
    print('54. backport shadPS4 #5220: EXEC scope sesudah cabang kosong (BB_ORDER_EXECSCOPE=0 mematikan)')


# --- 55. Bintik wajah: discard (demote) di pixel shader dicatat / dimatikan (17 Okt 00:15) ---
# Dump 52: piksel titik tidak ditulis pass warna padahal prepass menggambar. Depth/stencil/bounds
# sudah dilonggarkan tanpa efek; yang tersisa: pixel shader sendiri membuang fragmen (discard/kill,
# mis. dither transisi LOD atau alpha test dengan noise per frame -> pola acak tiap frame).
# BB_ORDER_NODISCARD=log -> tiap shader yang punya discard dicatat (hash), =1 -> dicatat dan
# discard dimatikan. Cache shader harus dihapus.
DISC_OLD = """void EmitDiscard(EmitContext& ctx) {
    ctx.OpDemoteToHelperInvocationEXT();
}

void EmitDiscardCond(EmitContext& ctx, Id condition) {
"""
DISC_NEW = """// bbport-order (55): BB_ORDER_NODISCARD=log|1 -> catat shader dengan discard; 1 = matikan discard.
static int BbOrderNoDiscard(EmitContext& ctx) {
    static const int mode = [] {
        const char* e = std::getenv("BB_ORDER_NODISCARD");
        return e == nullptr ? 0 : (e[0] == '1' ? 2 : 1);
    }();
    if (mode != 0) {
        static std::mutex m;
        static std::unordered_set<u64> told;
        std::scoped_lock lock{m};
        if (told.insert(ctx.info.pgm_hash).second) {
            std::printf("bbport-order (55): discard di shader %llx%s\\n",
                        (unsigned long long)ctx.info.pgm_hash, mode == 2 ? " (dimatikan)" : "");
            std::fflush(stdout);
        }
    }
    return mode;
}

void EmitDiscard(EmitContext& ctx) {
    if (BbOrderNoDiscard(ctx) == 2) {
        return;
    }
    ctx.OpDemoteToHelperInvocationEXT();
}

void EmitDiscardCond(EmitContext& ctx, Id condition) {
    if (BbOrderNoDiscard(ctx) == 2) {
        return;
    }
"""
DISC_INC_OLD = '#include "shader_recompiler/backend/spirv/emit_spirv_instructions.h"\n'
DISC_INC_NEW = ('#include <cstdio>\n#include <cstdlib>\n#include <mutex>\n#include <unordered_set>\n'
                + DISC_INC_OLD)


def no_discard():
    path = BBPORT / 'gpu' / 'shadps4' / 'shader_recompiler' / 'backend' / 'spirv' / 'emit_spirv_special.cpp'
    text = read(path)
    if 'bbport-order (55)' in text:
        print('55. discard dicatat/dimatikan (BB_ORDER_NODISCARD): sudah dipatch')
        return
    for old in (DISC_OLD, DISC_INC_OLD):
        if text.count(old) != 1:
            sys.exit('bagian 55: titik sisip tidak ditemukan di emit_spirv_special.cpp')
    text = text.replace(DISC_INC_OLD, DISC_INC_NEW, 1).replace(DISC_OLD, DISC_NEW, 1)
    write(path, text)
    print('55. discard pixel shader: BB_ORDER_NODISCARD=log (catat) atau 1 (matikan)')


# --- 56. Bintik wajah: depth test mati untuk SEMUA draw (bit 16 di BB_ORDER_DSFLAGS_FILE) (17 Okt 00:20) ---
# Dump 52: 469 piksel alpha 0 (semuanya di wajah, 36 kelompok) = pass warna tidak menulis. Discard (55)
# bukan penyebab. Bit 4 (bagian 50) hanya untuk draw tanpa tulis depth; kalau draw kulit menulis depth,
# tesnya belum pernah dimatikan. Bit 16: depth test mati untuk semua draw (gambar jadi berantakan,
# hanya untuk diagnosa): lubang terisi -> ditolak depth; tetap lubang -> segitiga memang tidak tergambar.
DS16_OLD = "        !((BbOrderDsFlags() & 4) != 0 && !regs.depth_control.depth_write_enable); // bbport-order (50)\n"
DS16_NEW = ("        !((BbOrderDsFlags() & 4) != 0 && !regs.depth_control.depth_write_enable) && // bbport-order (50)\n"
            "        (BbOrderDsFlags() & 16) == 0; // bbport-order (56): semua draw\n")


def ds_all():
    path = BBPORT / 'gpu' / 'shadps4' / 'video_core' / 'renderer_vulkan' / 'vk_rasterizer.cpp'
    text = read(path)
    if 'bbport-order (56)' in text:
        print('56. depth test mati untuk semua draw (bit 16): sudah dipatch')
        return
    if text.count(DS16_OLD) != 1:
        sys.exit('bagian 56: titik sisip tidak ditemukan (bagian 50 dulu)')
    write(path, text.replace(DS16_OLD, DS16_NEW, 1))
    print('56. BB_ORDER_DSFLAGS_FILE bit 16: depth test mati untuk semua draw')


# --- 57. Bintik wajah: depth test mati hanya untuk draw dengan >= 2 render target (bit 32) ---
# (17 Okt 00:25) Bit 16 (semua draw) merusak seluruh layar (kabut/efek layar penuh ikut). Pass warna
# utama (#65) menulis 2 target (warna 1920x800 + A2B10G10R10); efek layar penuh hanya 1. Bit 32:
# depth test mati hanya untuk draw dengan color_buffers[0] dan [1] terpasang. Dipakai bersama dump
# (bagian 52): hitung piksel alpha 0 di wajah.
DS32_OLD = "        (BbOrderDsFlags() & 16) == 0; // bbport-order (56): semua draw\n"
DS32_NEW = ("        (BbOrderDsFlags() & 16) == 0 && // bbport-order (56): semua draw\n"
            "        !((BbOrderDsFlags() & 32) != 0 && regs.color_buffers[0] && regs.color_buffers[1]); // bbport-order (57)\n")


def ds_mrt():
    path = BBPORT / 'gpu' / 'shadps4' / 'video_core' / 'renderer_vulkan' / 'vk_rasterizer.cpp'
    text = read(path)
    if 'bbport-order (57)' in text:
        print('57. depth test mati untuk draw 2 target (bit 32): sudah dipatch')
        return
    if text.count(DS32_OLD) != 1:
        sys.exit('bagian 57: titik sisip tidak ditemukan (bagian 56 dulu)')
    write(path, text.replace(DS32_OLD, DS32_NEW, 1))
    print('57. BB_ORDER_DSFLAGS_FILE bit 32: depth test mati untuk draw dengan 2 render target')


# --- 58. Bintik wajah: depth bias kecil untuk pass warna 2 target (bit 64 / 128) (17 Okt 00:35) ---
# Dump dengan bit 32 (depth test mati untuk pass warna 2 target): piksel alpha 0 = 0, artinya lubang
# berasal dari DEPTH TEST pass warna (bukan geometri, bukan discard). Tapi tanpa depth test benda lain
# ikut menimpa wajah, jadi itu bukan perbaikan. Dugaan: kedalaman pass warna sedikit berbeda dari
# prepass (VS lain). Bit 64: depth bias -64 / slope -1 (ke arah kamera, Z biasa), bit 128: +64 / +1
# (Z terbalik), hanya untuk draw dengan 2 render target.
DB_OLD = "            (front ? regs.poly_offset.front_scale : regs.poly_offset.back_scale) / 16.f);\n    }\n"
DB_NEW = DB_OLD + """    if ((BbOrderDsFlags() & (64 | 128)) != 0 && regs.color_buffers[0] &&
        regs.color_buffers[1]) { // bbport-order (58): depth bias diagnosa untuk pass warna
        const float sign = (BbOrderDsFlags() & 64) != 0 ? -1.f : 1.f;
        dynamic_state.SetDepthBiasEnabled(true);
        dynamic_state.SetDepthBias(sign * 64.f, 0.f, sign * 1.f);
    }
"""


def depth_bias_test():
    path = BBPORT / 'gpu' / 'shadps4' / 'video_core' / 'renderer_vulkan' / 'vk_rasterizer.cpp'
    text = read(path)
    if 'bbport-order (58)' in text:
        print('58. depth bias diagnosa (bit 64/128): sudah dipatch')
        return
    if text.count(DB_OLD) != 1:
        sys.exit('bagian 58: titik sisip tidak ditemukan di vk_rasterizer.cpp')
    write(path, text.replace(DB_OLD, DB_NEW, 1))
    print('58. BB_ORDER_DSFLAGS_FILE bit 64/128: depth bias -/+ untuk pass warna 2 target')


# --- 59. PERBAIKAN bintik wajah: depth bias kecil untuk pass warna (bawaan NYALA) (17 Okt 00:40) ---
# Dump terukur (bagian 52/58, 1080p, MSAA 1 sampel): piksel lubang (alpha 0) di wajah:
#   normal 477 / 628, bias -64 & slope -1 (bit 64) 0 / 0, bias +64 (bit 128) 877 / 448.
# Gambar dengan bias -64 bersih, tidak ada benda hilang atau z-fighting yang terlihat.
# Jadi kedalaman kulit di pass warna sedikit lebih JAUH dari prepass (Z biasa: dekat = kecil); tes
# depth pass warna menolak sebagian piksel. Perbaikan: draw dengan 2 render target (pass warna utama),
# depth test aktif dan tanpa bias dari game sendiri -> depth bias -64 / slope -1.
# BB_ORDER_FACEFIX=0 mematikan.
FF_OLD = """    if ((BbOrderDsFlags() & (64 | 128)) != 0 && regs.color_buffers[0] &&
        regs.color_buffers[1]) { // bbport-order (58): depth bias diagnosa untuk pass warna
"""
FF_NEW = """    { // bbport-order (59): perbaikan bintik wajah, kedalaman pass warna vs prepass
        static const bool facefix = [] {
            const char* e = std::getenv("BB_ORDER_FACEFIX");
            return e == nullptr || e[0] != '0';
        }();
        if (facefix && (BbOrderDsFlags() & (64 | 128)) == 0 && !depth_bias_enabled &&
            depth_test_enabled && regs.color_buffers[0] && regs.color_buffers[1]) {
            dynamic_state.SetDepthBiasEnabled(true);
            dynamic_state.SetDepthBias(-64.f, 0.f, -1.f);
        }
    }
""" + FF_OLD


def face_fix():
    path = BBPORT / 'gpu' / 'shadps4' / 'video_core' / 'renderer_vulkan' / 'vk_rasterizer.cpp'
    text = read(path)
    if 'bbport-order (59)' in text:
        print('59. perbaikan bintik wajah (BB_ORDER_FACEFIX): sudah dipatch')
        return
    if text.count(FF_OLD) != 1:
        sys.exit('bagian 59: titik sisip tidak ditemukan (bagian 58 dulu)')
    write(path, text.replace(FF_OLD, FF_NEW, 1))
    print('59. PERBAIKAN bintik wajah: depth bias -64 untuk pass warna (bawaan nyala, BB_ORDER_FACEFIX=0 mati)')


# --- 60. Bintik wajah: besar depth bias bisa diatur saat main (17 Okt 00:45) ---
# Bias -64 / slope -1 (59) menghapus semua lubang di frame capture, tapi saat main biasa titik masih
# terlihat: selisih kedalaman di frame lain bisa lebih besar. BB_ORDER_FACEBIAS_FILE=path berisi
# "<konstanta> <slope>" (positif = ke arah kamera), dibaca ulang tiap 0,5 detik. Tanpa file: 64 1.
FB_OLD = "            dynamic_state.SetDepthBias(-64.f, 0.f, -1.f);\n"
FB_NEW = """            static const char* fb_path = std::getenv("BB_ORDER_FACEBIAS_FILE"); // bbport-order (60)
            static std::atomic<float> fb_const{64.f}, fb_slope{1.f};
            static std::atomic<long long> fb_next{0};
            if (fb_path != nullptr) {
                const long long now = std::chrono::duration_cast<std::chrono::milliseconds>(
                                          std::chrono::steady_clock::now().time_since_epoch())
                                          .count();
                long long expected = fb_next.load(std::memory_order_relaxed);
                if (now >= expected && fb_next.compare_exchange_strong(expected, now + 500)) {
                    float c = 64.f, s = 1.f;
                    if (FILE* f = std::fopen(fb_path, "r")) {
                        if (std::fscanf(f, "%f %f", &c, &s) < 1) {
                            c = 64.f;
                        }
                        std::fclose(f);
                    }
                    if (fb_const.exchange(c) != c || fb_slope.exchange(s) != s) {
                        std::printf("bbport-order (60): face bias %.1f slope %.2f\\n", c, s);
                        std::fflush(stdout);
                    }
                }
            }
            dynamic_state.SetDepthBias(-fb_const.load(), 0.f, -fb_slope.load());
"""


def face_bias_live():
    path = BBPORT / 'gpu' / 'shadps4' / 'video_core' / 'renderer_vulkan' / 'vk_rasterizer.cpp'
    text = read(path)
    if 'bbport-order (60)' in text:
        print('60. besar face bias saat main (BB_ORDER_FACEBIAS_FILE): sudah dipatch')
        return
    if text.count(FB_OLD) != 1:
        sys.exit('bagian 60: titik sisip tidak ditemukan (bagian 59 dulu)')
    write(path, text.replace(FB_OLD, FB_NEW, 1))
    print('60. besar face bias bisa diatur saat main (BB_ORDER_FACEBIAS_FILE "konstanta slope")')


# --- 61. Bintik wajah: waterfall loop InstanceId di vertex shader skinning (17 Okt) ---
# Dump VS wajah (prepass 1077f760/070b542d, warna e0ec7fe0/429d950d): GCN memakai "waterfall loop"
#   mask = ballot(true); loop { l = findLSB(mask); id = readlane(InstanceId, l);
#   if (id == InstanceId) { tulang dibaca pakai readfirstlane(...) } mask &= ~ballot(id == InstanceId) }
# Di SPIR-V readlane = OpGroupNonUniformBroadcast dengan lane dinamis. Di NVIDIA lane di dalam loop
# tidak dijamin konvergen (tanpa maximal reconvergence): lane bisa membaca dari lane yang sudah keluar
# loop -> InstanceId sampah -> matriks tulang salah -> sebagian vertex wajah meleset -> lubang acak.
# Perbaikan: di shader yang punya pola ini, readlane(x, findLSB(..)) -> x dan readfirstlane(x) -> x
# (nilai di badan loop memang seragam antar lane yang lolos, jadi hasilnya sama persis, tapi per lane).
# Setiap lane keluar loop di putaran pertama. BB_ORDER_WATERFALL: bawaan = hanya vertex shader,
# all = semua stage, 0 = mati. Cache shader harus dihapus.
WF_FUNC_ANCHOR = "IR::Program TranslateProgram(const std::span<const u32>& code, Pools& pools, Info& info,\n"
WF_FUNC = r"""// bbport-order (61): waterfall loop (readlane dengan lane findLSB) dijalankan per lane.
static void BbOrderWaterfallPass(IR::Program& program) {
    static const int mode = [] {
        const char* e = std::getenv("BB_ORDER_WATERFALL");
        if (e == nullptr || e[0] == '\0') {
            return 1;
        }
        if (e[0] == '0') {
            return 0;
        }
        return e[0] == 'a' ? 2 : 1;
    }();
    if (mode == 0 || (mode == 1 && program.info.sw_stage != SwStage::Vertex)) {
        return;
    }
    std::vector<IR::Inst*> lanes;
    std::vector<IR::Inst*> firsts;
    for (IR::Block* block : program.blocks) {
        for (IR::Inst& inst : block->Instructions()) {
            if (inst.GetOpcode() == IR::Opcode::ReadLane && !inst.Arg(1).IsImmediate()) {
                IR::Inst* src = inst.Arg(1).Inst();
                if (src->GetOpcode() == IR::Opcode::BallotFindLsb) {
                    lanes.push_back(&inst);
                }
            } else if (inst.GetOpcode() == IR::Opcode::ReadFirstLane) {
                firsts.push_back(&inst);
            }
        }
    }
    if (lanes.empty()) {
        return;
    }
    for (IR::Inst* inst : lanes) {
        inst->ReplaceUsesWithAndRemove(inst->Arg(0));
    }
    for (IR::Inst* inst : firsts) {
        inst->ReplaceUsesWithAndRemove(inst->Arg(0));
    }
    static std::mutex m;
    static std::unordered_set<u64> told;
    std::scoped_lock lock{m};
    if (told.insert(program.info.pgm_hash).second) {
        std::printf("bbport-order (61): waterfall per lane di shader %llx (%zu readlane, %zu readfirstlane)\n",
                    (unsigned long long)program.info.pgm_hash, lanes.size(), firsts.size());
        std::fflush(stdout);
    }
}

""" + WF_FUNC_ANCHOR
WF_CALL_OLD = "    Shader::Optimization::CollectShaderInfoPass(program, profile);\n"
WF_CALL_NEW = ("    BbOrderWaterfallPass(program); // bbport-order (61)\n"
               "    Shader::Optimization::DeadCodeEliminationPass(program);\n" + WF_CALL_OLD)
WF_INC_OLD = '#include "common/logging/classes.h"\n'
WF_INC_NEW = ('#include <cstdio>\n#include <cstdlib>\n#include <mutex>\n#include <unordered_set>\n#include <vector>\n'
              + WF_INC_OLD)

WF_IDENT_OLD = '''                while (src->GetOpcode() == IR::Opcode::Identity && !src->Arg(0).IsImmediate()) {
                    src = src->Arg(0).Inst();
                }
'''


def waterfall_lane():
    path = BBPORT / 'gpu' / 'shadps4' / 'shader_recompiler' / 'recompiler.cpp'
    text = read(path)
    if 'bbport-order (61)' in text:
        if WF_IDENT_OLD in text:  # versi pertama: opcode Identity tidak ada di bbport
            write(path, text.replace(WF_IDENT_OLD, '', 1))
            print('61. waterfall loop per lane: baris Identity dihapus (error build)')
            return
        print('61. waterfall loop per lane di vertex shader (BB_ORDER_WATERFALL): sudah dipatch')
        return
    for old in (WF_FUNC_ANCHOR, WF_CALL_OLD, WF_INC_OLD):
        if text.count(old) != 1:
            sys.exit('bagian 61: titik sisip tidak ditemukan di recompiler.cpp')
    text = text.replace(WF_INC_OLD, WF_INC_NEW, 1).replace(WF_FUNC_ANCHOR, WF_FUNC, 1)
    text = text.replace(WF_CALL_OLD, WF_CALL_NEW, 1)
    write(path, text)
    print('61. waterfall loop InstanceId di vertex shader dijalankan per lane (bawaan nyala, BB_ORDER_WATERFALL=0 mematikan)')


# --- 62. Bintik wajah: vertex buffer shader wajah (diagnosa + upload ulang) (17 Okt 01:10) ---
# 61 (waterfall) sudah aktif di shader wajah tapi bintik tetap. Perbandingan IR: rumus posisi prepass
# (1077f760/070b542d) dan pass warna (e0ec7fe0/429d950d) sama persis, tapi posisi diambil dari vertex
# buffer BERBEDA (prepass slot 0 stride 11 dword, warna slot 2 stride 14). Kalau salah satu salinan di
# buffer cache basi (data frame lain), kedalaman kedua pass tidak sama -> lubang yang berganti tiap frame.
# BB_ORDER_VBDIAG=1 (atau daftar hash): saat capture, tiap binding buffer shader itu dicatat (alamat,
#   ukuran, stride, paged, cpu/gpu modified, checksum isi memori game).
# BB_ORDER_VBFRESH=1 (atau daftar hash): binding baca shader itu di-invalidate sebelum dipakai -> data
#   diunggah ulang dari memori game tiap draw (kecuali yang ditulis GPU). Bawaan keduanya mati.
VB_OLD = """            if (FrameCapture::Active() && vsharp.base_address != 0 && vsharp.GetSize() != 0 &&
                memory->IsValidGpuMapping(vsharp.base_address, 0)) {
                FrameCapture::Buffer("""
VB_NEW = """            { // bbport-order (62): BB_ORDER_VBDIAG / BB_ORDER_VBFRESH
                struct BbVbList {
                    u64 h[48]{};
                    u32 n = 0;
                    bool on = false;
                };
                static const auto parse = [](const char* name) {
                    BbVbList l;
                    const char* e = std::getenv(name);
                    if (e == nullptr || e[0] == '\\0' || e[0] == '0') {
                        return l;
                    }
                    l.on = true;
                    const char* p = (e[0] == '1' && e[1] == '\\0')
                                        ? "1077f760,70b542d,e0ec7fe0,429d950d,bd739cf5,231d370b,"
                                          "190852fd,b2cc4b8f,b938dd39,a369ab85,59c67371,fd7e121b,b68b212f"
                                        : e;
                    while (*p && l.n < 48) {
                        char* end = nullptr;
                        const u64 v = std::strtoull(p, &end, 16);
                        if (end == p) {
                            break;
                        }
                        l.h[l.n++] = v;
                        p = (*end == ',') ? end + 1 : end;
                    }
                    return l;
                };
                static const BbVbList diag = parse("BB_ORDER_VBDIAG");
                static const BbVbList fresh = parse("BB_ORDER_VBFRESH");
                const auto listed = [&](const BbVbList& l) {
                    if (!l.on) {
                        return false;
                    }
                    for (u32 i = 0; i < l.n; i++) {
                        if (l.h[i] == stage.pgm_hash) {
                            return true;
                        }
                    }
                    return false;
                };
                const bool valid = vsharp.base_address != 0 && vsharp.GetSize() != 0 &&
                                   memory->IsValidGpuMapping(vsharp.base_address, 0);
                if (valid && FrameCapture::Active() && listed(diag)) {
                    const u64 sz = std::min<u64>(
                        memory->ClampRangeSize(vsharp.base_address, vsharp.GetSize()), 64ull << 20);
                    const auto* bytes = reinterpret_cast<const u8*>(vsharp.base_address);
                    u64 fnv = 1469598103934665603ull;
                    for (u64 i = 0; i < sz; i++) {
                        fnv = (fnv ^ bytes[i]) * 1099511628211ull;
                    }
                    const auto* f = reinterpret_cast<const float*>(vsharp.base_address);
                    char note[320];
                    std::snprintf(note, sizeof(note),
                                  "\\n  vb vs %08x slot %u at %#llx size %u stride %u w%d paged%d "
                                  "cpumod%d gpumod%d fnv %016llx: %g %g %g %g",
                                  u32(stage.pgm_hash), binding.buffer,
                                  (unsigned long long)vsharp.base_address, u32(vsharp.GetSize()),
                                  u32(vsharp.GetStride()), int(desc.is_written),
                                  int(Shader::IsPagedBuffer(
                                      VideoCore::BufferCache::LayerPagedActive(), vsharp)),
                                  int(buffer_cache.IsRegionCpuModified(vsharp.base_address, sz)),
                                  int(buffer_cache.IsRegionGpuModified(vsharp.base_address, sz)),
                                  (unsigned long long)fnv, f[0], f[1], f[2], f[3]);
                    FrameCapture::Note(note);
                }
                if (valid && !desc.is_written && listed(fresh)) {
                    const u64 sz = memory->ClampRangeSize(vsharp.base_address, vsharp.GetSize());
                    if (!buffer_cache.IsRegionGpuModified(vsharp.base_address, sz)) {
                        buffer_cache.InvalidateMemory(vsharp.base_address, sz);
                    }
                }
            }
""" + VB_OLD


def vb_diag():
    path = BBPORT / 'gpu' / 'shadps4' / 'video_core' / 'renderer_vulkan' / 'vk_rasterizer.cpp'
    text = read(path)
    if 'bbport-order (62)' in text:
        print('62. vertex buffer wajah: diagnosa/upload ulang (BB_ORDER_VBDIAG/VBFRESH): sudah dipatch')
        return
    if text.count(VB_OLD) != 1:
        sys.exit('bagian 62: titik sisip tidak ditemukan di vk_rasterizer.cpp')
    write(path, text.replace(VB_OLD, VB_NEW, 1))
    print('62. vertex buffer wajah: BB_ORDER_VBDIAG=1 (catat saat capture), BB_ORDER_VBFRESH=1 (upload ulang)')


# --- 63. Bintik wajah: isi konstanta (flatbuf) shader wajah saat capture (17 Okt 01:25) ---
# 61/62: rumus posisi prepass dan pass warna identik, vertex buffer dan matriks tulang sama persis.
# Sisa sumber beda kedalaman: konstanta per draw (matriks objek dan view-projection) yang dibaca
# lewat ReadConst. BB_ORDER_FLATLOG=1: saat capture, isi flatbuf tiap draw vertex shader wajah
# dicatat (hex) supaya prepass dan pass warna bisa dibandingkan bit per bit.
FL_OLD = """            if (desc.buffer_type == Shader::BufferType::Flatbuf &&
                !stage.flattened_ud_buf.empty()) {
                copy(index, stage.flattened_ud_buf.data(), 0,
"""
FL_NEW = """            if (desc.buffer_type == Shader::BufferType::Flatbuf &&
                !stage.flattened_ud_buf.empty()) {
                // bbport-order (63): BB_ORDER_FLATLOG=1 -> flatbuf shader wajah dicatat saat capture
                static const bool bb_flat_log = [] {
                    const char* e = std::getenv("BB_ORDER_FLATLOG");
                    return e != nullptr && e[0] == '1';
                }();
                if (bb_flat_log && FrameCapture::Active() &&
                    stage.sw_stage == Shader::SwStage::Vertex) {
                    static const u64 bb_hs[] = {0x1077f760, 0x70b542d,  0xe0ec7fe0, 0x429d950d,
                                                0xb938dd39, 0xbd739cf5, 0xb2cc4b8f, 0xa369ab85,
                                                0x59c67371, 0xfd7e121b, 0x231d370b, 0x190852fd,
                                                0xb68b212f};
                    bool bb_hit = false;
                    for (const u64 h : bb_hs) {
                        bb_hit |= h == stage.pgm_hash;
                    }
                    if (bb_hit) {
                        const auto& fb = stage.flattened_ud_buf;
                        char note[256];
                        for (size_t i = 0; i < fb.size(); i += 16) {
                            int n = std::snprintf(note, sizeof(note), "\\n  flat vs %08x [%3u]",
                                                  u32(stage.pgm_hash), u32(i));
                            for (size_t j = i; j < fb.size() && j < i + 16; ++j) {
                                n += std::snprintf(note + n, sizeof(note) - n, " %08x", u32(fb[j]));
                            }
                            FrameCapture::Note(note);
                        }
                    }
                }
                copy(index, stage.flattened_ud_buf.data(), 0,
"""


def flat_log():
    path = BBPORT / 'gpu' / 'shadps4' / 'video_core' / 'renderer_vulkan' / 'vk_rasterizer.cpp'
    text = read(path)
    if 'bbport-order (63)' in text:
        print('63. flatbuf shader wajah dicatat saat capture (BB_ORDER_FLATLOG): sudah dipatch')
        return
    if text.count(FL_OLD) != 1:
        sys.exit('bagian 63: titik sisip tidak ditemukan di vk_rasterizer.cpp')
    write(path, text.replace(FL_OLD, FL_NEW, 1))
    print('63. flatbuf shader wajah dicatat saat capture (BB_ORDER_FLATLOG=1, bawaan mati)')


# --- 64. Bintik wajah: apakah depth G-buffer dibersihkan tiap frame? (17 Okt 01:35) ---
# 61-63: posisi wajah di prepass dan pass warna identik bit per bit (rumus, vertex, tulang, konstanta),
# skip lapisan lain tidak berpengaruh. Sisa penjelasan: depth tidak di-clear tiap frame (clear lewat
# HTILE yang tidak tertangkap) -> depth frame lalu tertinggal; di titik tempat wajah sedikit maju/mundur
# sejak frame lalu, tes EQUAL pass warna gagal -> bintik acak yang berganti tiap frame, hanya di bagian
# yang bergerak (wajah karakter utama).
# Saat capture: tiap pemasangan depth dicatat (clear?, nilai clear, htile, func, write, jumlah warna).
# BB_ORDER_ZCLEAR=1: pass pertama tiap frame dengan 3 target warna + depth write dipaksa clear depth.
ZC_OLD = """        const bool is_depth_clear =
            (regs.depth_render_control.depth_clear_enable && regs.depth_control.depth_enable &&
             regs.depth_control.depth_write_enable) ||
            texture_cache.IsMetaCleared(htile_address, slice);
"""
ZC_NEW = """        bool is_depth_clear =
            (regs.depth_render_control.depth_clear_enable && regs.depth_control.depth_enable &&
             regs.depth_control.depth_write_enable) ||
            texture_cache.IsMetaCleared(htile_address, slice);
        { // bbport-order (64): diagnosa / paksa clear depth G-buffer
            static const bool bb_zclear = [] {
                const char* e = std::getenv("BB_ORDER_ZCLEAR");
                return e != nullptr && e[0] == '1';
            }();
            static u32 bb_zclear_frame = ~0u;
            bool forced = false;
            const u32 frame = BbStats::frame_number.load(std::memory_order_relaxed);
            if (bb_zclear && !is_depth_clear && state.num_color_attachments == 3 &&
                regs.depth_control.depth_enable && regs.depth_control.depth_write_enable &&
                bb_zclear_frame != frame) {
                is_depth_clear = true;
                forced = true;
            }
            if (state.num_color_attachments == 3 && regs.depth_control.depth_write_enable) {
                bb_zclear_frame = frame;
            }
            if (FrameCapture::Active()) {
                char note[200];
                std::snprintf(note, sizeof(note),
                              "\\n  zatt clear %d%s val %08x htile %#llx meta %d func %u test %u "
                              "write %u ncol %u frame %u",
                              int(is_depth_clear), forced ? " (dipaksa)" : "",
                              std::bit_cast<u32>(regs.depth_clear),
                              (unsigned long long)htile_address,
                              int(texture_cache.IsMetaCleared(htile_address, slice)),
                              u32(regs.depth_control.depth_func),
                              u32(regs.depth_control.depth_enable),
                              u32(regs.depth_control.depth_write_enable),
                              u32(state.num_color_attachments), frame);
                FrameCapture::Note(note);
            }
        }
"""


def zclear():
    path = BBPORT / 'gpu' / 'shadps4' / 'video_core' / 'renderer_vulkan' / 'vk_rasterizer.cpp'
    text = read(path)
    if 'bbport-order (64)' in text:
        print('64. diagnosa/paksa clear depth G-buffer (BB_ORDER_ZCLEAR): sudah dipatch')
        return
    if text.count(ZC_OLD) != 1:
        sys.exit('bagian 64: titik sisip tidak ditemukan di vk_rasterizer.cpp')
    write(path, text.replace(ZC_OLD, ZC_NEW, 1))
    print('64. clear depth dicatat saat capture; BB_ORDER_ZCLEAR=1 memaksa clear depth G-buffer tiap frame')


# --- 65. Bintik wajah: apakah memori tulang berubah di tengah frame? (17 Okt 01:50) ---
# 64: depth G-buffer dibersihkan normal tiap frame (clear lewat HTILE tertangkap). Pass warna wajah
# memakai LEQUAL/EQUAL tanpa tulis; di titik bintik kedalaman pass warna lebih jauh dari G-buffer.
# Saat capture (eksekusi lebih lambat) bias -64 menutup semua lubang, saat main tidak -> bergantung
# waktu. Dugaan: CPU game sudah menulis matriks tulang frame berikutnya ke buffer yang sama sementara
# frame ini masih direkam, sehingga prepass dan pass warna memakai tulang dari waktu berbeda.
# BB_ORDER_BONERACE=1: untuk binding baca > 1 MiB shader wajah, checksum memori game dicatat per frame;
# kalau berubah antara draw pertama dan draw berikutnya di frame yang sama, dihitung dan dilaporkan
# tiap 2 detik di log (bbport-order (65)).
BR_OLD = """                if (valid && !desc.is_written && listed(fresh)) {"""
BR_NEW = """                { // bbport-order (65): BB_ORDER_BONERACE=1
                    static const bool bb_race = [] {
                        const char* e = std::getenv("BB_ORDER_BONERACE");
                        return e != nullptr && e[0] == '1';
                    }();
                    static const BbVbList race_list = parse("BB_ORDER_BONERACE_LIST");
                    const bool race_hit =
                        race_list.on ? listed(race_list)
                                     : (stage.pgm_hash == 0x1077f760 || stage.pgm_hash == 0x70b542d ||
                                        stage.pgm_hash == 0xe0ec7fe0 || stage.pgm_hash == 0x429d950d ||
                                        stage.pgm_hash == 0xb938dd39);
                    if (bb_race && valid && !desc.is_written && race_hit &&
                        vsharp.GetSize() > (1u << 20)) {
                        static std::mutex rm;
                        static u32 r_frame = ~0u, r_frames = 0, r_changed = 0, r_cpumod = 0;
                        static std::unordered_map<u64, u64> r_seen;
                        static bool r_flag = false;
                        static auto r_last = std::chrono::steady_clock::now();
                        const u64 sz = std::min<u64>(
                            memory->ClampRangeSize(vsharp.base_address, vsharp.GetSize()), 16ull << 20);
                        const auto* bytes = reinterpret_cast<const u64*>(vsharp.base_address);
                        u64 fnv = 1469598103934665603ull;
                        for (u64 i = 0; i < sz / 8; i++) {
                            fnv = (fnv ^ bytes[i]) * 1099511628211ull;
                        }
                        const bool cm = buffer_cache.IsRegionCpuModified(vsharp.base_address, sz);
                        std::scoped_lock lk{rm};
                        const u32 frame = BbStats::frame_number.load(std::memory_order_relaxed);
                        if (frame != r_frame) {
                            r_frame = frame;
                            r_seen.clear();
                            ++r_frames;
                            r_flag = false;
                        }
                        auto [it, inserted] = r_seen.emplace(vsharp.base_address, fnv);
                        if (!inserted && it->second != fnv) {
                            it->second = fnv;
                            if (!r_flag) {
                                ++r_changed;
                                r_flag = true;
                            }
                            r_cpumod += cm ? 1 : 0;
                        }
                        const auto now = std::chrono::steady_clock::now();
                        if (now - r_last > std::chrono::seconds(2)) {
                            r_last = now;
                            std::printf("bbport-order (65): tulang berubah di tengah frame: %u dari %u "
                                        "frame (cpumod saat berubah %u)\\n",
                                        r_changed, r_frames, r_cpumod);
                            std::fflush(stdout);
                            r_frames = r_changed = r_cpumod = 0;
                        }
                    }
                }
""" + BR_OLD


def bone_race():
    path = BBPORT / 'gpu' / 'shadps4' / 'video_core' / 'renderer_vulkan' / 'vk_rasterizer.cpp'
    text = read(path)
    if 'bbport-order (65)' in text:
        print('65. tulang berubah di tengah frame (BB_ORDER_BONERACE): sudah dipatch')
        return
    if text.count(BR_OLD) != 1:
        sys.exit('bagian 65: titik sisip tidak ditemukan (bagian 62 dulu)')
    text = text.replace(BR_OLD, BR_NEW, 1)
    for inc in ('#include <unordered_map>\n', '#include <chrono>\n', '#include <mutex>\n'):
        if inc not in text:
            text = inc + text
    write(path, text)
    print('65. tulang berubah di tengah frame dicatat (BB_ORDER_BONERACE=1, bawaan mati)')


# --- 66. Bintik wajah: barrier penuh sebelum tiap draw (uji race di GPU) (17 Okt 01:55) ---
# 65: memori tulang tidak berubah di tengah frame (0 dari ~40 frame). Data di sisi CPU identik, tapi
# di capture (eksekusi berurutan) bias -64 menutup semua lubang dan saat main tidak -> dugaan race di
# GPU: barrier yang kurang antara salinan data / pass sebelumnya dan draw wajah.
# BB_ORDER_FULLBARRIER=1: sebelum SETIAP draw, render pass ditutup dan barrier memori penuh
# (semua stage, semua akses) dipasang. Sangat lambat, hanya untuk uji.
FB_HELPER_ANCHOR = "// bbport-order (44): BB_ORDER_SKIP_FILE = daftar hash shader (hex) yang tidak dijalankan.\n"
FB_HELPER = """// bbport-order (66): BB_ORDER_FULLBARRIER=1 -> barrier memori penuh sebelum tiap draw.
static bool BbOrderFullBarrier() {
    static const bool on = [] {
        const char* e = std::getenv("BB_ORDER_FULLBARRIER");
        return e != nullptr && e[0] == '1';
    }();
    return on;
}

""" + FB_HELPER_ANCHOR
FB_OLD = """    MarkPass(pipeline, state);
    scheduler.BeginRendering(state);
"""
FB_NEW = """    MarkPass(pipeline, state);
    if (BbOrderFullBarrier()) { // bbport-order (66)
        scheduler.EndRendering();
        scheduler.Record([](vk::CommandBuffer cmdbuf) {
            const vk::MemoryBarrier2 mb{
                .srcStageMask = vk::PipelineStageFlagBits2::eAllCommands,
                .srcAccessMask =
                    vk::AccessFlagBits2::eMemoryRead | vk::AccessFlagBits2::eMemoryWrite,
                .dstStageMask = vk::PipelineStageFlagBits2::eAllCommands,
                .dstAccessMask =
                    vk::AccessFlagBits2::eMemoryRead | vk::AccessFlagBits2::eMemoryWrite,
            };
            cmdbuf.pipelineBarrier2({.memoryBarrierCount = 1, .pMemoryBarriers = &mb});
        });
    }
    scheduler.BeginRendering(state);
"""


def full_barrier():
    path = BBPORT / 'gpu' / 'shadps4' / 'video_core' / 'renderer_vulkan' / 'vk_rasterizer.cpp'
    text = read(path)
    if 'bbport-order (66)' in text:
        print('66. barrier penuh sebelum tiap draw (BB_ORDER_FULLBARRIER): sudah dipatch')
        return
    if text.count(FB_HELPER_ANCHOR) != 1 or text.count(FB_OLD) != 2:
        sys.exit('bagian 66: titik sisip tidak ditemukan di vk_rasterizer.cpp')
    text = text.replace(FB_HELPER_ANCHOR, FB_HELPER, 1).replace(FB_OLD, FB_NEW)
    write(path, text)
    print('66. barrier penuh sebelum tiap draw (BB_ORDER_FULLBARRIER=1, bawaan mati)')


# --- 67. FPS: menu tinggi, gameplay 30 -> flip rate dari game (17 Okt 02:05) ---
# Patch 60 FPS (0x8507c4) terpasang dan vblank 120 Hz, tapi saat gameplay FPS tetap 30. bbport
# menghormati sceVideoOutSetFlipRate (flip hanya tiap rate+1 vblank, driver.cpp). Dugaan: game
# memanggil SetFlipRate(1) saat gameplay (30 FPS) dan 0 di menu.
# Setiap perubahan flip rate dari game dicatat di log (bbport-order (67)).
# BB_ORDER_FLIPRATE=0|1|2: paksa nilai itu (abaikan permintaan game). Bawaan: ikuti game.
FR_OLD = """s32 PS4_SYSV_ABI sceVideoOutSetFlipRate(s32 handle, s32 rate) {
    LOG_TRACE(Lib_VideoOut, "called");
    driver->GetPort(handle)->flip_rate = rate;
    return ORBIS_OK;
}
"""
FR_NEW = """s32 PS4_SYSV_ABI sceVideoOutSetFlipRate(s32 handle, s32 rate) {
    LOG_TRACE(Lib_VideoOut, "called");
    // bbport-order (67): catat permintaan game; BB_ORDER_FLIPRATE=0|1|2 memaksa nilainya.
    static const int forced = [] {
        const char* e = std::getenv("BB_ORDER_FLIPRATE");
        return (e != nullptr && e[0] >= '0' && e[0] <= '2') ? e[0] - '0' : -1;
    }();
    static int last = -100;
    if (rate != last) {
        last = rate;
        std::printf("bbport-order (67): game SetFlipRate(%d)%s\\n", rate,
                    forced >= 0 ? " -> dipaksa BB_ORDER_FLIPRATE" : "");
        std::fflush(stdout);
    }
    driver->GetPort(handle)->flip_rate = forced >= 0 ? forced : rate;
    return ORBIS_OK;
}
"""


def flip_rate():
    path = BBPORT / 'gpu' / 'shadps4' / 'core' / 'libraries' / 'videoout' / 'video_out.cpp'
    text = read(path)
    if 'bbport-order (67)' in text:
        print('67. flip rate game dicatat / dipaksa (BB_ORDER_FLIPRATE): sudah dipatch')
        return
    if text.count(FR_OLD) != 1:
        sys.exit('bagian 67: titik sisip tidak ditemukan di video_out.cpp')
    text = text.replace(FR_OLD, FR_NEW, 1)
    for inc in ('#include <cstdio>\n', '#include <cstdlib>\n'):
        if inc not in text:
            text = inc + text
    write(path, text)
    print('67. flip rate game dicatat; BB_ORDER_FLIPRATE=0|1|2 memaksa (bawaan: ikuti game)')


# --- 68. Bintik wajah khusus NVIDIA: posisi VS dihitung eksak lewat fp64 (17 Okt 11:20) ---
# Forum: RainKikyou (shadPS4 PR #4798) melihat bintik hitam di wajah The Order dengan Ryzen 9700X +
# RTX 3080; video AMD CPU + AMD GPU bersih. Jadi bergantung GPU NVIDIA, bukan CPU. Khronos forum
# ("Depth prepass causes z-fighting", NVIDIA): driver NVIDIA menghasilkan gl_Position berbeda untuk
# rumus yang sama di dua shader berbeda walau Invariant/NoContraction (kode mesin bergantung pada
# output lain shader). Cocok dengan temuan 61-65: rumus dan input identik, kedalaman beda sedikit.
# BB_ORDER_EXACTVS=1 (daftar VS wajah) | all (semua VS) | hash,hash: di VS itu setiap FMul/FAdd/FSub
# fp32 dihitung sebagai fp64 lalu dibulatkan ke fp32 (= hasil IEEE fp32 yang tepat). Konversi di
# antara operasi mencegah driver menggabungkan mul+add (FMA), jadi prepass dan pass warna memberi
# posisi yang sama bit per bit di GPU mana pun. Bawaan mati. Cache shader harus dihapus.
EX_LIST = r"""
// bbport-order (68): BB_ORDER_EXACTVS = 1 (VS wajah) | all | hash,hash
static int BbOrderExactMode(u64 hash) {
    static const char* env = std::getenv("BB_ORDER_EXACTVS");
    if (env == nullptr || env[0] == '\0' || env[0] == '0') {
        return 0;
    }
    if (env[0] == 'a') {
        return 1;
    }
    static const std::vector<u64> list = [] {
        std::vector<u64> out;
        const char* p = (env[0] == '1' && env[1] == '\0')
                            ? "1077f760,70b542d,e0ec7fe0,429d950d,bd739cf5,231d370b,190852fd,"
                              "b2cc4b8f,b938dd39,a369ab85,59c67371,fd7e121b,b68b212f"
                            : env;
        while (*p) {
            char* end = nullptr;
            const u64 v = std::strtoull(p, &end, 16);
            if (end == p) {
                break;
            }
            out.push_back(v);
            p = (*end == ',') ? end + 1 : end;
        }
        return out;
    }();
    for (const u64 h : list) {
        if (h == hash) {
            return 1;
        }
    }
    return 0;
}
"""
EX_REC_ANCHOR = "// bbport-order (61): waterfall loop (readlane dengan lane findLSB) dijalankan per lane.\n"
EX_REC_CALL_OLD = "    Shader::Optimization::CollectShaderInfoPass(program, profile);\n"
EX_REC_CALL_NEW = EX_REC_CALL_OLD + """    // bbport-order (68): VS eksak -> tipe/kemampuan fp64 dipasang untuk emitter
    if (info.sw_stage == SwStage::Vertex && profile.support_float64 && BbOrderExactMode(info.pgm_hash)) {
        info.uses_fp64 = true;
        static std::mutex m68;
        static std::unordered_set<u64> told68;
        std::scoped_lock lock68{m68};
        if (told68.insert(info.pgm_hash).second) {
            std::printf("bbport-order (68): VS %llx posisi eksak (fp64)\\n", (unsigned long long)info.pgm_hash);
            std::fflush(stdout);
        }
    }
"""
EX_FP_ANCHOR = "Id Decorate(EmitContext& ctx, IR::Inst* inst, Id op) {\n"
EX_FP_HELPER = EX_LIST + """
static bool BbOrderExact(EmitContext& ctx) {
    return ctx.info.uses_fp64 && ctx.info.sw_stage == SwStage::Vertex &&
           BbOrderExactMode(ctx.info.pgm_hash) != 0;
}

// fp32 op lewat fp64: hasil kali dua fp32 pas di fp64, dibulatkan sekali ke fp32 = IEEE fp32 tepat.
template <typename F>
static Id BbOrderExactOp(EmitContext& ctx, Id a, Id b, F&& op) {
    const Id a64 = ctx.OpFConvert(ctx.F64[1], a);
    const Id b64 = ctx.OpFConvert(ctx.F64[1], b);
    const Id r64 = op(a64, b64);
    ctx.Decorate(r64, spv::Decoration::NoContraction);
    return ctx.OpFConvert(ctx.F32[1], r64);
}

""" + EX_FP_ANCHOR
EX_ADD_OLD = """Id EmitFPAdd32(EmitContext& ctx, IR::Inst* inst, Id a, Id b) {
    return Decorate(ctx, inst, ctx.OpFAdd(ctx.F32[1], a, b));
"""
EX_ADD_NEW = """Id EmitFPAdd32(EmitContext& ctx, IR::Inst* inst, Id a, Id b) {
    if (BbOrderExact(ctx)) { // bbport-order (68)
        return BbOrderExactOp(ctx, a, b, [&](Id x, Id y) { return ctx.OpFAdd(ctx.F64[1], x, y); });
    }
    return Decorate(ctx, inst, ctx.OpFAdd(ctx.F32[1], a, b));
"""
EX_SUB_OLD = """Id EmitFPSub32(EmitContext& ctx, IR::Inst* inst, Id a, Id b) {
    return Decorate(ctx, inst, ctx.OpFSub(ctx.F32[1], a, b));
"""
EX_SUB_NEW = """Id EmitFPSub32(EmitContext& ctx, IR::Inst* inst, Id a, Id b) {
    if (BbOrderExact(ctx)) { // bbport-order (68)
        return BbOrderExactOp(ctx, a, b, [&](Id x, Id y) { return ctx.OpFSub(ctx.F64[1], x, y); });
    }
    return Decorate(ctx, inst, ctx.OpFSub(ctx.F32[1], a, b));
"""
EX_MUL_OLD = """Id EmitFPMul32(EmitContext& ctx, IR::Inst* inst, Id a, Id b) {
    return Decorate(ctx, inst, ctx.OpFMul(ctx.F32[1], a, b));
"""
EX_MUL_NEW = """Id EmitFPMul32(EmitContext& ctx, IR::Inst* inst, Id a, Id b) {
    if (BbOrderExact(ctx)) { // bbport-order (68)
        return BbOrderExactOp(ctx, a, b, [&](Id x, Id y) { return ctx.OpFMul(ctx.F64[1], x, y); });
    }
    return Decorate(ctx, inst, ctx.OpFMul(ctx.F32[1], a, b));
"""
EX_INC = '#include <cstdlib>\n#include <vector>\n'


def exact_vs():
    sr = BBPORT / 'gpu' / 'shadps4' / 'shader_recompiler'
    rec = sr / 'recompiler.cpp'
    fp = sr / 'backend' / 'spirv' / 'emit_spirv_floating_point.cpp'
    r, f = read(rec), read(fp)
    if 'bbport-order (68)' in r and 'bbport-order (68)' in f:
        print('68. posisi VS eksak lewat fp64 (BB_ORDER_EXACTVS): sudah dipatch')
        return
    if r.count(EX_REC_ANCHOR) != 1 or r.count(EX_REC_CALL_OLD) != 1:
        sys.exit('bagian 68: titik sisip tidak ditemukan di recompiler.cpp (bagian 61 dulu)')
    for old in (EX_FP_ANCHOR, EX_ADD_OLD, EX_SUB_OLD, EX_MUL_OLD):
        if f.count(old) != 1:
            sys.exit('bagian 68: titik sisip tidak ditemukan di emit_spirv_floating_point.cpp')
    r = r.replace(EX_REC_ANCHOR, EX_LIST + '\n' + EX_REC_ANCHOR, 1).replace(EX_REC_CALL_OLD, EX_REC_CALL_NEW, 1)
    f = f.replace(EX_FP_ANCHOR, EX_FP_HELPER, 1).replace(EX_ADD_OLD, EX_ADD_NEW, 1)
    f = f.replace(EX_SUB_OLD, EX_SUB_NEW, 1).replace(EX_MUL_OLD, EX_MUL_NEW, 1)
    f = EX_INC + f
    write(rec, r)
    write(fp, f)
    print('68. posisi VS eksak lewat fp64 (BB_ORDER_EXACTVS=1|all|hash, bawaan mati)')


# --- 69. Diagnosa: dump image depth (D32) lewat BB_ORDER_DIAG_CS (17 Okt 12:40) ---
# 68 (posisi eksak) dan skip semua pass yang membaca depth tidak menghapus bintik. Untuk memisahkan
# "depth G-buffer yang tersimpan salah" dari "kedalaman pass warna salah", depth G-buffer diambil
# langsung dari GPU: compute 8ea0ef5b (tepat sebelum pass warna) mengikat depth 0x104c7c0000.
# Bagian 52 sebelumnya melewati image depth; sekarang D32 (4 byte/piksel) ikut ditulis (aspek depth).
DD_OLD = """    if (image.info.props.is_depth || image.info.props.is_block || bytes_per_pixel == 0 ||
        image.info.num_samples > 1) {
        return;
    }
"""
DD_NEW = """    // bbport-order (69): depth 4 byte/piksel (D32) ikut ditulis, aspek depth.
    const bool bb_depth = image.info.props.is_depth;
    if ((bb_depth && bytes_per_pixel != 4) || image.info.props.is_block || bytes_per_pixel == 0 ||
        image.info.num_samples > 1) {
        return;
    }
"""
DD_ASPECT_OLD = "        .imageSubresource = {vk::ImageAspectFlagBits::eColor, 0, 0, 1},\n        .imageOffset = {0, 0, 0},\n        .imageExtent = {image.info.size.width, image.info.size.height, 1},\n    };\n    runtime.DownloadImage(&image, download.buffer, std::span{&copy, 1});\n"
DD_ASPECT_NEW = "        .imageSubresource = {bb_depth ? vk::ImageAspectFlagBits::eDepth : vk::ImageAspectFlagBits::eColor, 0, 0, 1},\n        .imageOffset = {0, 0, 0},\n        .imageExtent = {image.info.size.width, image.info.size.height, 1},\n    };\n    runtime.DownloadImage(&image, download.buffer, std::span{&copy, 1});\n"


def diag_depth():
    path = BBPORT / 'gpu' / 'shadps4' / 'video_core' / 'texture_cache' / 'texture_cache.cpp'
    text = read(path)
    if 'bbport-order (69)' in text:
        print('69. dump depth D32 lewat BB_ORDER_DIAG_CS: sudah dipatch')
        return
    if text.count(DD_OLD) != 1 or text.count(DD_ASPECT_OLD) != 1:
        sys.exit('bagian 69: titik sisip tidak ditemukan di texture_cache.cpp (bagian 52 dulu)')
    write(path, text.replace(DD_OLD, DD_NEW, 1).replace(DD_ASPECT_OLD, DD_ASPECT_NEW, 1))
    print('69. dump depth D32 lewat BB_ORDER_DIAG_CS (saat capture)')


# --- 70. Bintik = gumpalan bulat di sekitar vertex -> data vertex berubah di tengah frame? (17 Okt 12:55) ---
# Dump 69 (depth G-buffer + scene color, frame yang sama): depth tersimpan di titik bintik mulus
# dengan tetangganya (G-buffer benar). Bintiknya gumpalan bulat 5-15 piksel = kipas segitiga di sekitar
# satu vertex: vertex tertentu di pass warna berada di tempat lain daripada di prepass. Rumus dan tulang
# sama -> yang tersisa: isi vertex buffer wajah (animasi wajah ditulis CPU tiap frame) berubah di antara
# prepass dan pass warna. Bagian 65 hanya memeriksa buffer > 1 MiB (tulang); BB_ORDER_BONERACE_MIN=0
# ikut memeriksa vertex buffer wajah (36-46 KB) dan mencatat alamat yang berubah.
BR2_OLD = "                        vsharp.GetSize() > (1u << 20)) {"
BR2_NEW = """                        vsharp.GetSize() > [] { // bbport-order (70): BB_ORDER_BONERACE_MIN (byte)
                            const char* e = std::getenv("BB_ORDER_BONERACE_MIN");
                            return e != nullptr ? u32(std::strtoul(e, nullptr, 10)) : (1u << 20);
                        }()) {"""
BR2_LOG_OLD = "                            r_cpumod += cm ? 1 : 0;\n"
BR2_LOG_NEW = """                            r_cpumod += cm ? 1 : 0;
                            static u32 r_told = 0; // bbport-order (70): alamat yang berubah
                            if (r_told < 40) {
                                ++r_told;
                                std::printf("bbport-order (70): berubah di tengah frame: vs %08x slot %u "
                                            "%#llx ukuran %u stride %u cpumod %d\\n",
                                            u32(stage.pgm_hash), binding.buffer,
                                            (unsigned long long)vsharp.base_address,
                                            u32(vsharp.GetSize()), u32(vsharp.GetStride()), int(cm));
                                std::fflush(stdout);
                            }
"""


def vertex_race():
    path = BBPORT / 'gpu' / 'shadps4' / 'video_core' / 'renderer_vulkan' / 'vk_rasterizer.cpp'
    text = read(path)
    if 'bbport-order (70)' in text:
        print('70. vertex buffer wajah berubah di tengah frame (BB_ORDER_BONERACE_MIN): sudah dipatch')
        return
    if text.count(BR2_OLD) != 1 or text.count(BR2_LOG_OLD) != 1:
        sys.exit('bagian 70: titik sisip tidak ditemukan (bagian 65 dulu)')
    write(path, text.replace(BR2_OLD, BR2_NEW, 1).replace(BR2_LOG_OLD, BR2_LOG_NEW, 1))
    print('70. BB_ORDER_BONERACE_MIN=0: vertex buffer wajah ikut diperiksa (alamat yang berubah dicatat)')


# --- 71. Bintik wajah: depth bias HANYA untuk draw tanpa tulis depth (17 Okt) ---
# RenderDoc pixel history (frame 3267, MSAA 2): segitiga yang sama (prim 734) mendapat depth
# 0.87041384 di draw G-buffer (eid 864, LESS + tulis) dan 0.870413899 di pass warna (eid 6957,
# LEQUAL tanpa tulis): beda 1 ULP -> tes depth gagal -> lubang. State viewport, rasterizer,
# multisample identik (rdc_state.txt); bedanya hanya vertex shader-nya (dua shader berbeda yang
# menghitung posisi yang sama; di NVIDIA hasilnya bisa beda 1 ULP walau Position Invariant).
# Bagian 59 memberi bias ke SEMUA draw 2+ target, termasuk G-buffer yang menulis depth, jadi
# keduanya ikut bergeser dan sebagian lubang tetap ada; draw EQUAL ikut rusak oleh bias.
# Perbaikan: bias -konstanta/-slope hanya untuk draw dengan tes depth, TANPA tulis depth, dengan
# render target warna; EQUAL tanpa tulis di draw itu diganti LEQUAL; bias dari game ditambahkan.
# BB_ORDER_FACEFIX: bawaan 1 (versi ini), 0 mati, old/2 = perilaku lama bagian 59.
FX_HELPER_ANCHOR = "void Rasterizer::UpdateDepthStencilState() const {\n"
FX_HELPER = r"""// bbport-order (71): mode perbaikan bintik wajah. 0 mati, 1 draw tanpa tulis depth, 2 lama (59)
static int BbOrderFaceFixMode() {
    static const int mode = [] {
        const char* e = std::getenv("BB_ORDER_FACEFIX");
        int m = 1;
        if (e != nullptr && e[0] == '0') {
            m = 0;
        } else if (e != nullptr && (e[0] == '2' || e[0] == 'o')) {
            m = 2;
        }
        std::printf("bbport-order (71): face fix mode %d\n", m);
        std::fflush(stdout);
        return m;
    }();
    return mode;
}

"""
FX_CMP_OLD = "        dynamic_state.SetDepthCompareOp(bb_cmp);\n"
FX_CMP_NEW = """        if (BbOrderFaceFixMode() == 1 && bb_cmp == vk::CompareOp::eEqual && regs.color_buffers[0] &&
            !(regs.depth_control.depth_write_enable &&
              !regs.depth_render_control.depth_clear_enable)) { // bbport-order (71)
            bb_cmp = vk::CompareOp::eLessOrEqual;
        }
""" + FX_CMP_OLD
FX_COND_OLD = """        static const bool facefix = [] {
            const char* e = std::getenv("BB_ORDER_FACEFIX");
            return e == nullptr || e[0] != '0';
        }();
        if (facefix && (BbOrderDsFlags() & (64 | 128)) == 0 && !depth_bias_enabled &&
            depth_test_enabled && regs.color_buffers[0] && regs.color_buffers[1]) {
"""
FX_COND_NEW = """        const int bb_ff = BbOrderFaceFixMode(); // bbport-order (71)
        const bool bb_ff_writes = regs.depth_control.depth_write_enable &&
                                  !regs.depth_render_control.depth_clear_enable;
        const bool bb_ff_hit =
            bb_ff == 2 ? (!depth_bias_enabled && regs.color_buffers[0] && regs.color_buffers[1])
                       : (bb_ff == 1 && !bb_ff_writes && regs.color_buffers[0]);
        if (bb_ff_hit && (BbOrderDsFlags() & (64 | 128)) == 0 && depth_test_enabled) {
"""
FX_BIAS_OLD = "            dynamic_state.SetDepthBias(-fb_const.load(), 0.f, -fb_slope.load());\n"
FX_BIAS_NEW = """            float bb_gc = 0.f, bb_gs = 0.f; // bbport-order (71): bias game ditambahkan
            if (depth_bias_enabled) {
                const bool bb_front = regs.polygon_control.enable_polygon_offset_front;
                bb_gc = bb_front ? regs.poly_offset.front_offset : regs.poly_offset.back_offset;
                bb_gs = (bb_front ? regs.poly_offset.front_scale : regs.poly_offset.back_scale) / 16.f;
            }
            dynamic_state.SetDepthBias(bb_gc - fb_const.load(), 0.f, bb_gs - fb_slope.load());
"""


def face_fix_nowrite():
    path = BBPORT / 'gpu' / 'shadps4' / 'video_core' / 'renderer_vulkan' / 'vk_rasterizer.cpp'
    text = read(path)
    if 'bbport-order (71)' in text:
        print('71. face fix hanya draw tanpa tulis depth (BB_ORDER_FACEFIX): sudah dipatch')
        return
    for name, old in (('helper', FX_HELPER_ANCHOR), ('compare', FX_CMP_OLD), ('kondisi', FX_COND_OLD),
                      ('bias', FX_BIAS_OLD)):
        if text.count(old) != 1:
            sys.exit('bagian 71: titik sisip %s tidak ditemukan (bagian 59/60 dulu)' % name)
    text = text.replace(FX_HELPER_ANCHOR, FX_HELPER + FX_HELPER_ANCHOR, 1)
    text = text.replace(FX_CMP_OLD, FX_CMP_NEW, 1)
    text = text.replace(FX_COND_OLD, FX_COND_NEW, 1)
    text = text.replace(FX_BIAS_OLD, FX_BIAS_NEW, 1)
    write(path, text)
    print('71. PERBAIKAN bintik wajah: bias hanya draw tanpa tulis depth, EQUAL -> LEQUAL (BB_ORDER_FACEFIX)')


# --- 72. Bintik wajah: besar bias bawaan 256 / slope 4 (17 Okt 13:45) ---
# Uji di game (bagian 71, file BB_ORDER_FACEBIAS_FILE): "256 4" = bintik hilang total; 64/1 masih
# menyisakan bintik. Bawaan sekarang 256/4. BB_ORDER_FACEBIAS="konstanta slope" mengganti tanpa file.
FB2_OLD = "            static std::atomic<float> fb_const{64.f}, fb_slope{1.f};\n"
FB2_NEW = """            static float fb_def_c = 256.f, fb_def_s = 4.f; // bbport-order (72)
            static const bool fb_def_read = [] {
                if (const char* e = std::getenv("BB_ORDER_FACEBIAS")) {
                    float c = 256.f, s = 4.f;
                    if (std::sscanf(e, "%f %f", &c, &s) >= 1) {
                        fb_def_c = c;
                        fb_def_s = s;
                    }
                }
                std::printf("bbport-order (72): face bias bawaan %.1f slope %.2f\\n", fb_def_c, fb_def_s);
                std::fflush(stdout);
                return true;
            }();
            (void)fb_def_read;
            static std::atomic<float> fb_const{fb_def_c}, fb_slope{fb_def_s};
"""
FB2_FALLBACK_OLD = "                    float c = 64.f, s = 1.f;\n"
FB2_FALLBACK_NEW = "                    float c = fb_def_c, s = fb_def_s; // bbport-order (72)\n"
FB2_FALLBACK2_OLD = "                            c = 64.f;\n"
FB2_FALLBACK2_NEW = "                            c = fb_def_c;\n"


def face_bias_default():
    path = BBPORT / 'gpu' / 'shadps4' / 'video_core' / 'renderer_vulkan' / 'vk_rasterizer.cpp'
    text = read(path)
    if 'bbport-order (72)' in text:
        print('72. face bias bawaan 256/4 (BB_ORDER_FACEBIAS): sudah dipatch')
        return
    for name, old in (('atomic', FB2_OLD), ('fallback', FB2_FALLBACK_OLD), ('fallback2', FB2_FALLBACK2_OLD)):
        if text.count(old) != 1:
            sys.exit('bagian 72: titik sisip %s tidak ditemukan (bagian 60 dulu)' % name)
    text = text.replace(FB2_OLD, FB2_NEW, 1).replace(FB2_FALLBACK_OLD, FB2_FALLBACK_NEW, 1)
    text = text.replace(FB2_FALLBACK2_OLD, FB2_FALLBACK2_NEW, 1)
    write(path, text)
    print('72. face bias bawaan 256 / slope 4 (BB_ORDER_FACEBIAS="c s" mengganti)')


# --- 73. Threaded recording: RecordData lebih besar dari satu chunk (17 Okt 13:50) ---
# BB_VK_RECORD_THREAD=1 di The Order: "ReserveRecordData: Assertion Failed" (vk_scheduler.h): satu
# perintah membawa data > 127 KiB (ribuan region copy/upload atau barrier untuk image ribuan layer).
# Perbaikan: data yang tidak muat disalin ke blok heap milik chunk yang sama (dibebaskan sesudah
# chunk dijalankan); reservasi raksasa memulai chunk baru, potongan berikutnya tidak memensiunkan
# chunk di tengah perintah. Tanpa thread recording (bawaan The Order) tidak ada perubahan.
RD_CHUNK_OLD = """    void Execute(vk::CommandBuffer cmdbuf) {
        for (CommandBase* command = first; command;) {
            CommandBase* const next = command->next;
            command->Execute(cmdbuf);
            command->~CommandBase();
            command = next;
        }
        first = last = nullptr;
        used = 0;
    }
"""
RD_CHUNK_NEW = """    void Execute(vk::CommandBuffer cmdbuf) {
        for (CommandBase* command = first; command;) {
            CommandBase* const next = command->next;
            command->Execute(cmdbuf);
            command->~CommandBase();
            command = next;
        }
        first = last = nullptr;
        used = 0;
        big.clear(); // bbport-order (73)
    }

    /// bbport-order (73): data of a command too large for the chunk, freed with the chunk.
    void* AllocateBig(size_t bytes) {
        big.push_back(std::make_unique<std::byte[]>(bytes + 16));
        return big.back().get();
    }
    std::vector<std::unique_ptr<std::byte[]>> big;
"""
RD_RESERVE_OLD = """    void ReserveRecordData(size_t bytes) {
        if (!IsRecordingDeferred()) {
            return;
        }
        ASSERT(bytes + 1024 <= RecordChunk::Capacity);
        if (RecordChunk::Capacity - CurrentChunk().Size() < bytes + 1024) {
            RetireChunk();
        }
    }
"""
RD_RESERVE_NEW = """    void ReserveRecordData(size_t bytes) {
        if (!IsRecordingDeferred()) {
            return;
        }
        if (bytes + 1024 > RecordChunk::Capacity) { // bbport-order (73): larger than a chunk
            if (CurrentChunk().Size() > 0) {
                RetireChunk();
            }
            bb_record_oversized = true;
            return;
        }
        if (bb_record_oversized) {
            return;
        }
        if (RecordChunk::Capacity - CurrentChunk().Size() < bytes + 1024) {
            RetireChunk();
        }
    }
"""
RD_DATA_OLD = """        // Room for the data and the command that follows it, so both stay in one chunk.
        const size_t bytes = data.size_bytes();
        ReserveRecordData(bytes + alignof(T));
        auto* dst = static_cast<T*>(CurrentChunk().Allocate(bytes, alignof(T)));
        std::memcpy(dst, data.data(), bytes);
        return {dst, data.size()};
"""
RD_DATA_NEW = """        // Room for the data and the command that follows it, so both stay in one chunk.
        const size_t bytes = data.size_bytes();
        ReserveRecordData(bytes + alignof(T));
        T* dst = nullptr;
        // bbport-order (73): what does not fit (with 1 KiB left for the command) goes to a block
        // owned by the same chunk.
        if (RecordChunk::Capacity - CurrentChunk().Size() >= bytes + alignof(T) + 1024) {
            dst = static_cast<T*>(CurrentChunk().Allocate(bytes, alignof(T)));
        }
        if (dst == nullptr) {
            dst = static_cast<T*>(CurrentChunk().AllocateBig(bytes));
        }
        std::memcpy(dst, data.data(), bytes);
        return {dst, data.size()};
"""
RD_RECORD_OLD = """        if (!CurrentChunk().Push(std::forward<Func>(func))) {
            RetireChunk();
            const bool pushed = CurrentChunk().Push(std::forward<Func>(func));
            ASSERT(pushed);
        }
    }
"""
RD_RECORD_NEW = """        if (!CurrentChunk().Push(std::forward<Func>(func))) {
            RetireChunk();
            const bool pushed = CurrentChunk().Push(std::forward<Func>(func));
            ASSERT(pushed);
        }
        bb_record_oversized = false; // bbport-order (73)
    }
"""
RD_MEMBER_OLD = "    bool async_submit = false; ///< BB_ASYNC_SUBMIT (default on)\n"
RD_MEMBER_NEW = RD_MEMBER_OLD + "    bool bb_record_oversized = false; ///< bbport-order (73): ReserveRecordData > chunk\n"


def record_data_big():
    path = BBPORT / 'gpu' / 'shadps4' / 'video_core' / 'renderer_vulkan' / 'vk_scheduler.h'
    text = read(path)
    if 'bbport-order (73)' in text:
        print('73. RecordData lebih besar dari chunk (thread recording): sudah dipatch')
        return
    pairs = ((RD_CHUNK_OLD, RD_CHUNK_NEW), (RD_RESERVE_OLD, RD_RESERVE_NEW), (RD_DATA_OLD, RD_DATA_NEW),
             (RD_RECORD_OLD, RD_RECORD_NEW), (RD_MEMBER_OLD, RD_MEMBER_NEW))
    for i, (old, _) in enumerate(pairs):
        if text.count(old) != 1:
            sys.exit('bagian 73: titik sisip %d tidak ditemukan di vk_scheduler.h' % i)
    for old, new in pairs:
        text = text.replace(old, new, 1)
    write(path, text)
    print('73. thread recording: data perintah > 127 KiB ke blok heap chunk (assert ReserveRecordData)')


# --- 74. Worker job system game (Task Kernel) tidur sebentar saat menganggur (17 Okt 14:20) ---
# perf (i3-12100F, 4 core / 8 thread): 4 thread 'Task Kernel' masing-masing ~94% CPU. Loop worker
# (eboot 0x20ad20) mencoba ambil job; callback idle 0x8a7380 baru memanggil scePthreadYield sesudah
# 1801 percobaan gagal (tiap percobaan mfence + lock cmpxchg), tanpa PAUSE. sched_yield langsung
# kembali kalau CPU lain kosong -> spin murni yang memakan core fisik yang sama dengan thread
# hyperthread pasangannya (GpuComm / bb:Draw bbport).
# BB_ORDER_YIELD_US=N: scePthreadYield dari thread bernama "Task Kernel*" tidur N mikrodetik
# (bawaan 0 = sched_yield seperti asli). Ambang 1801 bisa dikecilkan dengan order_patches.py --spin.
TY_OLD = "static ABI int32_t thread_yield(void) { sched_yield(); return 0; }\n"
TY_NEW = r"""static ABI int32_t thread_yield(void) { /* bbport-order (74) */
    static int sleep_us = -1;
    if (sleep_us < 0) {
        const char *e = getenv("BB_ORDER_YIELD_US");
        sleep_us = e ? atoi(e) : 0;
        if (sleep_us > 0) {
            fprintf(stderr, "bbport-order (74): Task Kernel yield -> tidur %d us\n", sleep_us);
        }
    }
    static __thread int task_kernel = -1;
    if (task_kernel < 0) {
        char name[32] = {0};
        pthread_getname_np(pthread_self(), name, sizeof name);
        task_kernel = strncmp(name, "Task Kernel", 11) == 0;
    }
    if (sleep_us > 0 && task_kernel) {
        struct timespec ts = {0, (long)sleep_us * 1000L};
        nanosleep(&ts, NULL);
    } else {
        sched_yield();
    }
    return 0;
}
"""


def task_kernel_yield():
    path = BBPORT / 'src' / 'runtime_thread.c'
    text = read(path)
    if 'bbport-order (74)' in text:
        print('74. Task Kernel yield -> tidur (BB_ORDER_YIELD_US): sudah dipatch')
        return
    if text.count(TY_OLD) != 1:
        sys.exit('bagian 74: thread_yield tidak ditemukan di runtime_thread.c')
    text = text.replace(TY_OLD, TY_NEW, 1)
    if '#include <time.h>' not in text:
        text = text.replace('#include <sched.h>\n', '#include <sched.h>\n#include <time.h>\n', 1)
    write(path, text)
    print('74. scePthreadYield dari Task Kernel bisa tidur (BB_ORDER_YIELD_US=mikrodetik, bawaan 0)')


# --- 75. DLSS / FSR 3.1 menggantikan TAA game (compute 92311aca) (17 Okt 17:10) ---
# Dump SPIR-V 92311aca (BB_DUMP_SHADERS): TAA game = img0 exposure R32F 1x1 (log2), img1 motion
# vector A2B10G10R10 (x,y unorm; 2 bit alpha = tanda: bit0 membalik x, bit1 = y positif),
# img2 warna adegan RGBA16F MSAA (resolve sendiri, bobot 1/(1+luma*exposure)), img3 history,
# img4 output RGBA16F. Posisi history = piksel + 0.5 + data[63] * (-x*s0, y*s1) (data[63] di
# flatbuf = skala motion vector dalam piksel, data[64]/[65] = lebar/tinggi). Tanpa jitter.
# BB_ORDER_TAA_HOOK=dlss|fsr3: dispatch game dilewati; bbport me-resolve warna MSAA (bobot tonemap),
# depth (sampel terdekat) dan motion vector ke piksel, menjalankan DLSS (DLAA) atau FSR 3.1
# (Native AA), lalu menulis hasilnya ke output TAA game (alpha 1 seperti aslinya). History, motion
# blur, post dan UI tetap jalur game. DLSS tidak tersedia -> FSR 3.1. BB_ORDER_TAA_MV=faktor (uji
# arah motion vector, bawaan 1). Depth adegan = depth pass G-buffer (3 target, color0 A2B10G10R10).
OT_PREP_SHADER = r"""// SPDX-License-Identifier: GPL-2.0-or-later
// bbport-order (75): inputs for DLSS / FSR 3.1 in place of The Order: 1886's TAA (cs 92311aca):
// the MSAA scene color resolved (tonemap-weighted), the nearest depth sample, the game's motion
// vectors decoded to render pixels (current to previous).
#version 450
#extension GL_EXT_samplerless_texture_functions : require
layout(local_size_x = 8, local_size_y = 8) in;
#ifdef SCENE_MS
layout(binding = 0) uniform texture2DMS scene_tex;
#else
layout(binding = 0) uniform texture2D scene_tex;
#endif
#ifdef DEPTH_MS
layout(binding = 1) uniform texture2DMS depth_tex;
#else
layout(binding = 1) uniform texture2D depth_tex;
#endif
layout(binding = 2) uniform texture2D velocity_tex;
layout(binding = 3, rgba16f) uniform writeonly image2D color_out;
layout(binding = 4, r32f) uniform writeonly image2D depth_out;
layout(binding = 5, rg16f) uniform writeonly image2D motion_out;

layout(push_constant) uniform Params {
    float velocity_scale;
    uint width;
    uint height;
    uint pad;
};

void main() {
    const ivec2 p = ivec2(gl_GlobalInvocationID.xy);
    if (p.x >= int(width) || p.y >= int(height)) {
        return;
    }
#ifdef SCENE_MS
    vec3 sum = vec3(0.0);
    float weights = 0.0;
    const int samples = textureSamples(scene_tex);
    for (int s = 0; s < samples; ++s) {
        const vec3 c = max(texelFetch(scene_tex, p, s).rgb, vec3(0.0));
        const float w = 1.0 / (1.0 + dot(c, vec3(0.299, 0.587, 0.114)));
        sum += c * w;
        weights += w;
    }
    const vec3 color = sum / max(weights, 1e-6);
#else
    const vec3 color = max(texelFetch(scene_tex, p, 0).rgb, vec3(0.0));
#endif
#ifdef DEPTH_MS
    float depth = 1.0;
    const int depth_samples = textureSamples(depth_tex);
    for (int s = 0; s < depth_samples; ++s) {
        depth = min(depth, texelFetch(depth_tex, p, s).r);
    }
#else
    const float depth = texelFetch(depth_tex, p, 0).r;
#endif
    const vec4 v = texelFetch(velocity_tex, p, 0);
    const uint signs = uint(v.w * 3.0 + 0.5);
    const float mx = -v.x * (((signs & 1u) != 0u) ? -1.0 : 1.0);
    const float my = (((signs & 2u) != 0u) ? 1.0 : -1.0) * v.y;
    imageStore(color_out, p, vec4(color, 1.0));
    imageStore(depth_out, p, vec4(depth));
    imageStore(motion_out, p, vec4(velocity_scale * mx, velocity_scale * my, 0.0, 0.0));
}
"""
OT_STORE_SHADER = r"""// SPDX-License-Identifier: GPL-2.0-or-later
// bbport-order (75): the DLSS / FSR 3.1 result into the output of The Order's TAA (alpha 1).
#version 450
layout(local_size_x = 8, local_size_y = 8) in;
layout(binding = 0, rgba16f) uniform readonly image2D upscaled;
layout(binding = 1, rgba16f) uniform writeonly image2D target;

void main() {
    const ivec2 p = ivec2(gl_GlobalInvocationID.xy);
    if (any(greaterThanEqual(p, imageSize(target)))) {
        return;
    }
    imageStore(target, p, vec4(max(imageLoad(upscaled, p).rgb, vec3(0.0)), 1.0));
}
"""
OT_CMAKE_OLD = "add_host_shader(camera_motion.comp camera_motion_debug_comp DEBUG_OVERLAY=1)\n"
OT_CMAKE_NEW = OT_CMAKE_OLD + """# bbport-order (75): The Order: 1886 TAA -> DLSS / FSR 3.1
add_host_shader(order_taa_prep.comp order_taa_prep_comp)
add_host_shader(order_taa_prep.comp order_taa_prep_sms_comp SCENE_MS=1)
add_host_shader(order_taa_prep.comp order_taa_prep_dms_comp DEPTH_MS=1)
add_host_shader(order_taa_prep.comp order_taa_prep_sdms_comp SCENE_MS=1 DEPTH_MS=1)
add_host_shader(order_taa_store.comp order_taa_store_comp)
"""
OT_H_OLD = "    vk::UniqueImageView ui_storage_view;\n};\n"
OT_H_NEW = """    vk::UniqueImageView ui_storage_view;

public:
    /// bbport-order (75): The Order: 1886's TAA (compute 92311aca) replaced by DLSS / FSR 3.1
    /// (BB_ORDER_TAA_HOOK=dlss|fsr3). True when recorded: the game's dispatch is then skipped.
    bool OrderTaa(VideoCore::ImageId scene, VideoCore::ImageId velocity, VideoCore::ImageId depth,
                  VideoCore::ImageId output, float velocity_scale);

private:
    int order_mode = -1; ///< 0 off, 1 FSR 3.1, 2 DLSS
    bool order_failed = false;
    bool order_warned = false;
    bool order_reset = true;
    float order_mv = 1.0f;
    float order_last_scale = -1.0f;
    u32 order_w = 0, order_h = 0;
    VideoCore::UniqueImage order_color_image, order_depth_image;
    vk::UniqueImageView order_color_view, order_depth_view;
    vk::UniqueDescriptorSetLayout order_prep_desc_layout, order_store_desc_layout;
    vk::UniquePipelineLayout order_prep_pipeline_layout, order_store_pipeline_layout;
    std::array<vk::UniquePipeline, 4> order_prep_pipelines;
    vk::UniquePipeline order_store_pipeline;
    std::chrono::steady_clock::time_point order_last_frame{};
};
"""
OT_CPP = r"""
// bbport-order (75): The Order: 1886's TAA (compute 92311aca) replaced by DLSS / FSR 3.1.
#include "video_core/host_shaders/order_taa_prep_comp.h"
#include "video_core/host_shaders/order_taa_prep_sms_comp.h"
#include "video_core/host_shaders/order_taa_prep_dms_comp.h"
#include "video_core/host_shaders/order_taa_prep_sdms_comp.h"
#include "video_core/host_shaders/order_taa_store_comp.h"

namespace Vulkan {

bool TemporalUpscaler::OrderTaa(VideoCore::ImageId scene_id, VideoCore::ImageId velocity_id,
                                VideoCore::ImageId depth_id, VideoCore::ImageId output_id,
                                float velocity_scale) {
    if (order_mode < 0) {
        order_mode = 0;
        const char* hook = std::getenv("BB_ORDER_TAA_HOOK");
        if (hook && std::strcmp(hook, "dlss") == 0) {
            order_mode = 2;
        } else if (hook && std::strcmp(hook, "fsr3") == 0) {
            order_mode = 1;
        }
        if (order_mode == 2) {
            const Dlss* dlss = Dlss::Get();
            if (!dlss || !dlss->Available()) {
                std::printf("bbport-order (75): DLSS tidak tersedia (%s): FSR 3.1 dipakai\n",
                            dlss ? dlss->Problem().c_str() : "bridge atau library NVIDIA tidak ada");
                order_mode = 1;
            }
        }
        if (const char* mv = std::getenv("BB_ORDER_TAA_MV")) {
            order_mv = std::strtof(mv, nullptr);
        }
        if (order_mode != 0) {
            std::printf("bbport-order (75): TAA game diganti %s (faktor motion vector %.2f)\n",
                        order_mode == 2 ? "DLSS (DLAA)" : "FSR 3.1 (Native AA)", order_mv);
        }
        std::fflush(stdout);
    }
    if (order_mode == 0 || order_failed) {
        return false;
    }
    if (!scene_id || !velocity_id || !depth_id || !output_id) {
        return false;
    }
    auto& scene = texture_cache.GetImage(scene_id);
    auto& velocity = texture_cache.GetImage(velocity_id);
    auto& depth = texture_cache.GetImage(depth_id);
    auto& output = texture_cache.GetImage(output_id);
    const u32 w = output.info.size.width, h = output.info.size.height;
    const auto fail = [&](const char* why) {
        if (!order_warned) {
            order_warned = true;
            std::printf("bbport-order (75): TAA game tetap dipakai: %s (output %ux%u)\n", why, w, h);
            std::fflush(stdout);
        }
        return false;
    };
    const bool depth_stencil = depth.info.pixel_format == vk::Format::eD32SfloatS8Uint;
    if (output.info.pixel_format != vk::Format::eR16G16B16A16Sfloat ||
        !(output.usage_flags & vk::ImageUsageFlagBits::eStorage)) {
        return fail("output bukan RGBA16F storage");
    }
    if (scene.info.pixel_format != vk::Format::eR16G16B16A16Sfloat) {
        return fail("warna adegan bukan RGBA16F");
    }
    if (velocity.info.pixel_format != vk::Format::eA2B10G10R10UnormPack32) {
        return fail("motion vector bukan A2B10G10R10");
    }
    if (depth.info.pixel_format != vk::Format::eD32Sfloat && !depth_stencil) {
        return fail("format depth");
    }
    if (scene.info.size.width != w || scene.info.size.height != h ||
        velocity.info.size.width != w || velocity.info.size.height != h ||
        depth.info.size.width != w || depth.info.size.height != h) {
        return fail("ukuran input tidak sama");
    }
    if (!scene.backing || !velocity.backing || !depth.backing || velocity.backing->num_samples != 1) {
        return fail("sampel motion vector");
    }
    if (velocity_scale != order_last_scale) {
        order_last_scale = velocity_scale;
        std::printf("bbport-order (75): skala motion vector game %.4f\n", velocity_scale);
        std::fflush(stdout);
    }
    if (order_mode == 2 && dlss_failed) {
        order_mode = 1;
    }
    if (!EnsureResources(w, h, w, h, true)) {
        order_failed = true;
        return fail("resource upscaler");
    }
    const auto device = instance.GetDevice();
    if (order_w != w || order_h != h || !order_color_image) {
        scheduler.Finish();
        const auto allocator = instance.GetAllocator();
        const auto make = [&](VideoCore::UniqueImage& image, vk::UniqueImageView& view,
                              vk::Format format) {
            view.reset();
            image = VideoCore::UniqueImage(device, allocator);
            image.Create(vk::ImageCreateInfo{
                .imageType = vk::ImageType::e2D,
                .format = format,
                .extent = {w, h, 1},
                .mipLevels = 1,
                .arrayLayers = 1,
                .samples = vk::SampleCountFlagBits::e1,
                .tiling = vk::ImageTiling::eOptimal,
                .usage = vk::ImageUsageFlagBits::eStorage | vk::ImageUsageFlagBits::eSampled,
                .initialLayout = vk::ImageLayout::eUndefined,
            });
            view = Check(device.createImageViewUnique({
                .image = vk::Image(image),
                .viewType = vk::ImageViewType::e2D,
                .format = format,
                .subresourceRange = {vk::ImageAspectFlagBits::eColor, 0, 1, 0, 1},
            }));
        };
        make(order_color_image, order_color_view, vk::Format::eR16G16B16A16Sfloat);
        make(order_depth_image, order_depth_view, vk::Format::eR32Sfloat);
        order_w = w;
        order_h = h;
        order_reset = true;
        std::printf("bbport-order (75): input %ux%u (sampel warna %u, depth %u)\n", w, h,
                    scene.backing->num_samples, depth.backing->num_samples);
        std::fflush(stdout);
    }
    if (!order_store_pipeline) {
        const auto compute = [&](const auto& code, vk::PipelineLayout layout) {
            const auto module = CompileSPV(code, device);
            auto pipeline = Check(device.createComputePipelineUnique(
                {}, vk::ComputePipelineCreateInfo{
                        .stage = {.stage = vk::ShaderStageFlagBits::eCompute,
                                  .module = module,
                                  .pName = "main"},
                        .layout = layout,
                    }));
            device.destroyShaderModule(module);
            return pipeline;
        };
        std::array<vk::DescriptorSetLayoutBinding, 6> prep{};
        for (u32 i = 0; i < prep.size(); ++i) {
            prep[i] = {.binding = i,
                       .descriptorType = i < 3 ? vk::DescriptorType::eSampledImage
                                               : vk::DescriptorType::eStorageImage,
                       .descriptorCount = 1,
                       .stageFlags = vk::ShaderStageFlagBits::eCompute};
        }
        order_prep_desc_layout = Check(device.createDescriptorSetLayoutUnique({
            .flags = vk::DescriptorSetLayoutCreateFlagBits::ePushDescriptorKHR,
            .bindingCount = u32(prep.size()),
            .pBindings = prep.data(),
        }));
        const vk::PushConstantRange prep_push{vk::ShaderStageFlagBits::eCompute, 0, 16};
        order_prep_pipeline_layout = Check(device.createPipelineLayoutUnique({
            .setLayoutCount = 1,
            .pSetLayouts = &*order_prep_desc_layout,
            .pushConstantRangeCount = 1,
            .pPushConstantRanges = &prep_push,
        }));
        std::array<vk::DescriptorSetLayoutBinding, 2> store{};
        for (u32 i = 0; i < store.size(); ++i) {
            store[i] = {.binding = i,
                        .descriptorType = vk::DescriptorType::eStorageImage,
                        .descriptorCount = 1,
                        .stageFlags = vk::ShaderStageFlagBits::eCompute};
        }
        order_store_desc_layout = Check(device.createDescriptorSetLayoutUnique({
            .flags = vk::DescriptorSetLayoutCreateFlagBits::ePushDescriptorKHR,
            .bindingCount = u32(store.size()),
            .pBindings = store.data(),
        }));
        order_store_pipeline_layout = Check(device.createPipelineLayoutUnique({
            .setLayoutCount = 1,
            .pSetLayouts = &*order_store_desc_layout,
        }));
        order_prep_pipelines[0] = compute(ORDER_TAA_PREP_COMP, *order_prep_pipeline_layout);
        order_prep_pipelines[1] = compute(ORDER_TAA_PREP_SMS_COMP, *order_prep_pipeline_layout);
        order_prep_pipelines[2] = compute(ORDER_TAA_PREP_DMS_COMP, *order_prep_pipeline_layout);
        order_prep_pipelines[3] = compute(ORDER_TAA_PREP_SDMS_COMP, *order_prep_pipeline_layout);
        order_store_pipeline = compute(ORDER_TAA_STORE_COMP, *order_store_pipeline_layout);
    }

    const auto depth_format = depth.info.pixel_format;
    const auto scene_view =
        CachedView(scene, vk::Format::eR16G16B16A16Sfloat, vk::ImageAspectFlagBits::eColor);
    const auto depth_view = CachedView(depth, depth_format, vk::ImageAspectFlagBits::eDepth);
    const auto velocity_view =
        CachedView(velocity, vk::Format::eA2B10G10R10UnormPack32, vk::ImageAspectFlagBits::eColor);
    const auto output_guest_view =
        CachedView(output, vk::Format::eR16G16B16A16Sfloat, vk::ImageAspectFlagBits::eColor);

    scheduler.EndRendering();
    const auto read = vk::AccessFlagBits2::eShaderRead;
    const auto cs_stage = vk::PipelineStageFlagBits2::eComputeShader;
    runtime.Transit(&scene, vk::ImageLayout::eGeneral, cs_stage, read);
    runtime.Transit(&velocity, vk::ImageLayout::eGeneral, cs_stage, read);
    runtime.Transit(&depth, vk::ImageLayout::eGeneral, cs_stage, read);
    runtime.Transit(&output, vk::ImageLayout::eGeneral, cs_stage,
                    vk::AccessFlagBits2::eShaderWrite);
    runtime.FlushBarriers();

    const auto cmdbuf = scheduler.CommandBuffer();
    const Breadcrumbs::Scope crumb{cmdbuf, scheduler.CrumbStream(), "Order TAA hook"};
    const auto all = vk::PipelineStageFlagBits2::eAllCommands;
    const auto rw = vk::AccessFlagBits2::eShaderRead | vk::AccessFlagBits2::eShaderWrite;
    const auto barrier = [&](vk::Image image, vk::ImageLayout old_layout, vk::AccessFlags2 src,
                             vk::AccessFlags2 dst) {
        const vk::ImageMemoryBarrier2 b{
            .srcStageMask = all,
            .srcAccessMask = src,
            .dstStageMask = all,
            .dstAccessMask = dst,
            .oldLayout = old_layout,
            .newLayout = vk::ImageLayout::eGeneral,
            .image = image,
            .subresourceRange = {vk::ImageAspectFlagBits::eColor, 0, 1, 0, 1},
        };
        cmdbuf.pipelineBarrier2({.imageMemoryBarrierCount = 1, .pImageMemoryBarriers = &b});
    };
    const auto none = vk::AccessFlagBits2::eNone;
    barrier(vk::Image(order_color_image), vk::ImageLayout::eUndefined, none, rw);
    barrier(vk::Image(order_depth_image), vk::ImageLayout::eUndefined, none, rw);
    barrier(vk::Image(motion_image), vk::ImageLayout::eUndefined, none, rw);
    barrier(vk::Image(output_image), vk::ImageLayout::eUndefined, none, rw);

    {
        const vk::DescriptorImageInfo infos[6] = {
            {.imageView = scene_view, .imageLayout = vk::ImageLayout::eGeneral},
            {.imageView = depth_view, .imageLayout = vk::ImageLayout::eGeneral},
            {.imageView = velocity_view, .imageLayout = vk::ImageLayout::eGeneral},
            {.imageView = *order_color_view, .imageLayout = vk::ImageLayout::eGeneral},
            {.imageView = *order_depth_view, .imageLayout = vk::ImageLayout::eGeneral},
            {.imageView = *motion_view, .imageLayout = vk::ImageLayout::eGeneral},
        };
        std::array<vk::WriteDescriptorSet, 6> writes{};
        for (u32 i = 0; i < writes.size(); ++i) {
            writes[i] = {.dstBinding = i,
                         .descriptorCount = 1,
                         .descriptorType = i < 3 ? vk::DescriptorType::eSampledImage
                                                 : vk::DescriptorType::eStorageImage,
                         .pImageInfo = &infos[i]};
        }
        const u32 variant = (scene.backing->num_samples > 1 ? 1u : 0u) |
                            (depth.backing->num_samples > 1 ? 2u : 0u);
        struct {
            float scale;
            u32 width, height, pad;
        } push{velocity_scale * order_mv, w, h, 0};
        cmdbuf.bindPipeline(vk::PipelineBindPoint::eCompute, *order_prep_pipelines[variant]);
        cmdbuf.pushDescriptorSetKHR(vk::PipelineBindPoint::eCompute, *order_prep_pipeline_layout,
                                    0, writes);
        cmdbuf.pushConstants(*order_prep_pipeline_layout, vk::ShaderStageFlagBits::eCompute, 0,
                             sizeof(push), &push);
        cmdbuf.dispatch((w + 7) / 8, (h + 7) / 8, 1);
    }
    barrier(vk::Image(order_color_image), vk::ImageLayout::eGeneral, rw, rw);
    barrier(vk::Image(order_depth_image), vk::ImageLayout::eGeneral, rw, rw);
    barrier(vk::Image(motion_image), vk::ImageLayout::eGeneral, rw, rw);

    const auto now = std::chrono::steady_clock::now();
    float frame_ms = std::chrono::duration<float, std::milli>(now - order_last_frame).count();
    if (frame_ms <= 0.0f || frame_ms > 200.0f) {
        frame_ms = 16.6f;
    }
    order_last_frame = now;

    bool ok = false;
    if (order_mode == 2) {
        Dlss* dlss = Dlss::Get();
        const Dlss::FeatureDesc desc{w, h, w, h, 0, true};
        ok = true;
        if (!dlss->HasFeature(desc)) {
            scheduler.WaitSubmittedWork();
            dlss->ReleaseFeature();
            ok = dlss->CreateFeature(cmdbuf, desc);
            order_reset = true;
        }
        if (ok) {
            ok = dlss->Evaluate(cmdbuf, {
                .color = {vk::Image(order_color_image), *order_color_view,
                          vk::Format::eR16G16B16A16Sfloat, vk::ImageAspectFlagBits::eColor, w, h},
                .depth = {vk::Image(order_depth_image), *order_depth_view, vk::Format::eR32Sfloat,
                          vk::ImageAspectFlagBits::eColor, w, h},
                .motion = {vk::Image(motion_image), *motion_view, vk::Format::eR16G16Sfloat,
                           vk::ImageAspectFlagBits::eColor, w, h},
                .output = {vk::Image(output_image), *output_view, vk::Format::eR16G16B16A16Sfloat,
                           vk::ImageAspectFlagBits::eColor, w, h},
                .jitter_x = 0.0f,
                .jitter_y = 0.0f,
                .reset = order_reset,
                .frame_ms = frame_ms,
                .sharpness = 0.0f,
            });
        }
        if (!ok) {
            std::printf("bbport-order (75): DLSS gagal; FSR 3.1 dipakai mulai frame berikutnya\n");
            std::fflush(stdout);
            order_mode = 1;
            order_reset = true;
        }
    } else if (context) {
        FfxVkPortableUpscaleDispatchInfo info{};
        info.structSize = sizeof(info);
        info.commandBuffer = cmdbuf;
        const auto rw_usage = vk::ImageUsageFlagBits::eStorage | vk::ImageUsageFlagBits::eSampled;
        info.color = Describe(vk::Image(order_color_image), vk::Format::eR16G16B16A16Sfloat, w, h,
                              rw_usage, vk::ImageAspectFlagBits::eColor,
                              FFX_VK_PORTABLE_RESOURCE_STATE_GENERIC_READ);
        info.depth = Describe(vk::Image(order_depth_image), vk::Format::eR32Sfloat, w, h, rw_usage,
                              vk::ImageAspectFlagBits::eColor,
                              FFX_VK_PORTABLE_RESOURCE_STATE_GENERIC_READ);
        info.motionVectors = Describe(vk::Image(motion_image), vk::Format::eR16G16Sfloat, w, h,
                                      rw_usage, vk::ImageAspectFlagBits::eColor,
                                      FFX_VK_PORTABLE_RESOURCE_STATE_GENERIC_READ);
        info.output = Describe(vk::Image(output_image), vk::Format::eR16G16B16A16Sfloat, w, h,
                               rw_usage | vk::ImageUsageFlagBits::eTransferSrc,
                               vk::ImageAspectFlagBits::eColor,
                               FFX_VK_PORTABLE_RESOURCE_STATE_UNORDERED_ACCESS);
        info.exposure.structSize = sizeof(info.exposure);
        info.reactiveMask.structSize = sizeof(info.reactiveMask);
        info.transparencyAndCompositionMask.structSize = sizeof(info.transparencyAndCompositionMask);
        info.jitterOffset = {0.0f, 0.0f};
        info.motionVectorScale = {1.0f, 1.0f};
        info.renderSize = {w, h};
        info.outputSize = {w, h};
        info.frameTimeMilliseconds = frame_ms;
        info.preExposure = 1.0f;
        info.cameraNear = 0.1f;
        info.cameraFar = 10000.0f;
        info.cameraVerticalFovRadians = 0.9f;
        info.viewSpaceToMeters = 1.0f;
        info.sharpness = 0.0f;
        info.enableSharpening = VK_FALSE;
        info.reset = order_reset ? VK_TRUE : VK_FALSE;
        info.frameId = frame_id++;
        FfxVkPortableUpscaleCreateInfo create_info{};
        create_info.structSize = sizeof(create_info);
        create_info.flags =
            FFX_VK_PORTABLE_CONTEXT_HDR_COLOR_INPUT | FFX_VK_PORTABLE_CONTEXT_AUTO_EXPOSURE;
        create_info.maxRenderSize = {w, h};
        create_info.maxOutputSize = {w, h};
        if (const u64 issues = ffxVkPortableValidateUpscaleDispatchInfo(&create_info, &info)) {
            PrintIssues("Order TAA dispatch", issues);
        } else if (ffxVkPortableUpscaleContextRecordDispatch(context, &info) == FFX_VK_PORTABLE_OK) {
            ok = true;
        }
        if (!ok) {
            std::printf("bbport-order (75): FSR 3.1 gagal; TAA game dipakai lagi\n");
            std::fflush(stdout);
            order_failed = true;
        }
    }
    if (!ok) {
        return false;
    }
    order_reset = false;
    barrier(vk::Image(output_image), vk::ImageLayout::eGeneral, rw, rw);
    {
        const vk::DescriptorImageInfo src{.imageView = *output_view,
                                          .imageLayout = vk::ImageLayout::eGeneral};
        const vk::DescriptorImageInfo dst{.imageView = output_guest_view,
                                          .imageLayout = vk::ImageLayout::eGeneral};
        const std::array<vk::WriteDescriptorSet, 2> writes = {{
            {.dstBinding = 0, .descriptorCount = 1,
             .descriptorType = vk::DescriptorType::eStorageImage, .pImageInfo = &src},
            {.dstBinding = 1, .descriptorCount = 1,
             .descriptorType = vk::DescriptorType::eStorageImage, .pImageInfo = &dst},
        }};
        cmdbuf.bindPipeline(vk::PipelineBindPoint::eCompute, *order_store_pipeline);
        cmdbuf.pushDescriptorSetKHR(vk::PipelineBindPoint::eCompute, *order_store_pipeline_layout,
                                    0, writes);
        cmdbuf.dispatch((w + 7) / 8, (h + 7) / 8, 1);
    }
    return true;
}

} // namespace Vulkan
"""
OT_RAST_DECL_OLD = "namespace Vulkan {\n\nstatic Shader::PushData MakeUserData(const AmdGpu::Regs& regs) {\n"
OT_RAST_DECL_NEW = """namespace Vulkan {

// bbport-order (75): depth of The Order's G-buffer pass (3 color targets, color0 = the
// A2B10G10R10 motion vectors): the scene depth for DLSS / FSR 3.1 in place of the game's TAA.
static VideoCore::ImageId bb_order_scene_depth{};

static Shader::PushData MakeUserData(const AmdGpu::Regs& regs) {
"""
OT_RAST_DEPTH_OLD = "    // bbport: the G-buffer pass (5+ color targets) holds the scene depth, and its constants the\n"
OT_RAST_DEPTH_NEW = """    if (std::popcount(key.mrt_mask) == 3 && db_desc.first && cb_descs[0].first &&
        regs.depth_control.depth_write_enable) { // bbport-order (75)
        const auto& bb_c0 = texture_cache.GetImage(cb_descs[0].first);
        if (bb_c0.info.pixel_format == vk::Format::eA2B10G10R10UnormPack32) {
            bb_order_scene_depth = db_desc.first;
        }
    }
""" + OT_RAST_DEPTH_OLD
OT_RAST_HOOK_OLD = ("        .count = {dim_x, dim_y, dim_z},\n    };\n"
                    "    const bool bb_skip = BbOrderSkipLive(crumb.hash[0]) || BbOrderSkipLive(crumb.hash[1]); // bbport-order (44)\n")
OT_RAST_HOOK_NEW = """        .count = {dim_x, dim_y, dim_z},
    };
    bool bb_skip = BbOrderSkipLive(crumb.hash[0]) || BbOrderSkipLive(crumb.hash[1]); // bbport-order (44)
    if (cs.pgm_hash == 0x92311acaull && !bb_skip && bound_images.size() >= 5) { // bbport-order (75)
        const auto flat = cs.FlatUserData();
        const float bb_scale = flat.size() > 63 ? std::bit_cast<float>(u32(flat[63])) : 0.0f;
        if (upscaler->OrderTaa(bound_images[2], bound_images[1], bb_order_scene_depth,
                               bound_images[bound_images.size() - 1], bb_scale)) {
            bb_skip = true;
        }
    }
"""


def order_taa_hook():
    gpu = BBPORT / 'gpu'
    vk = gpu / 'shadps4' / 'video_core' / 'renderer_vulkan'
    shaders = gpu / 'shadps4' / 'video_core' / 'host_shaders'
    for name, body in (('order_taa_prep.comp', OT_PREP_SHADER), ('order_taa_store.comp', OT_STORE_SHADER)):
        target = shaders / name
        if not target.exists() or target.read_text(encoding='utf-8') != body:
            target.write_text(body, encoding='utf-8')
    cmake = gpu / 'CMakeLists.txt'
    text = read(cmake)
    if 'bbport-order (75)' not in text:
        if text.count(OT_CMAKE_OLD) != 1:
            sys.exit('bagian 75: titik sisip shader tidak ditemukan di gpu/CMakeLists.txt')
        write(cmake, text.replace(OT_CMAKE_OLD, OT_CMAKE_NEW, 1))
    header = vk / 'vk_temporal_upscaler.h'
    text = read(header)
    if 'bbport-order (75)' not in text:
        if text.count(OT_H_OLD) != 1:
            sys.exit('bagian 75: akhir kelas TemporalUpscaler tidak ditemukan')
        write(header, text.replace(OT_H_OLD, OT_H_NEW, 1))
    source = vk / 'vk_temporal_upscaler.cpp'
    text = read(source)
    if 'bbport-order (75)' not in text:
        write(source, text.rstrip('\n') + '\n' + OT_CPP)
    rast = vk / 'vk_rasterizer.cpp'
    text = read(rast)
    if 'bbport-order (75)' in text:
        print('75. DLSS / FSR 3.1 menggantikan TAA game (BB_ORDER_TAA_HOOK): sudah dipatch')
        return
    for name, old in (('deklarasi', OT_RAST_DECL_OLD), ('depth', OT_RAST_DEPTH_OLD),
                      ('dispatch', OT_RAST_HOOK_OLD)):
        if text.count(old) != 1:
            sys.exit('bagian 75: titik sisip %s tidak ditemukan di vk_rasterizer.cpp' % name)
    text = text.replace(OT_RAST_DECL_OLD, OT_RAST_DECL_NEW, 1)
    text = text.replace(OT_RAST_DEPTH_OLD, OT_RAST_DEPTH_NEW, 1)
    text = text.replace(OT_RAST_HOOK_OLD, OT_RAST_HOOK_NEW, 1)
    write(rast, text)
    print('75. DLSS / FSR 3.1 menggantikan TAA game (BB_ORDER_TAA_HOOK=dlss|fsr3, bawaan mati)')


# --- 76. Face bias tanpa slope: 256 / 0 (17 Okt 17:15) ---
# Uji live (BB_ORDER_FACEBIAS_FILE): "256 4" membuat decal lantai (noda/cat semprot) berkedip;
# "256 0" lantai bersih DAN wajah tetap tanpa bintik; "0 0" lantai bersih tapi bintik kembali.
# Slope bias -4 menggeser decal di permukaan miring terlalu jauh. Bawaan sekarang 256 / 0.
FB3_OLD = "            static float fb_def_c = 256.f, fb_def_s = 4.f; // bbport-order (72)\n"
FB3_NEW = "            static float fb_def_c = 256.f, fb_def_s = 0.f; // bbport-order (72) (76: slope 0)\n"
FB3_ENV_OLD = "                    float c = 256.f, s = 4.f;\n"
FB3_ENV_NEW = "                    float c = 256.f, s = 0.f;\n"


def face_bias_no_slope():
    path = BBPORT / 'gpu' / 'shadps4' / 'video_core' / 'renderer_vulkan' / 'vk_rasterizer.cpp'
    text = read(path)
    if 'bbport-order (72) (76: slope 0)' in text:
        print('76. face bias tanpa slope (256/0): sudah dipatch')
        return
    if text.count(FB3_OLD) != 1 or text.count(FB3_ENV_OLD) != 1:
        sys.exit('bagian 76: titik sisip tidak ditemukan (bagian 72 dulu)')
    write(path, text.replace(FB3_OLD, FB3_NEW, 1).replace(FB3_ENV_OLD, FB3_ENV_NEW, 1))
    print('76. face bias bawaan 256 / slope 0 (decal lantai tidak berkedip)')


# --- 77. Ikon segitiga pintu: info + dump image draw PS tertentu saat capture (17 Okt 17:40) ---
# capdoor TAMPIL vs HILANG: masker (#133) dan draw ikon (#134, PS a97669124982a223) identik; hanya
# alamat texture ikon (97x90 dan 64x64 R8G8B8A8) yang berganti. BB_TOGGLE_FILE (cache texture mati)
# dan RT_IGNORE_CPU=0 tidak menolong. BB_ORDER_DIAG_PS=hex[,hex]: saat frame capture, tiap image draw
# PS itu dicatat (alamat, ukuran, format, tile/array mode, pitch, guest_size, flag) dan di-dump ke
# BB_ORDER_DIAG_DIR (raw, bagian 52).
DP_OLD = "        FrameCapture::Draw(vs_info.pgm_hash, ps ? ps->pgm_hash : 0, num_indices, num_instances);\n"
DP_NEW = DP_OLD + """        { // bbport-order (77): BB_ORDER_DIAG_PS -> info + dump image draw ini saat capture
            static const char* bb_list = std::getenv("BB_ORDER_DIAG_PS");
            if (bb_list != nullptr && ps != nullptr) {
                bool bb_hit = false;
                const char* p = bb_list;
                while (*p != 0) {
                    char* end = nullptr;
                    const unsigned long long v = std::strtoull(p, &end, 16);
                    if (end == p) {
                        break;
                    }
                    bb_hit |= v == ps->pgm_hash || v == (ps->pgm_hash & 0xffffffffull);
                    p = (*end == ',') ? end + 1 : end;
                }
                if (bb_hit) {
                    char tag[32];
                    std::snprintf(tag, sizeof(tag), "ps%08x", static_cast<u32>(ps->pgm_hash));
                    const auto images = bound_images;
                    for (const auto image_id : images) {
                        const auto& im = texture_cache.GetImage(image_id);
                        char note[320];
                        std::snprintf(note, sizeof(note),
                                      "\\n  diag ps %08x img %#llx %ux%u fmt %d tile %u array %u "
                                      "pitch %u gsize %u flags %#x samples %u mips %u layers %u",
                                      static_cast<u32>(ps->pgm_hash),
                                      static_cast<unsigned long long>(im.info.guest_address),
                                      im.info.size.width, im.info.size.height,
                                      static_cast<int>(im.info.pixel_format),
                                      static_cast<u32>(im.info.tile_mode),
                                      static_cast<u32>(im.info.array_mode), im.info.pitch,
                                      im.info.guest_size, static_cast<u32>(im.flags),
                                      im.info.num_samples, im.info.resources.levels,
                                      im.info.resources.layers);
                        FrameCapture::Note(note);
                        texture_cache.BbOrderDumpImage(image_id, tag);
                    }
                }
            }
        }
"""


def diag_ps():
    path = BBPORT / 'gpu' / 'shadps4' / 'video_core' / 'renderer_vulkan' / 'vk_rasterizer.cpp'
    text = read(path)
    if 'bbport-order (77)' in text:
        print('77. info + dump image draw PS (BB_ORDER_DIAG_PS): sudah dipatch')
        return
    if text.count(DP_OLD) != 1:
        sys.exit('bagian 77: titik sisip FrameCapture::Draw tidak ditemukan')
    write(path, text.replace(DP_OLD, DP_NEW, 1))
    print('77. BB_ORDER_DIAG_PS=hex: info + dump image draw PS itu saat frame capture')


# --- 78. Ikon segitiga pintu: uji texture kecil dibaca ulang tiap bind (17 Okt 17:55) ---
# Dump bagian 77 (capdoor2): TAMPIL -> texture 64x64 (0x10689f5b00, tile 13) = lingkaran + segitiga;
# HILANG -> ALAMAT SAMA, isi = setengah lingkaran tanpa segitiga (frame animasi prompt). Draw, masker,
# depth sama. Flag image = Registered|GpuModified. Jadi isi texture di bbport tertinggal (animasi ikon
# berhenti di tengah), bukan masalah tiling atau depth.
# BB_ORDER_REFRESH_SMALL=1: texture <= 128x128 yang hanya dibaca ditandai CpuDirty tiap bind ->
# dibaca ulang dari memori game. Segitiga selalu muncul = update dari game terlewat.
RS_OLD = """        const auto debug_native = [&](const VideoCore::Image& image) {
            if (!scene_debug_frame || proxy_candidate || !image.scene_proxy) return;
"""
RS_NEW = """        const auto debug_native = [&](const VideoCore::Image& image) {
            { // bbport-order (78): BB_ORDER_REFRESH_SMALL=1 -> texture kecil dibaca ulang tiap bind
                static const bool bb_refresh = [] {
                    const char* e = std::getenv("BB_ORDER_REFRESH_SMALL");
                    return e != nullptr && e[0] == '1';
                }();
                if (bb_refresh && !image_desc.is_written && !image.binding.is_target &&
                    !image.info.props.is_depth && image.info.size.width <= 128 &&
                    image.info.size.height <= 128) {
                    const_cast<VideoCore::Image&>(image).flags |= VideoCore::ImageFlagBits::CpuDirty;
                }
            }
            if (!scene_debug_frame || proxy_candidate || !image.scene_proxy) return;
"""


def refresh_small():
    path = BBPORT / 'gpu' / 'shadps4' / 'video_core' / 'renderer_vulkan' / 'vk_rasterizer.cpp'
    text = read(path)
    if 'bbport-order (78)' in text:
        print('78. texture kecil dibaca ulang tiap bind (BB_ORDER_REFRESH_SMALL): sudah dipatch')
        return
    if text.count(RS_OLD) != 1:
        sys.exit('bagian 78: titik sisip debug_native tidak ditemukan')
    write(path, text.replace(RS_OLD, RS_NEW, 1))
    print('78. BB_ORDER_REFRESH_SMALL=1: texture <= 128x128 dibaca ulang tiap bind (uji ikon)')


# --- 79. Ikon segitiga pintu: tulisan GPU di tengah texture juga menyegarkan texture (17 Okt 18:00) ---
# 78 (baca ulang texture kecil dari memori tiap bind): FPS jatuh dan teks menu hilang -> data UI
# hanya ada di sisi GPU (disalin GPU), memori game tidak berisi gambar itu. Ikon 64x64 ditandai
# GpuModified dan isinya tertinggal di frame animasi lama. TextureCache::InvalidateMemoryFromGPU hanya
# menyegarkan image yang MULAI tepat di alamat awal tulisan GPU (storage buffer / DMA); salinan GPU yang
# dimulai sebelum texture (satu buffer berisi beberapa ikon) tidak pernah menyegarkannya.
# Perbaikan: tulisan GPU sampai BB_ORDER_GPUWRITE_SPAN MB (bawaan 32, 0 = mati) juga menandai GpuDirty
# image lain yang MULAI di dalam rentang itu, asal image itu hanya texture (bukan render target, depth,
# storage) -> dibaca ulang dari buffer GPU saat dipakai. BB_ORDER_GPUWRITE_LOG=1: catat 40 pertama.
GW_OLD = """        WatchImage(image, "GPU write (marked for refresh)");
        image.flags |= ImageFlagBits::GpuDirty;
    });
}
"""
GW_NEW = """        WatchImage(image, "GPU write (marked for refresh)");
        image.flags |= ImageFlagBits::GpuDirty;
    });
    { // bbport-order (79): texture yang mulai DI DALAM rentang tulisan GPU juga disegarkan
        static const u64 span = [] {
            const char* e = std::getenv("BB_ORDER_GPUWRITE_SPAN");
            return u64(e ? std::strtoull(e, nullptr, 10) : 32) << 20;
        }();
        static const bool log79 = [] {
            const char* e = std::getenv("BB_ORDER_GPUWRITE_LOG");
            return e != nullptr && e[0] == '1';
        }();
        if (span != 0 && max_size > 1 && max_size <= span) {
            ForEachImageInRegion(address, max_size, [&](ImageId image_id, Image& image) {
                if (image.info.guest_address <= address ||
                    image.info.guest_address >= address + max_size) {
                    return;
                }
                if (image.usage.render_target || image.usage.depth_target || image.usage.storage ||
                    image.info.props.is_depth || True(image.flags & ImageFlagBits::GpuDirty)) {
                    return;
                }
                if (log79) {
                    static std::atomic<u32> told79{0};
                    if (told79.fetch_add(1) < 40) {
                        std::printf("bbport-order (79): tulisan GPU %#llx+%#llx menyegarkan texture "
                                    "%#llx %ux%u fmt %u\\n",
                                    (unsigned long long)address, (unsigned long long)max_size,
                                    (unsigned long long)image.info.guest_address,
                                    image.info.size.width, image.info.size.height,
                                    u32(image.info.pixel_format));
                    }
                }
                WatchImage(image, "GPU write inside (79, marked for refresh)");
                image.flags |= ImageFlagBits::GpuDirty;
            });
        }
    }
}
"""


def gpu_write_inside():
    path = BBPORT / 'gpu' / 'shadps4' / 'video_core' / 'texture_cache' / 'texture_cache.cpp'
    text = read(path)
    if 'bbport-order (79)' in text:
        print('79. tulisan GPU di tengah texture menyegarkan texture: sudah dipatch')
        return
    if text.count(GW_OLD) != 1:
        sys.exit('bagian 79: akhir InvalidateMemoryFromGPU tidak ditemukan')
    write(path, text.replace(GW_OLD, GW_NEW, 1))
    print('79. tulisan GPU di tengah texture juga menyegarkan texture (BB_ORDER_GPUWRITE_SPAN MB, bawaan 32)')


# --- 80. Ikon segitiga pintu: apakah memori game di alamat texture berubah? (17 Okt 18:05) ---
# 79 tidak menolong. BB_IMAGE_WATCH=0x10689f5b00: texture diupload SEKALI saat pertama dipakai, lalu
# tidak pernah ada tulisan GPU, tulisan CPU, atau refresh lagi, padahal isinya (dump 77) berubah antar
# frame di game. BB_ORDER_MEMHASH=alamat_hex[,alamat_hex]: tiap texture di alamat itu dipakai, hash
# memori game (guest_size byte) dihitung; berubah -> dicatat (maks 200). BB_ORDER_MEMHASH_REFRESH=1:
# saat berubah texture juga ditandai CpuDirty (dibaca ulang). Hash berubah tanpa refresh = tulisan CPU
# yang terlewat oleh pelacakan halaman; hash tetap = data datang dari jalur lain.
MH_OLD = """            { // bbport-order (78): BB_ORDER_REFRESH_SMALL=1 -> texture kecil dibaca ulang tiap bind
"""
MH_NEW = """            { // bbport-order (80): BB_ORDER_MEMHASH -> hash memori game di alamat texture
                static const char* bb_mh_list = std::getenv("BB_ORDER_MEMHASH");
                static const bool bb_mh_refresh = [] {
                    const char* e = std::getenv("BB_ORDER_MEMHASH_REFRESH");
                    return e != nullptr && e[0] == '1';
                }();
                if (bb_mh_list != nullptr && image.info.guest_size != 0) {
                    bool bb_mh_hit = false;
                    const char* p = bb_mh_list;
                    while (*p != 0) {
                        char* end = nullptr;
                        const unsigned long long v = std::strtoull(p, &end, 16);
                        if (end == p) {
                            break;
                        }
                        bb_mh_hit |= v == image.info.guest_address;
                        p = (*end == ',') ? end + 1 : end;
                    }
                    if (bb_mh_hit) {
                        static std::mutex bb_mh_mutex;
                        static std::unordered_map<VAddr, u64> bb_mh_last;
                        static u32 bb_mh_told = 0, bb_mh_binds = 0;
                        const u64 h = XXH3_64bits(
                            reinterpret_cast<const void*>(image.info.guest_address),
                            image.info.guest_size);
                        std::scoped_lock bb_mh_lock{bb_mh_mutex};
                        ++bb_mh_binds;
                        auto [it, fresh] = bb_mh_last.try_emplace(image.info.guest_address, h);
                        if (fresh || it->second != h) {
                            it->second = h;
                            if (bb_mh_told++ < 200) {
                                std::printf("bbport-order (80): memori %#llx berubah (hash %016llx, "
                                            "bind ke-%u, flags %#x)%s\\n",
                                            (unsigned long long)image.info.guest_address,
                                            (unsigned long long)h, bb_mh_binds,
                                            u32(image.flags),
                                            bb_mh_refresh && !fresh ? " -> dibaca ulang" : "");
                                std::fflush(stdout);
                            }
                            if (bb_mh_refresh && !fresh) {
                                const_cast<VideoCore::Image&>(image).flags |=
                                    VideoCore::ImageFlagBits::CpuDirty;
                            }
                        }
                    }
                }
            }
""" + MH_OLD


def mem_hash():
    path = BBPORT / 'gpu' / 'shadps4' / 'video_core' / 'renderer_vulkan' / 'vk_rasterizer.cpp'
    text = read(path)
    if 'bbport-order (80)' in text:
        print('80. hash memori game di alamat texture (BB_ORDER_MEMHASH): sudah dipatch')
        return
    if text.count(MH_OLD) != 1:
        sys.exit('bagian 80: titik sisip (bagian 78) tidak ditemukan')
    write(path, text.replace(MH_OLD, MH_NEW, 1))
    print('80. BB_ORDER_MEMHASH=alamat: hash memori game texture dicatat saat berubah (uji ikon)')


# --- 81. Bagian 79 bawaan MATI (17 Okt 18:05) ---
# 79 tidak memperbaiki ikon (tidak ada satu pun tulisan GPU di atas texture ikon), jadi dimatikan agar
# tidak mengubah perilaku texture lain. BB_ORDER_GPUWRITE_SPAN=32 menyalakan lagi untuk uji.
# Temuan ikon (BB_ORDER_MEMHASH): alamat texture UI (97x90 noda, 64x64 ikon) adalah memori sementara
# yang dipakai ulang tiap frame; dibaca ulang dari memori game = rusak. Pengisinya belum ditemukan.
GS_OLD = "            return u64(e ? std::strtoull(e, nullptr, 10) : 32) << 20;\n"
GS_NEW = "            return u64(e ? std::strtoull(e, nullptr, 10) : 0) << 20; // bbport-order (81): bawaan mati\n"


def gpu_write_inside_off():
    path = BBPORT / 'gpu' / 'shadps4' / 'video_core' / 'texture_cache' / 'texture_cache.cpp'
    text = read(path)
    if 'bbport-order (81)' in text:
        print('81. bagian 79 bawaan mati: sudah dipatch')
        return
    if text.count(GS_OLD) != 1:
        sys.exit('bagian 81: titik sisip (bagian 79) tidak ditemukan')
    write(path, text.replace(GS_OLD, GS_NEW, 1))
    print('81. bagian 79 bawaan mati (BB_ORDER_GPUWRITE_SPAN=32 untuk uji)')


# --- 82. Menu overlay Bloodborne (Insert / L3+R3) dimatikan (17 Okt 18:20) ---
# bbport membuka menu grafis Bloodborne dengan Insert atau L3+R3; di The Order L3/R3 dipakai game.
# Menu itu tidak berlaku untuk game ini. BB_ORDER_MENU=1 menyalakannya lagi (pengembangan).
OV_HELPER_OLD = "bool HandleEvent(const SDL_Event& event) {\n"
OV_HELPER_NEW = """// bbport-order (82): menu overlay Bloodborne hanya dengan BB_ORDER_MENU=1.
static bool BbOrderMenuKeys() {
    static const bool on = [] {
        const char* e = std::getenv("BB_ORDER_MENU");
        return e != nullptr && e[0] == '1';
    }();
    return on;
}

""" + OV_HELPER_OLD
OV_KEY_OLD = "            (event.key.key == SDLK_INSERT || (is_open && event.key.key == SDLK_ESCAPE))) {\n"
OV_KEY_NEW = "            ((BbOrderMenuKeys() && event.key.key == SDLK_INSERT) || (is_open && event.key.key == SDLK_ESCAPE))) {\n"
OV_PAD_OLD = "        if (down && l3_down && r3_down) {\n"
OV_PAD_NEW = "        if (down && l3_down && r3_down && BbOrderMenuKeys()) { // bbport-order (82)\n"


def overlay_menu_off():
    path = BBPORT / 'gpu' / 'shim' / 'bbport_overlay.cpp'
    text = read(path)
    if 'bbport-order (82)' in text:
        print('82. menu overlay Bloodborne (Insert / L3+R3) mati: sudah dipatch')
        return
    for old in (OV_HELPER_OLD, OV_KEY_OLD, OV_PAD_OLD):
        if text.count(old) != 1:
            sys.exit('bagian 82: titik sisip tidak ditemukan di bbport_overlay.cpp')
    text = text.replace(OV_HELPER_OLD, OV_HELPER_NEW, 1).replace(OV_KEY_OLD, OV_KEY_NEW, 1)
    write(path, text.replace(OV_PAD_OLD, OV_PAD_NEW, 1))
    print('82. menu overlay Bloodborne (Insert / L3+R3) dimatikan (BB_ORDER_MENU=1 menyalakan)')


# --- 83. Crash cutscene: MapNumberConversion "Unreachable" untuk T# sampah (17 Okt 18:40) ---
# AppImage, cutscene prolog: "MapNumberConversion: Unreachable code! data_fmt = 25" -> STOP. T# sampah
# (num_format SnormNz dengan data_format yang tidak punya konversi, mis. dari shader a7b66f58 yang
# juga disebut di shadPS4 PR #4798) membuat recompiler berhenti. Sekarang: tanpa konversi (None).
NC_OLD = """            return NumberConversion::Sint16ToSnormNz;
        default:
            UNREACHABLE_MSG("data_fmt = {}", u32(data_fmt));
        }"""
NC_NEW = """            return NumberConversion::Sint16ToSnormNz;
        default:
            return NumberConversion::None; // bbport-order (83): T# sampah, jangan berhenti
        }"""


def number_conversion_safe():
    path = BBPORT / 'gpu' / 'shadps4' / 'video_core' / 'amdgpu' / 'pixel_format.h'
    text = read(path)
    if 'bbport-order (83)' in text:
        print('83. MapNumberConversion tanpa crash untuk T# sampah: sudah dipatch')
        return
    if text.count(NC_OLD) != 1:
        sys.exit('bagian 83: titik sisip MapNumberConversion tidak ditemukan')
    write(path, text.replace(NC_OLD, NC_NEW, 1))
    print('83. MapNumberConversion: format tanpa konversi = None (crash cutscene)')


# --- 84. Lag cutscene: shader 539eee77 ikut aturan permutasi longgar (17 Okt 18:40) ---
# Log yang sama: shader material 0x539eee77 mencapai 41 permutasi (slot kosong/terisi, 2D/cube
# berganti) -> compile terus saat cutscene. Ditambahkan ke daftar BB_ORDER_LOOSE_SHADER bawaan
# (hanya aturan permutasi longgar, bukan "hanya 2D": texture cube tetap dipakai).
LS_OLD = '            const char* p = e ? e : "%s";\n' % ORDER_SHADERS
LS_NEW = ('            const char* p = e ? e : (k == 0 ? "%s,539eee77" : "%s"); // bbport-order (84)\n'
          % (ORDER_SHADERS, ORDER_SHADERS))


def loose_539():
    path = BBPORT / 'gpu' / 'shadps4' / 'shader_recompiler' / 'resource.h'
    text = read(path)
    if 'bbport-order (84)' in text:
        print('84. shader 539eee77 di daftar permutasi longgar: sudah dipatch')
        return
    if text.count(LS_OLD) != 1:
        sys.exit('bagian 84: daftar shader bawaan (bagian 23) tidak ditemukan di resource.h')
    write(path, text.replace(LS_OLD, LS_NEW, 1))
    print('84. shader 539eee77 ikut aturan permutasi longgar (lag cutscene)')


# --- 85. Rekam stutter cutscene: waktu compile per permutasi + alasan lengkap (17 Okt 19:10) ---
# Log 19:00: 43 "Stall" 260 ms, tiap kali bersamaan dengan 2 permutasi baru shader 539eee77
# (+-130 ms per permutasi, di thread GPU). Aturan longgar (84) tidak menangkapnya. Untuk tahu
# kenapa: alasan permutasi sekarang juga mencatat srgb/konversi angka/storage, dan setiap
# compile > 15 ms mencatat waktunya per tahap (terjemah GCN, SPIR-V, modul Vulkan, simpan cache).
PERM_FMT_OLD = """            why += fmt::format(" img{}(type {}->{} int {}->{} cube {}->{} binds {}->{})", i,
                               u32(b.images[i].type), u32(a.images[i].type), b.images[i].is_integer,
                               a.images[i].is_integer, b.images[i].is_cube, a.images[i].is_cube,
                               b.images[i].num_bindings, a.images[i].num_bindings);"""
PERM_FMT_NEW = """            why += fmt::format(" img{}(type {}->{} int {}->{} cube {}->{} binds {}->{} srgb {}->{} conv {}->{} st {}->{})", i, // bbport-order (85)
                               u32(b.images[i].type), u32(a.images[i].type), b.images[i].is_integer,
                               a.images[i].is_integer, b.images[i].is_cube, a.images[i].is_cube,
                               b.images[i].num_bindings, a.images[i].num_bindings,
                               b.images[i].is_srgb, a.images[i].is_srgb,
                               u32(b.images[i].num_conversion), u32(a.images[i].num_conversion),
                               b.images[i].is_storage, a.images[i].is_storage);"""
CM_OLD1 = """    CompileTimer timer;

    const auto ir_program = Shader::TranslateProgram(code, pools, info, runtime_info, profile);
    auto spv = Shader::Backend::SPIRV::EmitSPIRV(profile, runtime_info, ir_program, binding);
    DumpShader(spv, info.pgm_hash, info.hw_stage, perm_idx, "spv");
"""
CM_NEW1 = """    CompileTimer timer;
    using BbClk = std::chrono::steady_clock; // bbport-order (85): waktu per tahap
    const auto bb_t0 = BbClk::now();

    const auto ir_program = Shader::TranslateProgram(code, pools, info, runtime_info, profile);
    const auto bb_t1 = BbClk::now();
    auto spv = Shader::Backend::SPIRV::EmitSPIRV(profile, runtime_info, ir_program, binding);
    const auto bb_t2 = BbClk::now();
    DumpShader(spv, info.pgm_hash, info.hw_stage, perm_idx, "spv");
"""
CM_OLD2 = """        module = CompileSPV(spv, instance.GetDevice());
    }

    RegisterShaderBinary(std::move(spv), info.pgm_hash, perm_idx);
"""
CM_NEW2 = """        module = CompileSPV(spv, instance.GetDevice());
    }
    const auto bb_t3 = BbClk::now();
    const size_t bb_words = spv.size();

    RegisterShaderBinary(std::move(spv), info.pgm_hash, perm_idx);
    {
        const auto bb_t4 = BbClk::now();
        auto ms = [](auto a, auto b) { return std::chrono::duration<double, std::milli>(b - a).count(); };
        if (ms(bb_t0, bb_t4) > 15.0) {
            LOG_WARNING(Render_Vulkan,
                        "bbport-order (85): compile shader {:#x} perm {} = {:.1f} ms (terjemah {:.1f}, "
                        "spirv {:.1f}, modul {:.1f}, simpan {:.1f}; {} kata, {} inst GCN)",
                        info.pgm_hash, perm_idx, ms(bb_t0, bb_t4), ms(bb_t0, bb_t1), ms(bb_t1, bb_t2),
                        ms(bb_t2, bb_t3), ms(bb_t3, bb_t4), bb_words, code.size());
        }
    }
"""
GP_OLD = """        GraphicsPipeline::SerializationSupport sdata{};
        it.value() = std::make_unique<GraphicsPipeline>(
            instance, scheduler, desc_heap, profile, sel.graphics_key, *pipeline_cache, sel.infos,
            sel.runtime_infos, sel.fetch_shader, sel.modules, sdata, false);
"""
GP_NEW = """        GraphicsPipeline::SerializationSupport sdata{};
        const auto bb_p0 = std::chrono::steady_clock::now(); // bbport-order (85)
        it.value() = std::make_unique<GraphicsPipeline>(
            instance, scheduler, desc_heap, profile, sel.graphics_key, *pipeline_cache, sel.infos,
            sel.runtime_infos, sel.fetch_shader, sel.modules, sdata, false);
        if (const double bb_ms = std::chrono::duration<double, std::milli>(
                std::chrono::steady_clock::now() - bb_p0).count(); bb_ms > 15.0) {
            LOG_WARNING(Render_Vulkan, "bbport-order (85): pipeline {:#x} di thread GPU = {:.1f} ms "
                        "(ps {:#x}, async tidak boleh)", pipeline_hash, bb_ms,
                        sel.infos[u32(Shader::SwStage::Fragment)] ? sel.infos[u32(Shader::SwStage::Fragment)]->pgm_hash : 0);
        }
"""


def compile_timing():
    path = BBPORT / 'gpu' / 'shadps4' / 'video_core' / 'renderer_vulkan' / 'vk_pipeline_cache.cpp'
    text = read(path)
    if 'bbport-order (85)' in text:
        print('85. catatan waktu compile per permutasi: sudah dipatch')
        return
    for name, old in (('PERM_FMT', PERM_FMT_OLD), ('CM1', CM_OLD1), ('CM2', CM_OLD2), ('GP', GP_OLD)):
        if text.count(old) != 1:
            sys.exit('bagian 85: titik sisip %s tidak ditemukan di vk_pipeline_cache.cpp' % name)
    text = (text.replace(PERM_FMT_OLD, PERM_FMT_NEW, 1).replace(CM_OLD1, CM_NEW1, 1)
            .replace(CM_OLD2, CM_NEW2, 1).replace(GP_OLD, GP_NEW, 1))
    write(path, text)
    print('85. catatan waktu compile per permutasi + alasan srgb/konversi (rekam stutter)')


# --- 86. Stutter cutscene: pipeline Vulkan di thread GPU, alasan + BB_ORDER_ASYNC_ALL (17 Okt 19:20) ---
# Rekaman 19:12 (bagian 85): terjemah shader cepat (maks 15 ms). Yang lama: driver NVIDIA membuat
# pipeline grafis, 112-232 ms per pipeline, 50 kali, di thread GPU (ps c74df487 28x, 99368239 21x).
# Compile di belakang (BB_ASYNC_PIPELINES) tidak dipakai untuk draw itu. Sekarang log 85 mencatat
# aturan mana yang menolak, dan BB_ORDER_ASYNC_ALL=1 (percobaan) melonggarkan aturan "digambar
# tiap frame" dan "frame >= 300 draw" (layar penuh dan indirect tetap menunggu).
AS_VARS_OLD = "std::unordered_map<u64, TargetStreak> target_streaks;\n"
AS_VARS_NEW = (AS_VARS_OLD +
    "// bbport-order (86): kenapa draw terakhir tidak boleh compile di belakang\n"
    "int bb_async_why = 0;\n"
    "u64 bb_async_draws = 0;\n"
    "u32 bb_async_streak = 0;\n"
    "const char* const bb_async_names[] = {\"-\", \"BB_ASYNC_PIPELINES=0\", \"tanpa vertex input dinamis\",\n"
    "    \"tanpa regs\", \"frame < 300 draw\", \"indirect\", \"layar penuh\", \"target belum 8 frame\"};\n")
AS_EN_OLD = "    if (!enabled || !instance.IsVertexInputDynamicState() || !selection.regs) {\n"
AS_EN_NEW = ("    static const bool bb_all = [] { // bbport-order (86)\n"
             "        const char* e = std::getenv(\"BB_ORDER_ASYNC_ALL\");\n"
             "        return e && e[0] == '1';\n"
             "    }();\n"
             "    bb_async_why = !enabled ? 1 : !instance.IsVertexInputDynamicState() ? 2 : !selection.regs ? 3 : 0;\n"
             + AS_EN_OLD)
AS_DR_OLD = "    if (last_frame_draws < 300) {\n"
AS_DR_NEW = ("    bb_async_draws = last_frame_draws;\n"
             "    if (last_frame_draws < 300 && !bb_all && (bb_async_why = 4, true)) { // bbport-order (86)\n")
AS_FS_OLD = "    if (indirect || selection.regs->num_indices <= FullScreenIndices) {\n"
AS_FS_NEW = ("    if ((indirect || selection.regs->num_indices <= FullScreenIndices) &&\n"
             "        (bb_async_why = indirect ? 5 : 6, true)) { // bbport-order (86)\n")
AS_RET_OLD = "    return target != 0 && streak != target_streaks.end() && streak->second.frames >= PerFrameStreak;\n"
AS_RET_NEW = ("    const bool bb_ok = target != 0 && streak != target_streaks.end() &&\n"
              "                       streak->second.frames >= PerFrameStreak; // bbport-order (86)\n"
              "    if (!bb_ok) {\n"
              "        bb_async_why = 7;\n"
              "        bb_async_streak = streak != target_streaks.end() ? streak->second.frames : 0;\n"
              "    }\n"
              "    return bb_ok || (bb_all && target != 0);\n")
AS_LOG_OLD = r"""            LOG_WARNING(Render_Vulkan, "bbport-order (85): pipeline {:#x} di thread GPU = {:.1f} ms "
                        "(ps {:#x}, async tidak boleh)", pipeline_hash, bb_ms,
                        sel.infos[u32(Shader::SwStage::Fragment)] ? sel.infos[u32(Shader::SwStage::Fragment)]->pgm_hash : 0);"""
AS_LOG_NEW = r"""            LOG_WARNING(Render_Vulkan, "bbport-order (85): pipeline {:#x} di thread GPU = {:.1f} ms "
                        "(ps {:#x}, vs {:#x}; async tidak: {}, {} draw/frame, target {} frame, {} indeks)", // (86)
                        pipeline_hash, bb_ms,
                        sel.infos[u32(Shader::SwStage::Fragment)] ? sel.infos[u32(Shader::SwStage::Fragment)]->pgm_hash : 0,
                        sel.infos[u32(Shader::SwStage::Vertex)] ? sel.infos[u32(Shader::SwStage::Vertex)]->pgm_hash : 0,
                        bb_async_names[bb_async_why], bb_async_draws, bb_async_streak,
                        sel.regs ? u32(sel.regs->num_indices) : 0u);"""


def async_reason():
    path = BBPORT / 'gpu' / 'shadps4' / 'video_core' / 'renderer_vulkan' / 'vk_pipeline_cache.cpp'
    text = read(path)
    if 'bbport-order (86)' in text:
        print('86. alasan compile pipeline di thread GPU + BB_ORDER_ASYNC_ALL: sudah dipatch')
        return
    pairs = ((AS_VARS_OLD, AS_VARS_NEW), (AS_EN_OLD, AS_EN_NEW), (AS_DR_OLD, AS_DR_NEW),
             (AS_FS_OLD, AS_FS_NEW), (AS_RET_OLD, AS_RET_NEW), (AS_LOG_OLD, AS_LOG_NEW))
    for i, (old, _) in enumerate(pairs):
        if text.count(old) != 1:
            sys.exit('bagian 86: titik sisip %d tidak ditemukan (bagian 85 belum terpasang?)' % i)
    for old, new in pairs:
        text = text.replace(old, new, 1)
    write(path, text)
    print('86. alasan compile pipeline di thread GPU dicatat; BB_ORDER_ASYNC_ALL=1 = percobaan')

# --- 87. Stutter cutscene: kenapa ps c74df487/99368239 terus butuh pipeline baru (17 Okt 19:30) ---
# Rekaman A/B 19:23: semua 43-49 pipeline lambat (112-120 ms) ditolak compile di belakang karena
# draw-nya indirect (vs d1017d4b, 6 indeks). Shader-nya tidak punya permutasi baru, jadi yang
# berubah ada di kunci pipeline (format/blend/mask/sampel...). Sekarang setiap pipeline lambat
# membandingkan kuncinya dengan pipeline lain yang memakai shader sama dan mencatat field yang
# berbeda. BB_ORDER_ASYNC_ALL=2 (percobaan): draw indirect juga boleh compile di belakang.
KD_OLD = "                        sel.regs ? u32(sel.regs->num_indices) : 0u);\n"
KD_NEW = KD_OLD + r"""            // bbport-order (87): field kunci yang berbeda dari pipeline lain dengan shader yang sama
            const GraphicsPipelineKey& nk = sel.graphics_key;
            for (auto it2 = graphics_pipelines.begin(); it2 != graphics_pipelines.end(); ++it2) {
                const GraphicsPipelineKey& ok = it2->first;
                if (ok == nk || ok.stage_hashes != nk.stage_hashes) {
                    continue;
                }
                std::string d;
                auto hex = [](const void* p, size_t n) {
                    std::string s;
                    for (size_t j = 0; j < n && j < 8; ++j) s += fmt::format("{:02x}", static_cast<const u8*>(p)[j]);
                    return s;
                };
                auto arr = [&](const char* name, const auto& a, const auto& b) {
                    for (size_t j = 0; j < a.size(); ++j) {
                        if (std::memcmp(&a[j], &b[j], sizeof(a[j])) != 0) {
                            d += fmt::format(" {}[{}] {}->{}", name, j, hex(&b[j], sizeof(b[j])), hex(&a[j], sizeof(a[j])));
                        }
                    }
                };
                auto one = [&](const char* name, u64 a, u64 b) {
                    if (a != b) d += fmt::format(" {} {}->{}", name, b, a);
                };
                arr("vbfmt", nk.vertex_buffer_formats, ok.vertex_buffer_formats);
                one("pcp", nk.patch_control_points, ok.patch_control_points);
                one("ncolor", nk.num_color_attachments, ok.num_color_attachments);
                arr("cb", nk.color_buffers, ok.color_buffers);
                arr("blend", nk.blend_controls, ok.blend_controls);
                arr("wmask", nk.write_masks, ok.write_masks);
                one("cbmask", u64(nk.cb_shader_mask.raw), u64(ok.cb_shader_mask.raw));
                one("logic", u64(nk.logic_op), u64(ok.logic_op));
                one("samples", nk.num_samples, ok.num_samples);
                one("zsamples", nk.depth_samples, ok.depth_samples);
                arr("csamples", nk.color_samples, ok.color_samples);
                one("mrt", nk.mrt_mask, ok.mrt_mask);
                one("mv", nk.motion_vectors, ok.motion_vectors);
                one("zfmt", u64(nk.z_format), u64(ok.z_format));
                one("sfmt", u64(nk.stencil_format), u64(ok.stencil_format));
                one("zclamp", nk.depth_clamp_enable, ok.depth_clamp_enable);
                one("prim", u64(nk.prim_type), u64(ok.prim_type));
                one("poly", u64(nk.polygon_mode), u64(ok.polygon_mode));
                one("clip", u64(nk.clip_space), u64(ok.clip_space));
                one("pvtx", u64(nk.provoking_vtx_last), u64(ok.provoking_vtx_last));
                one("zclip", nk.depth_clip_enable, ok.depth_clip_enable);
                LOG_WARNING(Render_Vulkan, "bbport-order (87): beda kunci dari pipeline lain shader sama:{}",
                            d.empty() ? " (tidak ada field berbeda?)" : d);
                break;
            }
"""
AL_OLD = """    static const bool bb_all = [] { // bbport-order (86)
        const char* e = std::getenv("BB_ORDER_ASYNC_ALL");
        return e && e[0] == '1';
    }();
"""
AL_NEW = """    static const int bb_all = [] { // bbport-order (86/87): 1 = aturan longgar, 2 = + indirect
        const char* e = std::getenv("BB_ORDER_ASYNC_ALL");
        return e ? std::atoi(e) : 0;
    }();
"""
AI_OLD = """    if ((indirect || selection.regs->num_indices <= FullScreenIndices) &&
        (bb_async_why = indirect ? 5 : 6, true)) { // bbport-order (86)
"""
AI_NEW = """    if (((indirect && bb_all < 2) || (!indirect && selection.regs->num_indices <= FullScreenIndices)) &&
        (bb_async_why = indirect ? 5 : 6, true)) { // bbport-order (86/87)
"""


def key_diff():
    path = BBPORT / 'gpu' / 'shadps4' / 'video_core' / 'renderer_vulkan' / 'vk_pipeline_cache.cpp'
    text = read(path)
    if 'bbport-order (87)' in text:
        print('87. beda kunci pipeline + BB_ORDER_ASYNC_ALL=2: sudah dipatch')
        return
    for i, old in enumerate((KD_OLD, AL_OLD, AI_OLD)):
        if text.count(old) != 1:
            sys.exit('bagian 87: titik sisip %d tidak ditemukan (bagian 86 belum terpasang?)' % i)
    text = text.replace(KD_OLD, KD_NEW, 1).replace(AL_OLD, AL_NEW, 1).replace(AI_OLD, AI_NEW, 1)
    write(path, text)
    print('87. pipeline lambat mencatat field kunci yang berbeda; BB_ORDER_ASYNC_ALL=2 = + indirect')

# --- 88. Stutter cutscene: draw indirect boleh compile di belakang, aturan "tiap frame" tetap (17 Okt 19:45) ---
# Tes 19:37 BB_ORDER_ASYNC_ALL=2: stutter hilang, tapi di cutscene berikutnya karakter tidak muncul
# sampai gameplay. ALL melonggarkan juga aturan "target digambar 8 frame berturut-turut", yang
# melindungi render sekali jalan (karakter/wajah yang disiapkan sekali di awal cutscene): render itu
# terlewat. Rekaman A menunjukkan yang menghalangi hanya aturan indirect. Sekarang bawaan: draw
# indirect ikut compile di belakang bila targetnya digambar tiap frame; aturan lain tetap.
# BB_ORDER_ASYNC_INDIRECT=0: aturan lama. BB_ORDER_ASYNC_ALL=1/2: percobaan lama (berisiko).
IN_OLD = """    if (((indirect && bb_all < 2) || (!indirect && selection.regs->num_indices <= FullScreenIndices)) &&
        (bb_async_why = indirect ? 5 : 6, true)) { // bbport-order (86/87)
"""
IN_NEW = """    static const bool bb_ind = [] { // bbport-order (88): indirect di belakang bila tiap frame
        const char* e = std::getenv("BB_ORDER_ASYNC_INDIRECT");
        return !(e && e[0] == '0');
    }();
    if (((indirect && bb_all < 2 && !bb_ind) || (!indirect && selection.regs->num_indices <= FullScreenIndices)) &&
        (bb_async_why = indirect ? 5 : 6, true)) { // bbport-order (86/87/88)
"""
RT_OLD = "    return bb_ok || (bb_all && target != 0);\n"
RT_NEW = "    return bb_ok || (bb_all >= 1 && target != 0 && !indirect); // bbport-order (88)\n"


def async_indirect():
    path = BBPORT / 'gpu' / 'shadps4' / 'video_core' / 'renderer_vulkan' / 'vk_pipeline_cache.cpp'
    text = read(path)
    if 'bbport-order (88)' in text:
        print('88. draw indirect compile di belakang (target tiap frame): sudah dipatch')
        return
    for i, old in enumerate((IN_OLD, RT_OLD)):
        if text.count(old) != 1:
            sys.exit('bagian 88: titik sisip %d tidak ditemukan (bagian 87 belum terpasang?)' % i)
    text = text.replace(IN_OLD, IN_NEW, 1).replace(RT_OLD, RT_NEW, 1)
    write(path, text)
    print('88. draw indirect compile di belakang bila targetnya digambar tiap frame (stutter cutscene)')

# --- 89. Kedip objek jauh (kereta, orang di alun-alun): buffer dengan alamat tidak rata 4 byte (17 Okt 20:05) ---
# Video 19:51: kereta/orang di kejauhan hilang-muncul tiap beberapa frame. Tes 19:57: tetap kedip
# tanpa compile di belakang (88), dengan barrier penuh (66) dan dengan Safe -> bukan race. Log:
# +-2000/detik "Buffer binding in shader ... isn't dword aligned" (14 shader). GCN membaca dword dari
# alamat byte mana pun; port membagi offset dengan 4 (buf_off >> 2), jadi bila alamat V# bergeser
# 1-3 byte (ring buffer per frame) shader membaca data yang tergeser -> objek hilang di frame itu.
# Sekarang: baca dword dari alamat tidak rata = gabungan dua dword (geser byte). BB_ORDER_UNALIGNED=0
# mematikan. Log peringatan dibatasi (log 57 MB). Shader lama di cache harus di-compile ulang.
UA_HELPER_ANCHOR = "Id EmitReadConstBuffer(EmitContext& ctx, u32 handle, Id index) {\n"
UA_HELPER = r"""// bbport-order (89): dword dari alamat buffer yang tidak rata 4 byte (alamat V# + 1..3).
static bool BbOrderUnalignedOn() {
    static const bool on = [] {
        const char* e = std::getenv("BB_ORDER_UNALIGNED");
        return !(e && e[0] == '0');
    }();
    return on;
}

/// lo/hi = dword ke-n dan ke-n+1 (u32). Hasil = 4 byte mulai (buf_off & 3) di dalam lo.
static Id BbOrderJoinUnaligned(EmitContext& ctx, Id byte_off, Id lo, Id hi) {
    const Id sh = ctx.OpShiftLeftLogical(ctx.U32[1], ctx.OpBitwiseAnd(ctx.U32[1], byte_off, ctx.ConstU32(3u)),
                                         ctx.ConstU32(3u));
    const Id aligned = ctx.OpIEqual(ctx.U1[1], sh, ctx.u32_zero_value);
    const Id back = ctx.OpSelect(ctx.U32[1], aligned, ctx.u32_zero_value,
                                 ctx.OpISub(ctx.U32[1], ctx.ConstU32(32u), sh));
    const Id joined = ctx.OpBitwiseOr(ctx.U32[1], ctx.OpShiftRightLogical(ctx.U32[1], lo, sh),
                                      ctx.OpShiftLeftLogical(ctx.U32[1], hi, back));
    return ctx.OpSelect(ctx.U32[1], aligned, lo, joined);
}

"""
RCB_OLD = """    const auto [id, pointer_type] = buffer.Alias(PointerType::U32);
    const Id ptr{ctx.OpAccessChain(pointer_type, id, ctx.u32_zero_value, index)};
    const Id result{ctx.OpLoad(ctx.U32[1], ptr)};
    return result;
}
"""
RCB_NEW = """    const auto [id, pointer_type] = buffer.Alias(PointerType::U32);
    const Id ptr{ctx.OpAccessChain(pointer_type, id, ctx.u32_zero_value, index)};
    const Id result{ctx.OpLoad(ctx.U32[1], ptr)};
    if (const Id byte_off = buffer.Offset(PointerSize::B8);
        BbOrderUnalignedOn() && !buffer.paged && Sirit::ValidId(byte_off)) { // bbport-order (89)
        const Id next = ctx.OpIAdd(ctx.U32[1], index, ctx.ConstU32(1u));
        const Id hi{ctx.OpLoad(ctx.U32[1], ctx.OpAccessChain(pointer_type, id, ctx.u32_zero_value, next))};
        return BbOrderJoinUnaligned(ctx, byte_off, result, hi);
    }
    return result;
}
"""
LB_OLD = """    boost::container::static_vector<Id, N> ids;
    for (u32 i = 0; i < N; i++) {
        const Id index_i = i == 0 ? address : ctx.OpIAdd(ctx.U32[1], address, ctx.ConstU32(i));
        if (spv_buffer.paged) {
            const Id zero = alias == PointerType::U32 ? ctx.u32_zero_value : ctx.f32_zero_value;
            ids.push_back(PagedLoad(ctx, spv_buffer, index_i, 4, data_types[1], zero));
            continue;
        }
        const Id ptr_i = ctx.OpAccessChain(pointer_type, id, ctx.u32_zero_value, index_i);
        const Id result_i = ctx.OpLoad(data_types[1], ptr_i);
        ids.push_back(result_i);
    }
"""
LB_NEW = """    boost::container::static_vector<Id, N> ids;
    // bbport-order (89): alamat buffer tidak rata 4 byte -> N+1 dword, gabungkan yang berdampingan.
    if (const Id byte_off = spv_buffer.Offset(PointerSize::B8);
        BbOrderUnalignedOn() && !spv_buffer.paged && Sirit::ValidId(byte_off)) {
        boost::container::static_vector<Id, N + 1> raw;
        for (u32 i = 0; i <= N; i++) {
            const Id index_i = i == 0 ? address : ctx.OpIAdd(ctx.U32[1], address, ctx.ConstU32(i));
            const Id ptr_i = ctx.OpAccessChain(pointer_type, id, ctx.u32_zero_value, index_i);
            const Id v = ctx.OpLoad(data_types[1], ptr_i);
            raw.push_back(alias == PointerType::U32 ? v : ctx.OpBitcast(ctx.U32[1], v));
        }
        for (u32 i = 0; i < N; i++) {
            const Id j = BbOrderJoinUnaligned(ctx, byte_off, raw[i], raw[i + 1]);
            ids.push_back(alias == PointerType::U32 ? j : ctx.OpBitcast(ctx.F32[1], j));
        }
        return N == 1 ? ids[0] : ctx.OpCompositeConstruct(data_types[N], ids);
    }
    for (u32 i = 0; i < N; i++) {
        const Id index_i = i == 0 ? address : ctx.OpIAdd(ctx.U32[1], address, ctx.ConstU32(i));
        if (spv_buffer.paged) {
            const Id zero = alias == PointerType::U32 ? ctx.u32_zero_value : ctx.f32_zero_value;
            ids.push_back(PagedLoad(ctx, spv_buffer, index_i, 4, data_types[1], zero));
            continue;
        }
        const Id ptr_i = ctx.OpAccessChain(pointer_type, id, ctx.u32_zero_value, index_i);
        const Id result_i = ctx.OpLoad(data_types[1], ptr_i);
        ids.push_back(result_i);
    }
"""
DW_OLD = """                if (adjust % 4 != 0) {
                    LOG_WARNING(Render_Vulkan, "Buffer binding in shader {:#x} isn't dword aligned",
                                stage.pgm_hash);
                }
"""
DW_NEW = """                if (adjust % 4 != 0) { // bbport-order (89): dibaca benar di shader; log dibatasi
                    static std::atomic<u32> bb_told{0};
                    if (bb_told.fetch_add(1) < 40) {
                        LOG_WARNING(Render_Vulkan, "Buffer binding in shader {:#x} isn't dword aligned "
                                    "(+{} byte, ukuran {}, tulis {}, format {})", stage.pgm_hash,
                                    adjust % 4, size, desc.is_written, desc.is_formatted);
                    }
                }
"""


def unaligned_buffers():
    sp = BBPORT / 'gpu' / 'shadps4' / 'shader_recompiler' / 'backend' / 'spirv' / 'emit_spirv_context_get_set.cpp'
    rz = BBPORT / 'gpu' / 'shadps4' / 'video_core' / 'renderer_vulkan' / 'vk_rasterizer.cpp'
    st, rt = read(sp), read(rz)
    if 'bbport-order (89)' in st and 'bbport-order (89)' in rt:
        print('89. baca buffer dari alamat tidak rata 4 byte: sudah dipatch')
        return
    for name, text, old in (('helper', st, UA_HELPER_ANCHOR), ('ReadConstBuffer', st, RCB_OLD),
                            ('LoadBuffer', st, LB_OLD), ('warning', rt, DW_OLD)):
        if text.count(old) != 1:
            sys.exit('bagian 89: titik sisip %s tidak ditemukan' % name)
    st = st.replace(UA_HELPER_ANCHOR, UA_HELPER + UA_HELPER_ANCHOR, 1).replace(RCB_OLD, RCB_NEW, 1)
    st = st.replace(LB_OLD, LB_NEW, 1)
    rt = rt.replace(DW_OLD, DW_NEW, 1)
    write(sp, st)
    write(rz, rt)
    print('89. buffer dari alamat tidak rata 4 byte dibaca benar (kedip objek jauh); BB_ORDER_UNALIGNED=0 = lama')

# --- 90. Kedip objek jauh: rekam draw 16 frame berturut-turut (17 Okt 20:15) ---
# Tes 20:05/20:09: tetap kedip dengan bagian 89, dan juga di 30 FPS. Buffer tidak rata ternyata
# semuanya buffer berformat 16-bit (+2 byte = rata untuk elemennya): bagian 89 tidak relevan ->
# bawaannya dimatikan (BB_ORDER_UNALIGNED=1 menyalakan). Diagnosa baru: BB_ORDER_DRAWLOG=<file pemicu>.
# Saat file itu dibuat, 16 frame berikutnya setiap draw dicatat ke <file pemicu>.txt: draw biasa
# (vs, ps, jumlah indeks/instance, alamat indeks) dan draw indirect (vs, ps, alamat argumen, isi
# argumen yang terlihat CPU, nilai count). Objek yang hilang-muncul = draw yang ada/tidak ada atau
# jumlah instance-nya berganti antar frame.
UA_OFF_OLD = """        const char* e = std::getenv("BB_ORDER_UNALIGNED");
        return !(e && e[0] == '0');"""
UA_OFF_NEW = """        const char* e = std::getenv("BB_ORDER_UNALIGNED"); // bbport-order (90): bawaan mati
        return e && e[0] == '1';"""
DL_HELPER_ANCHOR = "void Rasterizer::Draw(bool is_indexed, u32 index_offset, const PreparedDraw* prepared) {\n"
DL_HELPER = r"""// bbport-order (90): BB_ORDER_DRAWLOG=<file pemicu> -> 16 frame draw dicatat ke <pemicu>.txt
namespace {
struct BbDrawLog {
    std::mutex m;
    std::FILE* f = nullptr;
    u32 start = 0;
    u32 checked = ~0u;
};
BbDrawLog& BbDrawLogState() {
    static BbDrawLog d;
    return d;
}
/// Aktif? `rel` = frame ke berapa sejak pemicu.
bool BbDrawLogOn(u32& rel) {
    static const char* trig = std::getenv("BB_ORDER_DRAWLOG");
    if (trig == nullptr) {
        return false;
    }
    auto& d = BbDrawLogState();
    std::scoped_lock lk{d.m};
    const u32 frame = BbStats::frame_number.load(std::memory_order_relaxed);
    if (d.f == nullptr) {
        if (d.checked == frame) {
            return false;
        }
        d.checked = frame;
        std::FILE* t = std::fopen(trig, "r");
        if (t == nullptr) {
            return false;
        }
        std::fclose(t);
        std::remove(trig);
        d.f = std::fopen((std::string(trig) + ".txt").c_str(), "w");
        d.start = frame;
        std::printf("bbport-order (90): rekam draw 16 frame -> %s.txt\n", trig);
        if (d.f == nullptr) {
            return false;
        }
    }
    rel = frame - d.start;
    if (rel >= 16) {
        std::fclose(d.f);
        d.f = nullptr;
        std::printf("bbport-order (90): rekam draw selesai\n");
        return false;
    }
    return true;
}
void BbDrawLogWrite(const std::string& line) {
    auto& d = BbDrawLogState();
    std::scoped_lock lk{d.m};
    if (d.f != nullptr) {
        std::fputs(line.c_str(), d.f);
    }
}
} // namespace

"""
DLD_OLD = """    if (FrameCapture::Active()) {
        const auto* ps = pipeline->GetStages()[u32(Shader::SwStage::Fragment)];
        FrameCapture::Draw(vs_info.pgm_hash, ps ? ps->pgm_hash : 0, num_indices, num_instances);
"""
DLD_NEW = """    if (u32 bb_rel = 0; BbDrawLogOn(bb_rel)) { // bbport-order (90)
        BbDrawLogWrite(fmt::format("{} D vs {:08x} ps {:08x} idx {} inst {} first {}/{} ib {:#x} rt {:#x}\\n",
                                   bb_rel, vs_info.pgm_hash, ps_info ? ps_info->pgm_hash : 0,
                                   num_indices, num_instances, first_vertex, first_instance,
                                   is_indexed ? u64(regs.index_base_address.Address<VAddr>()) : 0,
                                   regs.color_buffers[0] ? regs.color_buffers[0].Address() : 0));
    }
""" + DLD_OLD
DLI_OLD = """    const bool bb_skip = BbOrderSkipLive(crumb.hash[0]) || BbOrderSkipLive(crumb.hash[1]); // bbport-order (44)
    scheduler.RecordCrumb(crumb, [=](vk::CommandBuffer cmdbuf) {
        if (bb_skip) {
            return;
        }
        cmdbuf.bindPipeline(vk::PipelineBindPoint::eGraphics, handle);
        if (is_indexed) {
            if (counts) {"""
DLI_NEW = """    if (u32 bb_rel = 0; BbDrawLogOn(bb_rel)) { // bbport-order (90)
        u32 a[5]{};
        std::memcpy(a, reinterpret_cast<const void*>(indirect.args), sizeof(a));
        u32 cnt = 0;
        if (count_address != 0) {
            std::memcpy(&cnt, reinterpret_cast<const void*>(count_address), 4);
        }
        BbDrawLogWrite(fmt::format("{} I vs {:08x} ps {:08x} args {:#x} max {} count@{:#x}={} cpu [{} {} {} {} {}] rt {:#x}\\n",
                                   bb_rel, crumb.hash[0], crumb.hash[1], indirect.args, max_count,
                                   count_address, cnt, a[0], a[1], a[2], a[3], a[4],
                                   Regs().color_buffers[0] ? Regs().color_buffers[0].Address() : 0));
    }
""" + DLI_OLD


def draw_log():
    sp = BBPORT / 'gpu' / 'shadps4' / 'shader_recompiler' / 'backend' / 'spirv' / 'emit_spirv_context_get_set.cpp'
    rz = BBPORT / 'gpu' / 'shadps4' / 'video_core' / 'renderer_vulkan' / 'vk_rasterizer.cpp'
    st, rt = read(sp), read(rz)
    if 'bbport-order (90)' in st and 'bbport-order (90)' in rt:
        print('90. rekam draw 16 frame (BB_ORDER_DRAWLOG): sudah dipatch')
        return
    if 'bbport-order (90)' not in st:
        if st.count(UA_OFF_OLD) != 1:
            sys.exit('bagian 90: saklar bagian 89 tidak ditemukan')
        st = st.replace(UA_OFF_OLD, UA_OFF_NEW, 1)
    if 'bbport-order (90)' not in rt:
        for name, old in (('helper', DL_HELPER_ANCHOR), ('draw', DLD_OLD), ('indirect', DLI_OLD)):
            if rt.count(old) != 1:
                sys.exit('bagian 90: titik sisip %s tidak ditemukan di vk_rasterizer.cpp' % name)
        rt = (rt.replace(DL_HELPER_ANCHOR, DL_HELPER + DL_HELPER_ANCHOR, 1)
              .replace(DLD_OLD, DLD_NEW, 1).replace(DLI_OLD, DLI_NEW, 1))
    write(sp, st)
    write(rz, rt)
    print('90. rekam draw 16 frame (BB_ORDER_DRAWLOG=file); bagian 89 bawaan mati')

# --- 91. Kedip objek jauh: rekaman draw + target depth, clear, scissor, viewport (17 Okt 20:30) ---
# Rekaman 20:18 (15 frame, kamera diam): semua draw warna sama tiap frame. Yang berganti hanya draw
# depth saja (ps kosong: vs 0b9de8df / f3da855e = shadow map), dan pass "clear" vs e5979e2b tetap
# 16 kali per frame. Dugaan: game membersihkan bagian shadow map (scissor/HTILE) lalu tidak
# menggambar ulang sebagian peta di frame itu; kalau port membersihkan SELURUH image, bayangan objek
# jauh hilang di frame itu -> kedip. Sekarang baris D juga mencatat alamat depth, clear (register dan
# HTILE), func/write depth, scissor generic/screen dan viewport.
DL91_OLD = """        BbDrawLogWrite(fmt::format("{} D vs {:08x} ps {:08x} idx {} inst {} first {}/{} ib {:#x} rt {:#x}\\n",
                                   bb_rel, vs_info.pgm_hash, ps_info ? ps_info->pgm_hash : 0,
                                   num_indices, num_instances, first_vertex, first_instance,
                                   is_indexed ? u64(regs.index_base_address.Address<VAddr>()) : 0,
                                   regs.color_buffers[0] ? regs.color_buffers[0].Address() : 0));"""
DL91_NEW = """        const auto& bb_vp = regs.viewports[0]; // bbport-order (91): depth/clear/scissor/viewport
        BbDrawLogWrite(fmt::format("{} D vs {:08x} ps {:08x} idx {} inst {} first {}/{} ib {:#x} rt {:#x}"
                                   " z {:#x} zclr {} htile {:#x} zf {} zw {} gs {},{}-{},{} ss {},{}-{},{}"
                                   " vp {:.0f},{:.0f} {:.0f}x{:.0f}\\n",
                                   bb_rel, vs_info.pgm_hash, ps_info ? ps_info->pgm_hash : 0,
                                   num_indices, num_instances, first_vertex, first_instance,
                                   is_indexed ? u64(regs.index_base_address.Address<VAddr>()) : 0,
                                   regs.color_buffers[0] ? regs.color_buffers[0].Address() : 0,
                                   regs.depth_buffer.DepthValid() ? u64(regs.depth_buffer.DepthAddress()) : 0,
                                   u32(regs.depth_render_control.depth_clear_enable),
                                   u64(regs.depth_htile_data_base.GetAddress()),
                                   u32(regs.depth_control.depth_func), u32(regs.depth_control.depth_write_enable),
                                   s32(regs.generic_scissor.top_left_x), s32(regs.generic_scissor.top_left_y),
                                   s32(regs.generic_scissor.bottom_right_x), s32(regs.generic_scissor.bottom_right_y),
                                   s32(regs.screen_scissor.top_left_x), s32(regs.screen_scissor.top_left_y),
                                   s32(regs.screen_scissor.bottom_right_x), s32(regs.screen_scissor.bottom_right_y),
                                   bb_vp.xoffset - bb_vp.xscale, bb_vp.yoffset - bb_vp.yscale,
                                   bb_vp.xscale * 2, bb_vp.yscale * 2));"""


def draw_log_depth():
    rz = BBPORT / 'gpu' / 'shadps4' / 'video_core' / 'renderer_vulkan' / 'vk_rasterizer.cpp'
    rt = read(rz)
    if 'bbport-order (91)' in rt:
        print('91. rekaman draw + depth/clear/scissor: sudah dipatch')
        return
    if rt.count(DL91_OLD) != 1:
        sys.exit('bagian 91: baris rekaman draw bagian 90 tidak ditemukan')
    write(rz, rt.replace(DL91_OLD, DL91_NEW, 1))
    print('91. rekaman draw (BB_ORDER_DRAWLOG) + target depth, clear, scissor, viewport')

# --- 92. Kedip bayangan objek jauh: uji clear depth lewat HTILE (17 Okt 20:35) ---
# Rekaman 20:24 (15 frame): setiap shadow map tetap di-"clear" dan digambar tiap frame, tetapi
# pass "clear" vs e5979e2b TIDAK menulis depth (func NEVER, write 0) dan register clear 0. Port
# membersihkan image karena metadata HTILE dianggap "cleared" (heuristik: compute yang menulis
# buffer HTILE tanpa XOR = clear seluruh surface, atau FillBuffer). Isi caster per frame juga
# berganti (gedung 12093 indeks: 1,0,1,0...). BB_ORDER_NO_METACLEAR=1 (percobaan): depth tidak
# dibersihkan dari status HTILE, hanya dari register clear.
MC_OLD = "            texture_cache.IsMetaCleared(htile_address, slice);\n"
MC_NEW = """            ([] { // bbport-order (92): BB_ORDER_NO_METACLEAR=1 -> abaikan status clear HTILE
                static const bool off = [] {
                    const char* e = std::getenv("BB_ORDER_NO_METACLEAR");
                    return e != nullptr && e[0] == '1';
                }();
                return off;
            }() ? false : texture_cache.IsMetaCleared(htile_address, slice));
"""


def no_meta_clear():
    rz = BBPORT / 'gpu' / 'shadps4' / 'video_core' / 'renderer_vulkan' / 'vk_rasterizer.cpp'
    rt = read(rz)
    if 'bbport-order (92)' in rt:
        print('92. BB_ORDER_NO_METACLEAR (uji clear depth HTILE): sudah dipatch')
        return
    if rt.count(MC_OLD) != 1:
        sys.exit('bagian 92: IsMetaCleared depth tidak ditemukan di vk_rasterizer.cpp')
    write(rz, rt.replace(MC_OLD, MC_NEW, 1))
    print('92. BB_ORDER_NO_METACLEAR=1: depth tidak dibersihkan dari status HTILE (percobaan)')

# --- 93. Kedip kereta/objek jauh = perbaikan bintik wajah: batasi ke vertex shader karakter (17 Okt 20:40) ---
# Tes 20:35: face fix mati -> kereta normal (bintik wajah kembali); face fix nyala -> kereta kedip.
# Bias 256 (bagian 72/76) dan EQUAL->LEQUAL berlaku untuk SEMUA draw tanpa tulis depth. Depth di sini
# standar (jauh = mendekati 1.0): satu ULP di kejauhan = jarak dunia yang besar, jadi permukaan di
# belakang (yang mestinya gagal tes EQUAL) ikut lolos, dan dengan jitter TAA bergantian tiap frame.
# Bintik wajah berasal dari dua vertex shader skinning yang berbeda (prepass vs pass warna). Sekarang
# bias dan EQUAL->LEQUAL hanya untuk draw yang vertex shader-nya di daftar shader skinning karakter.
# BB_ORDER_FACEFIX_VS=all -> semua draw (perilaku lama), atau daftar hash hex sendiri.
FV_HELPER_ANCHOR = "void Rasterizer::UpdateDynamicState(const GraphicsPipeline* pipeline, const bool is_indexed) const {\n"
FV_HELPER = r"""// bbport-order (93): vertex shader draw yang sedang disiapkan, untuk perbaikan bintik wajah.
static thread_local u64 bb_order_ff_vs = 0;
static bool BbOrderFaceFixVsOk() {
    struct List {
        u64 h[48]{};
        u32 n = 0;
        bool all = false;
    };
    static const List list = [] {
        List l;
        const char* e = std::getenv("BB_ORDER_FACEFIX_VS");
        if (e != nullptr && (e[0] == 'a' || e[0] == 'A')) {
            l.all = true;
        }
        const char* p = (e != nullptr && !l.all && e[0] != '\0')
                            ? e
                            : "1077f760,70b542d,e0ec7fe0,429d950d,bd739cf5,231d370b,"
                              "190852fd,b2cc4b8f,b938dd39,a369ab85,59c67371,fd7e121b,b68b212f";
        while (!l.all && *p && l.n < 48) {
            char* end = nullptr;
            const u64 v = std::strtoull(p, &end, 16);
            if (end == p) {
                break;
            }
            l.h[l.n++] = v;
            p = (*end == ',') ? end + 1 : end;
        }
        std::printf("bbport-order (93): face fix hanya untuk %s\n",
                    l.all ? "semua draw" : "vertex shader skinning karakter");
        std::fflush(stdout);
        return l;
    }();
    if (list.all) {
        return true;
    }
    for (u32 i = 0; i < list.n; ++i) {
        if (list.h[i] == bb_order_ff_vs) {
            return true;
        }
    }
    return false;
}

"""
FV_CALL_OLD = "    UpdateDepthStencilState();\n"
FV_CALL_NEW = ("    bb_order_ff_vs = pipeline ? pipeline->GetStage(Shader::SwStage::Vertex).pgm_hash : 0; // bbport-order (93)\n"
               + FV_CALL_OLD)
FV_CMP_OLD = "        if (BbOrderFaceFixMode() == 1 && bb_cmp == vk::CompareOp::eEqual && regs.color_buffers[0] &&\n"
FV_CMP_NEW = ("        if (BbOrderFaceFixMode() == 1 && bb_cmp == vk::CompareOp::eEqual && regs.color_buffers[0] &&\n"
              "            BbOrderFaceFixVsOk() && // bbport-order (93)\n")
FV_HIT_OLD = "                       : (bb_ff == 1 && !bb_ff_writes && regs.color_buffers[0]);\n"
FV_HIT_NEW = "                       : (bb_ff == 1 && !bb_ff_writes && regs.color_buffers[0] && BbOrderFaceFixVsOk()); // (93)\n"


def face_fix_vs_only():
    rz = BBPORT / 'gpu' / 'shadps4' / 'video_core' / 'renderer_vulkan' / 'vk_rasterizer.cpp'
    rt = read(rz)
    if 'bbport-order (93)' in rt:
        print('93. face fix hanya untuk vertex shader skinning karakter: sudah dipatch')
        return
    pairs = ((FV_HELPER_ANCHOR, FV_HELPER + FV_HELPER_ANCHOR), (FV_CALL_OLD, FV_CALL_NEW),
             (FV_CMP_OLD, FV_CMP_NEW), (FV_HIT_OLD, FV_HIT_NEW))
    for i, (old, _) in enumerate(pairs):
        if rt.count(old) != 1:
            sys.exit('bagian 93: titik sisip %d tidak ditemukan di vk_rasterizer.cpp' % i)
    for old, new in pairs:
        rt = rt.replace(old, new, 1)
    write(rz, rt)
    print('93. face fix (bias + EQUAL->LEQUAL) hanya untuk vertex shader skinning karakter (kedip kereta)')

# --- 94. Bintik wajah kembali dengan 93: batasi menurut PIXEL shader kulit f5c17eec (17 Okt 20:50) ---
# Tes 20:42: dengan daftar vertex shader (93) bintik wajah kembali -> wajah di adegan itu memakai
# vertex shader lain. Yang pasti: bintik = lubang di draw pixel shader kulit f5c17eec (bisection
# BB_ORDER_SKIP_PS, bagian 37). Rekaman alun-alun: pass warna gedung/kereta memakai vs 123dadc0,
# 7e01dddc, 86d3f798, 695da02b dengan ps lain. Sekarang perbaikan wajah berlaku untuk draw dengan
# PIXEL shader di daftar BB_ORDER_FACEFIX_PS (bawaan f5c17eec), ATAU vertex shader di
# BB_ORDER_FACEFIX_VS (bawaan kosong; all = semua draw, perilaku lama).
PS_SET_OLD = "    bb_order_ff_vs = pipeline ? pipeline->GetStage(Shader::SwStage::Vertex).pgm_hash : 0; // bbport-order (93)\n"
PS_SET_NEW = PS_SET_OLD + (
    "    { // bbport-order (94)\n"
    "        const auto* bb_ps = pipeline ? pipeline->GetStages()[u32(Shader::SwStage::Fragment)] : nullptr;\n"
    "        bb_order_ff_ps = bb_ps ? bb_ps->pgm_hash : 0;\n"
    "    }\n")
PS_VAR_OLD = "static thread_local u64 bb_order_ff_vs = 0;\n"
PS_VAR_NEW = PS_VAR_OLD + r"""static thread_local u64 bb_order_ff_ps = 0; // bbport-order (94)
static bool BbOrderFaceFixPsOk() {
    struct List {
        u64 h[32]{};
        u32 n = 0;
    };
    static const List list = [] {
        List l;
        const char* e = std::getenv("BB_ORDER_FACEFIX_PS");
        const char* p = (e != nullptr && e[0] != '\0') ? e : "f5c17eec";
        while (*p && l.n < 32) {
            char* end = nullptr;
            const u64 v = std::strtoull(p, &end, 16);
            if (end == p) {
                break;
            }
            l.h[l.n++] = v;
            p = (*end == ',') ? end + 1 : end;
        }
        std::printf("bbport-order (94): face fix untuk pixel shader %s\n", (e != nullptr && e[0] != '\0') ? e : "f5c17eec");
        std::fflush(stdout);
        return l;
    }();
    for (u32 i = 0; i < list.n; ++i) {
        if (list.h[i] == bb_order_ff_ps) {
            return true;
        }
    }
    return false;
}
"""
PS_CHK_OLD = "static bool BbOrderFaceFixVsOk() {\n"
PS_CHK_NEW = PS_CHK_OLD + "    if (BbOrderFaceFixPsOk()) { // bbport-order (94)\n        return true;\n    }\n"
PS_DEF_OLD = """        const char* p = (e != nullptr && !l.all && e[0] != '\\0')
                            ? e
                            : "1077f760,70b542d,e0ec7fe0,429d950d,bd739cf5,231d370b,"
                              "190852fd,b2cc4b8f,b938dd39,a369ab85,59c67371,fd7e121b,b68b212f";"""
PS_DEF_NEW = """        const char* p = (e != nullptr && !l.all && e[0] != '\\0') ? e : ""; // bbport-order (94): bawaan kosong"""
PS_MSG_OLD = """        std::printf("bbport-order (93): face fix hanya untuk %s\\n",
                    l.all ? "semua draw" : "vertex shader skinning karakter");"""
PS_MSG_NEW = """        std::printf("bbport-order (93): face fix vertex shader: %s\\n",
                    l.all ? "semua draw" : (l.n ? "daftar BB_ORDER_FACEFIX_VS" : "-"));"""


def face_fix_ps_only():
    rz = BBPORT / 'gpu' / 'shadps4' / 'video_core' / 'renderer_vulkan' / 'vk_rasterizer.cpp'
    rt = read(rz)
    if 'bbport-order (94)' in rt:
        print('94. face fix menurut pixel shader kulit f5c17eec: sudah dipatch')
        return
    pairs = ((PS_SET_OLD, PS_SET_NEW), (PS_VAR_OLD, PS_VAR_NEW), (PS_CHK_OLD, PS_CHK_NEW),
             (PS_DEF_OLD, PS_DEF_NEW), (PS_MSG_OLD, PS_MSG_NEW))
    for i, (old, _) in enumerate(pairs):
        if rt.count(old) != 1:
            sys.exit('bagian 94: titik sisip %d tidak ditemukan (bagian 93 belum terpasang?)' % i)
    for old, new in pairs:
        rt = rt.replace(old, new, 1)
    write(rz, rt)
    print('94. face fix hanya untuk pixel shader kulit (f5c17eec; BB_ORDER_FACEFIX_PS / _VS)')

# --- 95. Kedip kereta = EQUAL->LEQUAL dari perbaikan wajah, bukan bias (17 Okt 23:59) ---
# Tes 23:55 (file bias live): 16/32/64/128 sama saja; 23:58: bias 0 -> kereta TETAP kedip. Jadi
# penyebabnya penggantian tes depth EQUAL -> LEQUAL (71). Game memakai EQUAL sebagai saringan
# (hanya permukaan yang sama persis dengan prepass); LEQUAL meloloskan permukaan lain, dan dengan
# jitter TAA bergantian tiap frame. Sekarang: draw EQUAL dibiarkan EQUAL tanpa bias; bias hanya untuk
# draw tanpa tulis depth yang tes aslinya LESS/LEQUAL (pass kulit wajah memakai LEQUAL). Daftar
# shader 93/94 tidak dipakai lagi secara bawaan (semua draw). BB_ORDER_FACEFIX_EQUAL=1 = perilaku lama.
EQ_HELPER_OLD = "static thread_local u64 bb_order_ff_ps = 0; // bbport-order (94)\n"
EQ_HELPER_NEW = EQ_HELPER_OLD + r"""// bbport-order (95): EQUAL -> LEQUAL (+bias) hanya bila BB_ORDER_FACEFIX_EQUAL=1
static bool BbOrderFaceFixEqualOk() {
    static const bool on = [] {
        const char* e = std::getenv("BB_ORDER_FACEFIX_EQUAL");
        const bool v = e != nullptr && e[0] == '1';
        std::printf("bbport-order (95): face fix untuk draw EQUAL: %s\n", v ? "ya (lama)" : "tidak");
        std::fflush(stdout);
        return v;
    }();
    return on;
}
"""
EQ_CMP_OLD = "            BbOrderFaceFixVsOk() && // bbport-order (93)\n"
EQ_CMP_NEW = "            BbOrderFaceFixVsOk() && BbOrderFaceFixEqualOk() && // bbport-order (93/95)\n"
EQ_HIT_OLD = "                       : (bb_ff == 1 && !bb_ff_writes && regs.color_buffers[0] && BbOrderFaceFixVsOk()); // (93)\n"
EQ_HIT_NEW = ("                       : (bb_ff == 1 && !bb_ff_writes && regs.color_buffers[0] && BbOrderFaceFixVsOk() &&\n"
              "                          (regs.depth_control.depth_func != AmdGpu::CompareFunc::Equal ||\n"
              "                           BbOrderFaceFixEqualOk())); // (93/95)\n")
EQ_ALL_OLD = "        if (e != nullptr && (e[0] == 'a' || e[0] == 'A')) {\n            l.all = true;\n        }\n"
EQ_ALL_NEW = ("        if (e == nullptr || e[0] == '\\0' || e[0] == 'a' || e[0] == 'A') { // bbport-order (95): bawaan semua\n"
              "            l.all = true;\n        }\n")


def face_fix_no_equal():
    rz = BBPORT / 'gpu' / 'shadps4' / 'video_core' / 'renderer_vulkan' / 'vk_rasterizer.cpp'
    rt = read(rz)
    if 'bbport-order (95)' in rt:
        print('95. face fix tidak mengubah draw EQUAL: sudah dipatch')
        return
    pairs = ((EQ_HELPER_OLD, EQ_HELPER_NEW), (EQ_CMP_OLD, EQ_CMP_NEW), (EQ_HIT_OLD, EQ_HIT_NEW),
             (EQ_ALL_OLD, EQ_ALL_NEW))
    for i, (old, _) in enumerate(pairs):
        if rt.count(old) != 1:
            sys.exit('bagian 95: titik sisip %d tidak ditemukan (bagian 93/94 belum terpasang?)' % i)
    for old, new in pairs:
        rt = rt.replace(old, new, 1)
    write(rz, rt)
    print('95. face fix: draw EQUAL dibiarkan (kedip kereta); bias untuk LESS/LEQUAL tanpa tulis, semua draw')

# --- 96. Crash 2K/4K tanpa 16:9: dump register + stack juga untuk kode hasil generate (18 Okt 00:40) ---
# 2K/4K tanpa patch 16:9 (bar hitam asli 2.4:1): crash di thread shadPS4:GpuComm, RIP di mapping
# anonim rwx 32 MB (bukan image game, bukan .so) -> kemungkinan kode yang dibuat driver NVIDIA saat
# dipanggil port. Tanpa --views/--fix800 tetap crash. Handler hanya mencetak "#2 <alamat>". Sekarang:
# register dan 48 isi stack teratas juga dicetak, dengan nama library+offset (dladdr) -> fungsi port
# yang memanggil driver kelihatan.
PF_COND_OLD = "    if (rip - (uintptr_t)image < 0x10000000) {\n        static const struct { const char *name; int reg; } regs[] = {\n"
PF_COND_NEW = ("    Dl_info bb_rip_where; /* bbport-order (96): juga untuk kode generate (bukan image, bukan .so) */\n"
               "    if (rip - (uintptr_t)image < 0x10000000 ||\n"
               "        !(dladdr((void *)rip, &bb_rip_where) && bb_rip_where.dli_fname)) {\n"
               "        static const struct { const char *name; int reg; } regs[] = {\n")
PF_STACK_OLD = """        for (int i = 0; i < 24; i++) {
            const uintptr_t v = sp[i];
            if (v - (uintptr_t)image < 0x10000000)
                snprintf(line, sizeof(line), "  [rsp+0x%02x] = 0x%016lx  (guest offset 0x%lx)\\n", i * 8,
                         (unsigned long)v, (unsigned long)(v - (uintptr_t)image));
            else
                snprintf(line, sizeof(line), "  [rsp+0x%02x] = 0x%016lx\\n", i * 8, (unsigned long)v);"""
PF_STACK_NEW = """        for (int i = 0; i < 48; i++) { /* bbport-order (96): 48 entri + nama library */
            const uintptr_t v = sp[i];
            Dl_info bb_sw;
            if (v - (uintptr_t)image < 0x10000000)
                snprintf(line, sizeof(line), "  [rsp+0x%02x] = 0x%016lx  (guest offset 0x%lx)\\n", i * 8,
                         (unsigned long)v, (unsigned long)(v - (uintptr_t)image));
            else if (v > 0x10000 && dladdr((void *)v, &bb_sw) && bb_sw.dli_fname)
                snprintf(line, sizeof(line), "  [rsp+0x%02x] = 0x%016lx  %s+0x%lx (%s)\\n", i * 8, (unsigned long)v,
                         bb_sw.dli_fname, (unsigned long)(v - (uintptr_t)bb_sw.dli_fbase),
                         bb_sw.dli_sname ? bb_sw.dli_sname : "?");
            else
                snprintf(line, sizeof(line), "  [rsp+0x%02x] = 0x%016lx\\n", i * 8, (unsigned long)v);"""


def fault_dump_generated():
    path = BBPORT / 'src' / 'probe.c'
    text = read(path)
    if 'bbport-order (96)' in text:
        print('96. dump register/stack untuk crash di kode generate: sudah dipatch')
        return
    for i, old in enumerate((PF_COND_OLD, PF_STACK_OLD)):
        if text.count(old) != 1:
            sys.exit('bagian 96: titik sisip %d tidak ditemukan di src/probe.c' % i)
    write(path, text.replace(PF_COND_OLD, PF_COND_NEW, 1).replace(PF_STACK_OLD, PF_STACK_NEW, 1))
    print('96. crash di kode generate (driver) mencetak register + stack dengan nama library')

# --- 97. Crash 2K/4K tanpa 16:9: SRT walker membaca pointer sampah -> tahan fault (18 Okt 00:45) ---
# Dump bagian 96: crash di kode Xbyak "SRT walker" (RefreshFlatBuf, dipanggil dari
# PipelineCache::GetProgram) untuk vertex shader 0x170474b8: rdi = 0x500000000000 (pointer di user
# data yang tidak valid; di 2K/4K dengan bar hitam 2.4:1 game mengisi tabel itu lain). GPU PS4 hanya
# membaca bila memang dipakai; walker port membaca semuanya lebih dulu. Sekarang pembacaan walker
# memakai titik pulih runtime_fault_recover (seperti worker draw-prep): bila pointer tidak bisa
# dibaca, bagian yang diratakan diisi 0 dan draw berjalan terus (dicatat 20 kali pertama).
FB97_OLD = """        if (srt_info.walker_func) {
            srt_info.walker_func(user_data.data(), flattened_ud_buf.data());
        }
    }
"""
FB97_NEW = """        if (srt_info.walker_func) {
            if (runtime_fault_recover != nullptr) { // sudah di dalam titik pulih (worker)
                srt_info.walker_func(user_data.data(), flattened_ud_buf.data());
                return;
            }
            sigjmp_buf bb_recover; // bbport-order (97): pointer sampah di user data -> 0, bukan crash
            if (sigsetjmp(bb_recover, 0) == 0) {
                runtime_fault_recover = &bb_recover;
                srt_info.walker_func(user_data.data(), flattened_ud_buf.data());
                runtime_fault_recover = nullptr;
            } else {
                runtime_fault_recover = nullptr;
                std::fill(flattened_ud_buf.begin() + user_data.size(), flattened_ud_buf.end(), 0u);
                static std::atomic<u32> bb_told{0};
                if (bb_told.fetch_add(1) < 20) {
                    std::printf("bbport-order (97): SRT walker shader %llx membaca pointer tidak valid -> 0\\n",
                                (unsigned long long)pgm_hash);
                    std::fflush(stdout);
                }
            }
        }
    }
"""
FB97_INC_OLD = "#include <span>\n"
FB97_INC_NEW = ("#include <span>\n#include <algorithm> // bbport-order (97)\n#include <atomic>\n#include <cstdio>\n#include <setjmp.h>\n"
                "extern \"C\" __thread sigjmp_buf* runtime_fault_recover;\n")


def srt_walker_safe():
    path = BBPORT / 'gpu' / 'shadps4' / 'shader_recompiler' / 'info.h'
    text = read(path)
    if 'bbport-order (97)' in text:
        print('97. SRT walker tahan pointer sampah: sudah dipatch')
        return
    for i, old in enumerate((FB97_OLD, FB97_INC_OLD)):
        if text.count(old) != 1:
            sys.exit('bagian 97: titik sisip %d tidak ditemukan di info.h' % i)
    write(path, text.replace(FB97_OLD, FB97_NEW, 1).replace(FB97_INC_OLD, FB97_INC_NEW, 1))
    print('97. SRT walker: pointer tidak valid di user data -> 0 (crash 2K/4K tanpa 16:9)')

# --- 98. 2K/4K tanpa 16:9: shader sampah -> draw dilewati, bukan STOP (18 Okt 00:50) ---
# Sesudah 97: walker selamat (shader a6e55bd3), lalu "control_flow_graph.cpp:320 Assertion Failed"
# saat menerjemahkan shader berikutnya (kode program dari alamat sampah: cabang ke luar program).
# Assertion port = keluar (exit 23). Sekarang selama pemilihan pipeline (stage grafis dan compute)
# assertion dilempar sebagai exception; draw/dispatch itu dilewati dan dicatat (20 kali pertama).
AS98_OLD = "void assert_fail_impl() {\n    if (&runtime_restarting && runtime_restarting) {\n"
AS98_NEW = ("// bbport-order (98): >0 selama pemilihan pipeline -> assertion jadi exception (draw dilewati)\n"
            "static thread_local int bb_order_assert_throw = 0;\n"
            "extern \"C\" int* BbOrderAssertThrow() {\n    return &bb_order_assert_throw;\n}\n\n"
            "void assert_fail_impl() {\n"
            "    if (bb_order_assert_throw > 0) {\n"
            "        throw std::runtime_error(\"bbport-order (98): assertion saat pemilihan pipeline\");\n"
            "    }\n"
            "    if (&runtime_restarting && runtime_restarting) {\n")
PC98_HELPER_ANCHOR = "bool PipelineCache::RefreshGraphicsKey(PipelineSelection& sel) {\n"
PC98_HELPER = r"""// bbport-order (98): assertion -> exception selama pemilihan pipeline (shim/common/assert.cpp)
extern "C" int* BbOrderAssertThrow();
static void BbOrderBadShader(const char* what, u64 hash) {
    static std::atomic<u32> told{0};
    if (told.fetch_add(1) < 20) {
        std::printf("bbport-order (98): shader %llx gagal (%s) -> draw/dispatch dilewati\n",
                    (unsigned long long)hash, what);
        std::fflush(stdout);
    }
}

"""
PC98_GFX_OLD = "    if (!RefreshGraphicsStages(sel)) {\n"
PC98_GFX_NEW = """    bool bb_stages_ok = false; // bbport-order (98)
    ++*BbOrderAssertThrow();
    try {
        bb_stages_ok = RefreshGraphicsStages(sel);
    } catch (const std::exception& e) {
        const auto* bb_ps = sel.regs ? sel.regs->ProgramForStage(u32(HwStage::Fragment)) : nullptr;
        BbOrderBadShader(e.what(), bb_ps && bb_ps->Address<u32*>() ? AmdGpu::GetParams(*bb_ps).hash : 0);
        bb_stages_ok = false;
    }
    --*BbOrderAssertThrow();
    if (!bb_stages_ok) {
"""
PC98_CS_OLD = """    std::tie(sel.infos[0], sel.modules[0], sel.fetch_shader, compute_key.value) =
        GetProgram(sel, HwStage::Compute, SwStage::Compute, cs_params, binding);
    return true;
}
"""
PC98_CS_NEW = """    ++*BbOrderAssertThrow(); // bbport-order (98)
    try {
        std::tie(sel.infos[0], sel.modules[0], sel.fetch_shader, compute_key.value) =
            GetProgram(sel, HwStage::Compute, SwStage::Compute, cs_params, binding);
    } catch (const std::exception& e) {
        --*BbOrderAssertThrow();
        BbOrderBadShader(e.what(), cs_params.hash);
        return false;
    }
    --*BbOrderAssertThrow();
    return true;
}
"""


PC98_INC_OLD = "#include <atomic>\n"
PC98_INC_NEW = "#include <atomic>\n#include <exception> // bbport-order (98)\n"


def bad_shader_skip():
    asp = BBPORT / 'gpu' / 'shim' / 'common' / 'assert.cpp'
    pcp = BBPORT / 'gpu' / 'shadps4' / 'video_core' / 'renderer_vulkan' / 'vk_pipeline_cache.cpp'
    at, pt = read(asp), read(pcp)
    if 'bbport-order (98)' in at and 'bbport-order (98)' in pt:
        print('98. shader sampah -> draw dilewati: sudah dipatch')
        return
    if at.count(AS98_OLD) != 1:
        sys.exit('bagian 98: assert_fail_impl tidak ditemukan di shim/common/assert.cpp')
    for i, old in enumerate((PC98_HELPER_ANCHOR, PC98_GFX_OLD, PC98_CS_OLD, PC98_INC_OLD)):
        if pt.count(old) != 1:
            sys.exit('bagian 98: titik sisip %d tidak ditemukan di vk_pipeline_cache.cpp' % i)
    write(asp, at.replace(AS98_OLD, AS98_NEW, 1))
    write(pcp, pt.replace(PC98_HELPER_ANCHOR, PC98_HELPER + PC98_HELPER_ANCHOR, 1)
              .replace(PC98_GFX_OLD, PC98_GFX_NEW, 1).replace(PC98_CS_OLD, PC98_CS_NEW, 1)
              .replace(PC98_INC_OLD, PC98_INC_NEW, 1))
    print('98. assertion saat pemilihan pipeline -> draw/dispatch dilewati (2K/4K tanpa 16:9)')


# --- 99. Build gagal sesudah 98: helper ditaruh sesudah pemakaiannya (18 Okt 00:58) ---
# vk_pipeline_cache.cpp: 'BbOrderAssertThrow' / 'BbOrderBadShader' was not declared in
# RefreshGraphicsKey (helper 98 berada sebelum RefreshGraphicsStages, sesudah RefreshGraphicsKey).
# Helper dipindah ke sebelum RefreshGraphicsKey.
MV99_KEY = "bool PipelineCache::RefreshGraphicsKey(PipelineSelection& sel) {\n"


def bad_shader_helper_order():
    pcp = BBPORT / 'gpu' / 'shadps4' / 'video_core' / 'renderer_vulkan' / 'vk_pipeline_cache.cpp'
    pt = read(pcp)
    if pt.count(PC98_HELPER) != 1 or pt.count(MV99_KEY) != 1:
        sys.exit('bagian 99: helper bagian 98 atau RefreshGraphicsKey tidak ditemukan')
    if pt.index(PC98_HELPER) < pt.index(MV99_KEY):
        print('99. helper bagian 98 sudah sebelum RefreshGraphicsKey')
        return
    pt = pt.replace(PC98_HELPER, '', 1).replace(MV99_KEY, PC98_HELPER + MV99_KEY, 1)
    write(pcp, pt)
    print('99. helper bagian 98 dipindah ke sebelum RefreshGraphicsKey (build error)')

if __name__ == '__main__':
    import_names()
    runtime_kernel()
    runtime_memory()
    runtime_pad()
    fmask_formats()
    surface_fallback()
    tile_mode_check()
    swizzle_fallback()
    image_size_check()
    srt_trivial_phi()
    srt_zero_fill()
    save_diagnostics()
    permutation_log()
    image_guard2()
    big_buffer_guard()
    save_progress_dialog()
    loose_permutations()
    skip_compute()
    flat2d_shader()
    search_binary_info()
    image_size_256()
    giant_image_log()
    shader_list()
    perm_log_cap()
    flat_integer()
    image_size_pitch()
    guest_size_guard()
    legacy_math()
    phi_initial_value()
    wide_reject_log()
    rt_no_refresh()
    rt_ignore_cpu()
    rt_ignore_gpubuf()
    rt_depth_too()
    rt_small_too()
    srt_fail_hash()
    skip_pixel_shader()
    lane_zero()
    srt_two_pass()
    fp_clamp()
    nan_fix()
    alias_log()
    null_tex()
    alpha_to_coverage()
    skip_live()
    nan_debug()
    store_nan()
    invariant_position()
    depth_equal()
    no_msaa()
    ds_flags()
    bary_fix()
    diag_dump()
    clip_emu()
    exec_scope()
    no_discard()
    ds_all()
    ds_mrt()
    depth_bias_test()
    face_fix()
    face_bias_live()
    waterfall_lane()
    vb_diag()
    flat_log()
    zclear()
    bone_race()
    full_barrier()
    flip_rate()
    exact_vs()
    diag_depth()
    vertex_race()
    face_fix_nowrite()
    face_bias_default()
    record_data_big()
    task_kernel_yield()
    order_taa_hook()
    face_bias_no_slope()
    diag_ps()
    refresh_small()
    gpu_write_inside()
    mem_hash()
    gpu_write_inside_off()
    overlay_menu_off()
    number_conversion_safe()
    loose_539()
    compile_timing()
    async_reason()
    key_diff()
    async_indirect()
    unaligned_buffers()
    draw_log()
    draw_log_depth()
    no_meta_clear()
    face_fix_vs_only()
    face_fix_ps_only()
    face_fix_no_equal()
    fault_dump_generated()
    srt_walker_safe()
    bad_shader_skip()
    bad_shader_helper_order()
    print('Selesai. Build ulang bbport, lalu jalankan order-port.sh (tanpa --prepare).')
