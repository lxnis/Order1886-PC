// SPDX-FileCopyrightText: Copyright 2024 shadPS4 Emulator Project
// SPDX-License-Identifier: GPL-2.0-or-later

#include <cstdlib>
#include <cstring>
#include "shader_recompiler/frontend/translate/translate.h"
#include "shader_recompiler/ir/position.h"
#include "shader_recompiler/ir/reinterpret.h"
#include "shader_recompiler/profile.h"
#include "shader_recompiler/runtime_info.h"

namespace Shader::Gcn {

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

static AmdGpu::NumberFormat NumberFormatCompressed(AmdGpu::ShaderExportFormat export_format) {
    switch (export_format) {
    case AmdGpu::ShaderExportFormat::ABGR_FP16:
        return AmdGpu::NumberFormat::Float;
    case AmdGpu::ShaderExportFormat::ABGR_UNORM16:
        return AmdGpu::NumberFormat::Unorm;
    case AmdGpu::ShaderExportFormat::ABGR_SNORM16:
        return AmdGpu::NumberFormat::Snorm;
    case AmdGpu::ShaderExportFormat::ABGR_UINT16:
        return AmdGpu::NumberFormat::Uint;
    case AmdGpu::ShaderExportFormat::ABGR_SINT16:
        return AmdGpu::NumberFormat::Sint;
    default:
        UNREACHABLE_MSG("Unimplemented compressed export format {}",
                        static_cast<u32>(export_format));
    }
}

static u32 MaskFromExportFormat(u8 mask, AmdGpu::ShaderExportFormat export_format) {
    switch (export_format) {
    case AmdGpu::ShaderExportFormat::R_32:
        // Red only
        return mask & 1;
    case AmdGpu::ShaderExportFormat::GR_32:
        // Red and Green only
        return mask & 3;
    case AmdGpu::ShaderExportFormat::AR_32:
        // Red and Alpha only
        return mask & 9;
    case AmdGpu::ShaderExportFormat::ABGR_32:
        // All components
        return mask;
    default:
        UNREACHABLE_MSG("Unimplemented uncompressed export format {}",
                        static_cast<u32>(export_format));
    }
}

void Translator::ExportRenderTarget(const GcnInst& inst) {
    const auto& exp = inst.control.exp;
    const IR::Attribute mrt{exp.target};
    info.mrt_mask |= 1u << static_cast<u8>(mrt);

    // Dual source blending uses MRT1 for exporting src1
    u32 color_buffer_idx = static_cast<u32>(mrt) - static_cast<u32>(IR::Attribute::RenderTarget0);
    if (runtime_info.hw.fs.dual_source_blending && mrt == IR::Attribute::RenderTarget1) {
        color_buffer_idx = 0;
    }

    const auto color_buffer = runtime_info.hw.fs.color_buffers[color_buffer_idx];
    if (color_buffer.export_format == AmdGpu::ShaderExportFormat::Zero || exp.en == 0) {
        // No export
        return;
    }

    std::array<IR::F32, 4> components{};
    if (exp.compr) {
        // Components are float16 packed into a VGPR
        const auto num_format = NumberFormatCompressed(color_buffer.export_format);
        // Export R, G
        if (exp.en & 1) {
            const IR::Value unpacked_value =
                ir.Unpack2x16(num_format, ir.GetVectorReg(IR::VectorReg(inst.src[0].code)));
            components[0] = IR::F32{ir.CompositeExtract(unpacked_value, 0)};
            components[1] = IR::F32{ir.CompositeExtract(unpacked_value, 1)};
        }
        // Export B, A
        if ((exp.en >> 2) & 1) {
            const IR::Value unpacked_value =
                ir.Unpack2x16(num_format, ir.GetVectorReg(IR::VectorReg(inst.src[1].code)));
            components[2] = IR::F32{ir.CompositeExtract(unpacked_value, 0)};
            components[3] = IR::F32{ir.CompositeExtract(unpacked_value, 1)};
        }
    } else {
        // Components are float32 into separate VGPRS
        u32 mask = MaskFromExportFormat(exp.en, color_buffer.export_format);
        for (u32 i = 0; i < 4; i++, mask >>= 1) {
            if ((mask & 1) == 0) {
                continue;
            }
            components[i] = ir.GetVectorReg<IR::F32>(IR::VectorReg(inst.src[i].code));
        }
    }

    // Metal seems to have an issue where 8-bit unorm/snorm/sRGB outputs to render target
    // need a bias applied to round correctly; detect and set the flag for that here.
    const auto needs_unorm_fixup = profile.needs_unorm_fixup &&
                                   (color_buffer.num_format == AmdGpu::NumberFormat::Unorm ||
                                    color_buffer.num_format == AmdGpu::NumberFormat::Snorm ||
                                    color_buffer.num_format == AmdGpu::NumberFormat::Srgb) &&
                                   (color_buffer.data_format == AmdGpu::DataFormat::Format8 ||
                                    color_buffer.data_format == AmdGpu::DataFormat::Format8_8 ||
                                    color_buffer.data_format == AmdGpu::DataFormat::Format8_8_8_8);

    // Swizzle components and export
    for (u32 i = 0; i < 4; ++i) {
        const auto swizzled_comp = components[color_buffer.swizzle.Map(i)];
        if (swizzled_comp.IsEmpty()) {
            continue;
        }
        auto converted = ApplyWriteNumberConversion(ir, swizzled_comp, color_buffer.num_conversion);
        if (needs_unorm_fixup) {
            // FIXME: Fix-up for GPUs where float-to-unorm rounding is off from expected.
            converted = ir.FPSub(converted, ir.Imm32(1.f / 127500.f));
        }
        if (color_buffer.num_format != AmdGpu::NumberFormat::Uint &&
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

void Translator::ExportDepth(const GcnInst& inst) {
    const auto& exp = inst.control.exp;
    if (exp.en == 0) {
        // No export
        return;
    }

    std::array<IR::F32, 4> components{};
    if (exp.compr) {
        // Components are float16 packed into a VGPR
        const auto num_format = NumberFormatCompressed(runtime_info.hw.fs.z_export_format);
        // Export R, G
        if (exp.en & 1) {
            const IR::Value unpacked_value =
                ir.Unpack2x16(num_format, ir.GetVectorReg(IR::VectorReg(inst.src[0].code)));
            components[0] = IR::F32{ir.CompositeExtract(unpacked_value, 0)};
            components[1] = IR::F32{ir.CompositeExtract(unpacked_value, 1)};
        }
        // Export B, A
        if ((exp.en >> 2) & 1) {
            const IR::Value unpacked_value =
                ir.Unpack2x16(num_format, ir.GetVectorReg(IR::VectorReg(inst.src[1].code)));
            components[2] = IR::F32{ir.CompositeExtract(unpacked_value, 0)};
            // components[3] = IR::F32{ir.CompositeExtract(unpacked_value, 1)};
        }
    } else {
        // Components are float32 into separate VGPRS
        u32 mask = MaskFromExportFormat(exp.en & runtime_info.hw.fs.mrtz_mask,
                                        runtime_info.hw.fs.z_export_format);
        for (u32 i = 0; i < 4; i++, mask >>= 1) {
            if ((mask & 1) == 0) {
                continue;
            }
            components[i] = ir.GetVectorReg<IR::F32>(IR::VectorReg(inst.src[i].code));
        }
    }

    static constexpr std::array MrtzBuiltins = {IR::Attribute::Depth, IR::Attribute::StencilRef,
                                                IR::Attribute::SampleMask, IR::Attribute::Null};
    for (u32 i = 0; i < 4; ++i) {
        if (components[i].IsEmpty()) {
            continue;
        }
        ir.SetAttribute(MrtzBuiltins[i], components[i]);
    }
}

void Translator::EmitExport(const GcnInst& inst) {
    if (info.hw_stage == HwStage::Fragment && inst.control.exp.vm) {
        ir.Discard(ir.LogicalNot(ir.GetExec()));
    }

    const IR::Attribute attrib{inst.control.exp.target};
    if (IR::IsMrt(attrib)) {
        return ExportRenderTarget(inst);
    }
    if (attrib == IR::Attribute::Depth) {
        return ExportDepth(inst);
    }

    ASSERT_MSG(!inst.control.exp.compr, "Compressed exports only supported for render targets");

    const bool tess_emulated_primitive =
        info.sw_stage == SwStage::Vertex && runtime_info.sw.vs.tess_emulated_primitive;

    u32 mask = inst.control.exp.en;
    for (u32 i = 0; i < 4; i++, mask >>= 1) {
        if ((mask & 1) == 0) {
            continue;
        }
        const auto value = ir.GetVectorReg<IR::F32>(IR::VectorReg(inst.src[i].code));
        if (IsPosition(attrib)) {
            IR::ExportPosition(ir, runtime_info.hw.vs, tess_emulated_primitive, attrib, i, value);
        } else {
            ir.SetAttribute(attrib, value, i);
        }
    }
}

} // namespace Shader::Gcn
