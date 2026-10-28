// SPDX-License-Identifier: GPL-2.0-or-later
// bbport: helper thread sizing. Counts follow the hardware threads this process may run on
// (the affinity mask, so `taskset` can emulate a Steam Deck), and speculative helpers run as
// SCHED_IDLE: they use cores the game leaves idle and never take time from its threads.

#pragma once

#include <algorithm>
#include <cstdlib>
#include <thread>
#ifdef _WIN32
#include <bit>
#include <windows.h>
#else
#include <sched.h>
#include <sys/resource.h>
#include <unistd.h>
#endif

namespace BbThreads {
#ifdef _WIN32
/// Hardware threads available to the process (its affinity mask).
inline unsigned Available() {
    DWORD_PTR process = 0, system = 0;
    if (GetProcessAffinityMask(GetCurrentProcess(), &process, &system) && process) {
        return std::max(1, std::popcount(static_cast<unsigned long long>(process)));
    }
    return std::max(1u, std::thread::hardware_concurrency());
}

/// The calling thread only runs when cores are otherwise idle (lowest Windows priority).
inline void MakeBackground() {
    SetThreadPriority(GetCurrentThread(), THREAD_PRIORITY_IDLE);
}

/// bbport-order-win (112): the port's own threads (GPU command thread, draw pipe stage B, Vulkan
/// recorders, copy threads) above the game's spinning workers: a yield or a wake-up does not
/// wait behind them. BB_ORDER_HOST_PRIORITY: 0 off, 1 above normal (default), 2 highest.
inline int HostPriorityLevel() {
    static const int level = [] {
        const char* env = std::getenv("BB_ORDER_HOST_PRIORITY");
        return env && *env ? std::atoi(env) : 1;
    }();
    return level;
}
inline void RaiseHostPriority() {
    const int level = HostPriorityLevel();
    if (level >= 2) {
        SetThreadPriority(GetCurrentThread(), THREAD_PRIORITY_HIGHEST);
    } else if (level == 1) {
        SetThreadPriority(GetCurrentThread(), THREAD_PRIORITY_ABOVE_NORMAL);
    }
}
#else

/// Hardware threads available to the process.
inline unsigned Available() {
    cpu_set_t set;
    CPU_ZERO(&set);
    if (sched_getaffinity(0, sizeof(set), &set) == 0) {
        return std::max(1, CPU_COUNT(&set));
    }
    return std::max(1u, std::thread::hardware_concurrency());
}

inline int HostPriorityLevel() { return 0; }
inline void RaiseHostPriority() {} // bbport-order-win (112): Windows only

/// The calling thread only runs on otherwise idle cores (falls back to the lowest nice level).
inline void MakeBackground() {
    sched_param param{};
    if (sched_setscheduler(0, SCHED_IDLE, &param) != 0) {
        setpriority(PRIO_PROCESS, static_cast<id_t>(gettid()), 19);
    }
}
#endif

} // namespace BbThreads
