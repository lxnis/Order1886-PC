// SPDX-License-Identifier: GPL-2.0-or-later
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
