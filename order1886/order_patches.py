#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""The Order: 1886 (CUSA00035, eboot 01.02): patch FPS/resolusi -> out/patches.bin (format BBPATCH2
bbport, dibaca bb-probe --patches). Isi patch dari repo komunitas GoldHEN/shadPS4
(illusion0001/PS4-PS5-Game-Patch, patches/xml/TheOrder1886-Orbis.xml):

  60 FPS Unlock     0x8507c4: movl $2 -> $1 (interval vsync 2 -> 1). Catatan komunitas: SOFTLOCK di
                    Quick Time Event Chapter 6 dan 9 -> main bagian itu dengan ORDER_FPS=30.
  Resolution Patch  0x84cef5 je -> jne, lalu lebar/tinggi di 0x84cefd/0x84cf07. Komunitas memakai
                    1600x900 dan 1280x720; game sendiri punya cabang 3840x2160 (0xf00 x 0x870) dan
                    1920x1080, jadi nilai lain (mis. 4K) memakai jalur yang sama.
  -use4K (use4k)    Opsi developer bawaan game ("-use4K", diparse dari argumen) menyalakan flag 0x200
                    di 0x7dc(r13) -> cabang 3840x2160 asli game. 0x846ab9 jbe -> jmp ke `or $0x200`
                    (pencarian opsi dilewati, flag selalu menyala). Percobaan: jalur developer.
  16:9 Aspect Ratio 0x84ce8c float 2.4 -> 1.777 (layar penuh tanpa bar hitam; catatan komunitas:
                    di 1080p ke atas ada gangguan visual).

Tambahan kita (bukan dari repo komunitas):
  GpuStack (heap)   Heap "GpuStack" (tempat render target) dialokasikan tetap 654 MB (0x28e00000):
                    0x698d0b AllocateDirectMemory, 0x698d33 MapDirectMemory, 0x698d63 ukuran yang
                    disimpan di objek heap (= batas allocator) dan 0x6997cc pelepasan saat keluar.
                    Di atas 1080p render target tidak muat -> saling menimpa (texture rusak, layar
                    putih). Keempat angka harus diganti BERSAMA: kalau hanya alokasinya yang dibesarkan,
                    allocator tetap berhenti di 654 MB. Maksimum 2046 MB (imm32 bertanda di 0x698d63).
  Gpu (heap)        Heap "Gpu" 24 MB (0x1800000): alokasi 0x6989fd, map 0x698a25, ukuran tersimpan
                    0x698a78, pembuatan allocator 0x698a9c / 0x698aba, pelepasan 0x699854. Ikut
                    dibesarkan sebanding piksel (percobaan kedipan pink di 1440p, 16 Okt 13:20).
                    HASIL: 1440p + Gpu 44 MB = layar hitam, game tidak jalan -> bawaan MATI (off).

  Buffer 1920x800    0xc39c54 mov edi,0x780 / 0xc39c59 mov esi,0x320: satu buffer dibuat tetap 1920x800
                    (= 1920 / 2.4), padahal render target utama memakai LEBAR x LEBAR/2.4 (4K: 3840x1600).
                    Patch resolusi komunitas tidak mengubahnya; di 1080p kebetulan cocok. Tersangka pita
                    pink 1440p/4K (16 Okt 13:55). Ikut diskalakan bila lebar != 1920 (--fix800 off: mati).
  Ring konstanta    Ring per-frame untuk data yang ditulis CPU (konstanta shader; objek global di
                    0x1b0e020, init 0xc78730, tabel 0x19f9540: 2 x 2 MB, heap indeks 8 = GpuStack).
                    Di atas 1080p render target GpuStack menutupi ring ini (1440p: target tonemap,
                    4K: dua target HDR -> gambar gelap dan goyang). --ring-heap 3 memindahkan ring ke
                    heap indeks 3 (52 MB, prot 0x33, CPU+GPU) di 0x19f954c / 0x19f9564. Percobaan.
                    Ring 3 dengan heap 3 asli: crash 'Task Kernel' di awal (alokasi gagal, null).
  Heap 3 (52 MB)    0x3400000 di 0x698f06 alokasi, 0x698f2b map, 0x698f79 ukuran tersimpan, 0x698f8b
                    pembuatan allocator, 0x699785 pelepasan. --heap3 auto: 2 x 52 = 104 MB bila ring 3
                    atau command buffer 3.
  Command buffer    2 x 20 MB (0x1400000) di 0xc39e36 / 0xc39e66: mov rdi,[rax+0x40] = heap indeks 8
                    (GpuStack). Konstanta yang ditulis CPU (+0xcc8791 dll., 1440p di 373,7 MB) ada di sini
                    dan tertutup render target di atas 1080p. --cmdbuf-heap 3 -> [rax+0x18] (heap 3).
                    HASIL 4K: tetap goyang, tulisan CPU tidak pindah -> bukan di command buffer.
  Buffer konstanta  0xc6efe7 (0xa0000, 640 KB) dan 0xc6f13b (0x138800, 1,25 MB) dari heap 8, dibuat
                    0xc6efd0 tepat sesudah ring (tulisan CPU bergeser +8 MB saat ring kembali ke heap 8).
                    --cbuf-heap 3. Semua sekaligus: --cpu-heap 3 (ring + command buffer + konstanta).
                    HASIL 4K: tetap goyang (tulisan CPU hanya bergeser -1,9 MB, tetap di GpuStack).
  Ukuran view       Tiga konstruktor pengaturan view mengisi 1920x1080 tetap (+ rasio 2.4):
                    0xc96b41/0xc96b4b, 0xc9f861/0xc9f868, 0xca0db1/0xca0dbb. Patch resolusi komunitas
                    tidak mengubahnya. Bila dipakai untuk jitter TAA (1/lebar piksel), 4K = jitter 2x
                    terlalu besar -> gambar goyang. --views on: ikut diganti ke LEBARxTINGGI.

  Spin job system   0xca738c: callback idle worker 'Task Kernel' (0x8a7380) baru yield sesudah 0x709
                    (1801) percobaan ambil job yang gagal. --spin N mengecilkan ambang (dipakai bersama
                    BB_ORDER_YIELD_US, order_patch.py bagian 74: yield worker = tidur). Bawaan: asli.

