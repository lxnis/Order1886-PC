#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-or-later
# The Order: 1886 (CUSA00035, v01.02) — native lewat bbport (Linux).
#
#   bash order-port.sh --prepare   siapkan image game (pertama kali / sesudah ganti branch), lalu main
#   bash order-port.sh             main saja
#
# Semua hasil olahan (berisi kode game, JANGAN dibagikan) ada di $KERJA/out.
# Save dan cache shader di $KERJA/user, log di $KERJA/order_play.log.
set -u

PROJECT=$HOME/Project
KERJA=$HOME/PS41886
BBPORT=$PROJECT/bbport
GAME=$HOME/PS4/CUSA00035
OUT=$KERJA/out
USERDIR=${ORDER_USER:-$KERJA/user}   # ORDER_USER=folder lain (mis. save AppImage ~/.local/share/order1886/user)
LOG=$KERJA/order_play.log

# Awal: sama dengan pengaturan aman DmC (serial recording, tanpa upscaler, filter asli game).
# Nilai di sini hanya default: variabel yang sudah di-set dari luar (env BB_...=...) yang dipakai.
# ORDER_SERIAL=0 mematikan paket "serial recording" (optimasi paralel bbport menyala lagi).
ORDER_ENV=()
setdef() { [[ -n ${!1+x} ]] || ORDER_ENV+=("$1=$2"); }
setdef BB_SKIP_GAME_CHECK 1; setdef BB_GAME_MENU 0; setdef BB_UPSCALER off
setdef BB_ANISO 0; setdef BB_NEO 0
# Direct memory 9 GiB (asli PS4 5056 MiB): heap GpuStack yang dibesarkan untuk 1440p/4K mengambil
# jatah memori streaming. Dengan 5056 MiB + GpuStack 2046 MB: 'Streaming IO Thread' crash (NO_SPACE).
setdef BB_DMEM_MB 9216
# Pita pink 1440p/4K (order_patch.py bagian 31): tulisan CPU di dalam render target layar diabaikan.
setdef BB_ORDER_RT_IGNORE_CPU 1
# 4K: render target kebal tulisan buffer GPU yang menumpang (order_patch.py bagian 32-34).
setdef BB_ORDER_RT_IGNORE_GPUBUF 1
# Cache shader disk driver NVIDIA (bawaan run.sh). Pengaturan run.sh lain (PREUPLOAD, COPY_GPU_BUFFERS,
# GPU_WRITE_TWINS, model memori) TIDAK dipasang: dengan itu The Order macet di menu (16 Okt).
setdef __GL_SHADER_DISK_CACHE 1; setdef __GL_SHADER_DISK_CACHE_SKIP_CLEANUP 1
setdef __GL_SHADER_DISK_CACHE_SIZE 10737418240
if [[ ${ORDER_SERIAL:-1} == 1 ]]; then
    setdef BB_PREP_WORKERS 0; setdef BB_VK_RECORD_THREAD 0; setdef BB_VK_RECORD_THREADS 1
    setdef BB_ASYNC_SUBMIT 0; setdef BB_ASYNC_FENCES 0
fi
echo "== Pengaturan: ${ORDER_ENV[*]}"

gagal() { echo "ERROR: $1" >&2; exit 1; }

[[ -x $BBPORT/out/bb-probe ]] || gagal "bb-probe tidak ada: build bbport dulu (lihat CATATAN.md)."
[[ -f $GAME/eboot.bin ]] || gagal "eboot.bin tidak ada di $GAME (drive game belum ter-mount?)."
echo "== bbport branch: $(git -C "$BBPORT" rev-parse --abbrev-ref HEAD) ($(git -C "$BBPORT" rev-parse --short HEAD))"

mkdir -p "$OUT" "$USERDIR"
cd "$BBPORT" || exit 1

if [[ ${1:-} == --prepare || ! -f $OUT/boot-linked.bin || ! -f $OUT/content.bin ]]; then
    [[ ${1:-} == --prepare ]] && shift
    echo "== 1/3 prepare.py"
    env "${ORDER_ENV[@]}" python3 scripts/prepare.py "$GAME" --out "$OUT" || gagal "prepare.py"
    echo "== 2/3 link_modules.py (libc.prx + libSceFios2.prx dari sce_module)"
    env "${ORDER_ENV[@]}" python3 scripts/link_modules.py "$GAME" --out "$OUT" \
        --modules libc.prx libSceFios2.prx || gagal "link_modules.py"
    echo "== 3/3 content_profile.py"
    env "${ORDER_ENV[@]}" python3 scripts/content_profile.py "$GAME" --out "$OUT" || gagal "content_profile.py"
fi

# Patch komunitas (order_patches.py): ORDER_FPS=30|60, ORDER_RES=native|use4k|LEBARxTINGGI, ORDER_ASPECT=1 (16:9).
# ORDER_GPUSTACK=auto|MB: heap render target game (654 MB asli; auto = sebanding piksel di atas 1080p).
# ORDER_SPIN=off|N: ambang spin worker job system (pakai bersama BB_ORDER_YIELD_US, order_patch.py 74).
# 60 FPS: softlock QTE Chapter 6 & 9 -> main bagian itu dengan ORDER_FPS=30.
PATCH_ARGS=(--fps "${ORDER_FPS:-30}" --res "${ORDER_RES:-native}" --gpustack "${ORDER_GPUSTACK:-auto}" --gpuheap "${ORDER_GPUHEAP:-off}" --fix800 "${ORDER_FIX800:-on}" --ring-heap "${ORDER_RING:-8}" --heap3 "${ORDER_HEAP3:-auto}" --cmdbuf-heap "${ORDER_CMDBUF:-8}" --cbuf-heap "${ORDER_CBUF:-8}" --views "${ORDER_VIEWS:-on}" --spin "${ORDER_SPIN:-off}")
[[ -n ${ORDER_CPUHEAP:-} ]] && PATCH_ARGS+=(--cpu-heap "$ORDER_CPUHEAP")
[[ ${ORDER_ASPECT:-0} == 1 ]] && PATCH_ARGS+=(--aspect169)
python3 "$KERJA/order_patches.py" "$OUT" "${PATCH_ARGS[@]}" || gagal "order_patches.py"
PATCH_OPT=()
[[ -f $OUT/patches.bin ]] && PATCH_OPT=(--patches "$OUT/patches.bin")

echo "== Main (log: $LOG)"
env "${ORDER_ENV[@]}" ./out/bb-probe "$OUT/boot-linked.bin" \
    --content-profile "$OUT/content.bin" "${PATCH_OPT[@]}" \
    --app0 "$GAME" --user "$USERDIR" --timeout "${BB_TIMEOUT:-0}" "$@" > "$LOG" 2>&1
status=$?

echo "== Selesai (kode keluar $status). Ringkasan:"
grep -E '^Patches:|^STOP|^API|Guest fault|Host fault|Fault \(signal|NULL call|Shader binary|Failed to create' "$LOG" | head -15
echo "-- statistik frame (BB_FRAME_STATS=1), 10 terakhir:"
grep -iE 'frame stats|fps|pipelines compiled' "$LOG" | grep -v flipmode | tail -10
echo "-- pesan GPU terbanyak:"
grep -E '^GPU \[' "$LOG" | sed -E 's/0x[0-9a-f]+/X$HOME; s/[0-9]+/N$HOME' | sort | uniq -c | sort -rn | head -6
echo "-- 15 baris terakhir log (tanpa spam recompiler/flip):"
grep -vE 'SRT walker|flipmode|direct allocation|mapped direct' "$LOG" | tail -15
exit $status