Setiap alamat dicek dulu terhadap byte asli eboot 01.02, supaya versi lain tidak ikut ditambal.

Pemakaian: python3 order_patches.py OUT_DIR --fps 60 --res 3840x2160 [--aspect169] [--gpustack auto|MB]
--gpustack auto (bawaan): 654 MB sampai 1080p; di atasnya naik sebanding jumlah piksel, maks 2046 MB.
--gpuheap off (bawaan, 24 MB asli) | auto | MB. auto/MB = percobaan: 1440p + 44 MB -> layar hitam.
Tanpa patch apa pun file patches.bin dihapus (game asli).
"""
import argparse
import struct
import sys
from pathlib import Path

EBOOT_BASE = 0x400000
GPUSTACK_MB = 654                      # 0x28e00000
GPUSTACK_MAX_MB = 2046                 # 0x7fe00000: masih positif sebagai imm32 bertanda
GPUSTACK_SITES = (0x698d0c, 0x698d34, 0x698d6a, 0x6997cd)
GPUHEAP_MB = 24                        # 0x1800000
GPUHEAP_SITES = (0x6989fe, 0x698a26, 0x698a7f, 0x698a9d, 0x698abb, 0x699855)

# alamat: (byte asli eboot 01.02, keterangan)
ORIGINAL = {
    0x8507c4: (bytes([0x02]), 'interval vsync'),
    0x84cef5: (bytes([0x74]), 'cabang resolusi (je)'),
    0x84cefd: ((0x500).to_bytes(4, 'little'), 'lebar render'),
    0x84cf07: ((0x2d0).to_bytes(4, 'little'), 'tinggi render'),
    0x84ce8c: (struct.pack('<f', 2.4000000953674316), 'rasio aspek'),
    0x846ab9: (bytes([0x76, 0x3a]), 'pencarian opsi -use4K'),
}
for _site in GPUSTACK_SITES:
    ORIGINAL[_site] = ((GPUSTACK_MB << 20).to_bytes(4, 'little'), 'ukuran heap GpuStack')
BUF800_W, BUF800_H = 0xc39c55, 0xc39c5a
ORIGINAL[BUF800_W] = ((0x780).to_bytes(4, 'little'), 'lebar buffer 1920x800')
ORIGINAL[BUF800_H] = ((0x320).to_bytes(4, 'little'), 'tinggi buffer 1920x800')
RING_HEAP_SITES = (0x19f954c, 0x19f9564)
CMDBUF_SITES = (0xc39e39, 0xc39e69)     # disp8 [rax+0x40] = indeks heap * 8
for _site in CMDBUF_SITES:
    ORIGINAL[_site] = (bytes([0x40]), 'heap command buffer')
VIEW_SITES = ((0xc96b47, 0xc96b51), (0xc9f864, 0xc9f86b), (0xca0db7, 0xca0dc1))
for _w, _h in VIEW_SITES:
    ORIGINAL[_w] = ((0x780).to_bytes(4, 'little'), 'lebar view 1920')
    ORIGINAL[_h] = ((0x438).to_bytes(4, 'little'), 'tinggi view 1080')
CBUF_SITES = (0xc6efea, 0xc6f13e)
for _site in CBUF_SITES:
    ORIGINAL[_site] = (bytes([0x40]), 'heap buffer konstanta')
HEAP3_MB = 52                          # 0x3400000
HEAP3_SITES = (0x698f07, 0x698f2c, 0x698f80, 0x698f8c, 0x699786)
for _site in HEAP3_SITES:
    ORIGINAL[_site] = ((HEAP3_MB << 20).to_bytes(4, 'little'), 'ukuran heap 3')
for _site in RING_HEAP_SITES:
    ORIGINAL[_site] = ((8).to_bytes(4, 'little'), 'heap ring konstanta')
SPIN_SITE = 0xca738c                   # cmpq $0x709,(%rbx) di 0x8a7389 (imm32)
ORIGINAL[SPIN_SITE] = ((0x709).to_bytes(4, 'little'), 'ambang spin job system')
for _site in GPUHEAP_SITES:
    ORIGINAL[_site] = ((GPUHEAP_MB << 20).to_bytes(4, 'little'), 'ukuran heap Gpu')


def segments(elf):
    phoff, = struct.unpack_from('<Q', elf, 0x20)
    phentsize, phnum = struct.unpack_from('<HH', elf, 0x36)
    out = []
    for i in range(phnum):
        kind, _, off, vaddr, _, filesz, memsz, _ = struct.unpack_from('<IIQQQQQQ', elf, phoff + i * phentsize)
        if kind == 1:
            out.append((off, vaddr, filesz, memsz))
    return out


def read_at(elf, segs, addr, n):
    v = addr - EBOOT_BASE
    for off, vaddr, filesz, _ in segs:
        if vaddr <= v and v + n <= vaddr + filesz:
            return elf[off + v - vaddr:off + v - vaddr + n]
    sys.exit(f'alamat {addr:#x} di luar eboot')


def render_size(res):
    """Ukuran render (lebar, tinggi) untuk pilihan --res, atau None untuk resolusi asli."""
    if res == 'native':
        return None
    if res == 'use4k':
        return 3840, 2160
    try:
        w, h = (int(v) for v in res.lower().split('x'))
    except ValueError:
        sys.exit(f'--res {res!r}: pakai native, use4k atau LEBARxTINGGI')
    if not (320 <= w <= 7680 and 180 <= h <= 4320 and w % 2 == 0 and h % 2 == 0):
        sys.exit(f'--res {res}: ukuran tidak masuk akal')
    return w, h


def heap_mb(choice, size, base, name):
    """Ukuran heap (MB): angka dari pengguna, atau auto = sebanding piksel di atas 1080p."""
    if choice != 'auto':
        try:
            mb = int(choice)
        except ValueError:
            sys.exit(f'--{name} {choice!r}: pakai auto atau angka MB')
    elif size is None or size[0] * size[1] <= 1920 * 1080:
        mb = base
    else:
        mb = -(-base * size[0] * size[1] // (1920 * 1080))
    mb = min(GPUSTACK_MAX_MB, max(base, int(mb)))
    return (mb + 1) // 2 * 2          # kelipatan 2 MB (perataan alokasi 0x200000)


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('out', type=Path, help='folder out (berisi eboot.elf)')
    p.add_argument('--fps', choices=['30', '60'], default='30')
    p.add_argument('--res', default='native',
                   help='native, use4k (opsi developer -use4K) atau LEBARxTINGGI (mis. 2560x1440, 1600x900)')
    p.add_argument('--aspect169', action='store_true', help='16:9 layar penuh (tanpa bar hitam)')
    p.add_argument('--gpustack', default='auto',
                   help=f'ukuran heap GpuStack dalam MB: auto (bawaan) atau {GPUSTACK_MB}..{GPUSTACK_MAX_MB}')
    p.add_argument('--fix800', choices=['on', 'off'], default='on',
                   help='buffer 1920x800 ikut diskalakan ke LEBAR x LEBAR/2.4 (bawaan on)')
    p.add_argument('--ring-heap', type=int, default=8, choices=range(0, 9), metavar='0..8',
                   help='heap untuk ring konstanta per-frame (8 = asli GpuStack; 3 = heap CPU+GPU 52 MB)')
    p.add_argument('--cmdbuf-heap', type=int, default=8, choices=range(0, 9), metavar='0..8',
                   help='heap untuk 2 x 20 MB command buffer (8 = asli GpuStack; 3 = heap CPU+GPU)')
    p.add_argument('--views', choices=['on', 'off'], default='on',
                   help='ukuran view bawaan 1920x1080 ikut diganti ke resolusi render (bawaan on)')
    p.add_argument('--cbuf-heap', type=int, default=8, choices=range(0, 9), metavar='0..8',
                   help='heap untuk buffer konstanta 0xc6efe7/0xc6f13b (8 = asli GpuStack)')
    p.add_argument('--cpu-heap', type=int, default=None, choices=range(0, 9), metavar='0..8',
                   help='pindahkan ring, command buffer dan buffer konstanta sekaligus ke heap ini')
    p.add_argument('--heap3', default='auto',
                   help='ukuran heap 3 dalam MB: auto (104 bila --ring-heap 3, selain itu asli), off, atau MB')
    p.add_argument('--gpuheap', default='off',
                   help=f'ukuran heap Gpu dalam MB: off (bawaan), auto, atau {GPUHEAP_MB}..{GPUSTACK_MAX_MB}')
    p.add_argument('--spin', default='off',
                   help='ambang percobaan job sebelum worker yield: off (asli 1801) atau angka 1..1801')
    a = p.parse_args()

    if a.cpu_heap is not None:
        a.ring_heap = a.cmdbuf_heap = a.cbuf_heap = a.cpu_heap
    elf = (a.out / 'eboot.elf').read_bytes()
    segs = segments(elf)
    for addr, (orig, what) in ORIGINAL.items():
        if read_at(elf, segs, addr, len(orig)) != orig:
            sys.exit(f'eboot bukan versi 01.02 yang dikenal ({what} di {addr:#x} berbeda): patch dibatalkan')

    writes, names = [], []
    if a.fps == '60':
        writes.append((0x8507c4, bytes([0x01])))
        names.append('60 FPS Unlock')
    size = render_size(a.res)
    if a.res == 'use4k':
        writes.append((0x846ab9, bytes([0xeb, 0x2c])))
        names.append('Opsi developer -use4K')
    elif size is not None:
        w, h = size
        writes += [(0x84cef5, bytes([0x75])), (0x84cefd, w.to_bytes(4, 'little')),
                   (0x84cf07, h.to_bytes(4, 'little'))]
        names.append(f'Resolusi {w}x{h}')
    if a.fix800 == 'on' and size is not None and size[0] != 1920:
        bw = size[0]
        bh = int(round(bw / 2.4)) & ~1
        writes += [(BUF800_W, bw.to_bytes(4, 'little')), (BUF800_H, bh.to_bytes(4, 'little'))]
        names.append(f'buffer 1920x800 -> {bw}x{bh}')
    if a.views == 'on' and size is not None and size != (1920, 1080):
        for wsite, hsite in VIEW_SITES:
            writes += [(wsite, size[0].to_bytes(4, 'little')), (hsite, size[1].to_bytes(4, 'little'))]
        names.append(f'view {size[0]}x{size[1]}')
    if a.ring_heap != 8:
        writes += [(site, a.ring_heap.to_bytes(4, 'little')) for site in RING_HEAP_SITES]
        names.append(f'ring konstanta -> heap {a.ring_heap}')
    if a.cmdbuf_heap != 8:
        writes += [(site, bytes([a.cmdbuf_heap * 8])) for site in CMDBUF_SITES]
        names.append(f'command buffer -> heap {a.cmdbuf_heap}')
    if a.cbuf_heap != 8:
        writes += [(site, bytes([a.cbuf_heap * 8])) for site in CBUF_SITES]
        names.append(f'buffer konstanta -> heap {a.cbuf_heap}')
    h3 = HEAP3_MB
    if a.heap3 == 'auto':
        need = (8 if a.ring_heap == 3 else 0) + (40 if a.cmdbuf_heap == 3 else 0) + \
               (2 if a.cbuf_heap == 3 else 0)
        h3 = HEAP3_MB * (1 + -(-(need + 16) // HEAP3_MB)) if need else HEAP3_MB
    elif a.heap3 != 'off':
        try:
            h3 = int(a.heap3)
        except ValueError:
            sys.exit(f'--heap3 {a.heap3!r}: pakai auto, off atau angka MB')
        if not HEAP3_MB <= h3 <= GPUSTACK_MAX_MB:
            sys.exit(f'--heap3 {h3}: di luar {HEAP3_MB}..{GPUSTACK_MAX_MB}')
        h3 = (h3 + 1) // 2 * 2
    if h3 != HEAP3_MB:
        writes += [(site, (h3 << 20).to_bytes(4, 'little')) for site in HEAP3_SITES]
        names.append(f'heap 3 {HEAP3_MB} -> {h3} MB')
    if a.spin != 'off':
        try:
            spin = int(a.spin)
        except ValueError:
            sys.exit(f'--spin {a.spin!r}: pakai off atau angka 1..1801')
        if not 1 <= spin <= 0x709:
            sys.exit(f'--spin {spin}: di luar 1..1801')
        if spin != 0x709:
            writes.append((SPIN_SITE, spin.to_bytes(4, 'little')))
            names.append(f'spin job system 1801 -> {spin}')
    if a.aspect169:
        writes.append((0x84ce8c, struct.pack('<f', 16 / 9)))
        names.append('16:9 Aspect Ratio')
    for choice, base, sites, name in ((a.gpustack, GPUSTACK_MB, GPUSTACK_SITES, 'GpuStack'),
                                      (a.gpuheap, GPUHEAP_MB, GPUHEAP_SITES, 'Gpu')):
        mb = base if choice == 'off' else heap_mb(choice, size, base, name.lower())
        if mb != base:
            writes += [(site, (mb << 20).to_bytes(4, 'little')) for site in sites]
            names.append(f'heap {name} {base} -> {mb} MB')

    target = a.out / 'patches.bin'
    if not writes:
        target.unlink(missing_ok=True)
        print('Patch: tidak ada (game asli 30 FPS, resolusi asli)')
        return
    blob = struct.pack('<8sQQ', b'BBPATCH2', EBOOT_BASE, len(writes))
    for addr, data in writes:
        blob += struct.pack('<QQ', addr - EBOOT_BASE, len(data)) + data
    target.write_bytes(blob)
    print(f'Patch: {", ".join(names)} ({len(writes)} tulisan) -> {target}')


if __name__ == '__main__':
    main()
