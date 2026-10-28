/* Guest threads on host pthreads. Each guest thread owns a FreeBSD-style TCB
 * (variant II: static TLS below the TCB). The loader rewrites the eboot's
 * `mov rax, fs:[0]` into `mov rax, gs:[0]`, so GS base = guest TCB while glibc
 * keeps FS. Priorities/affinity are recorded, not enforced by a PS4 scheduler.
 * Windows: GS is the TEB and cannot be moved. The guest TCB lives in a TLS slot of the TEB
 * instead, and the loader rewrites the load to `mov rax, gs:[0x1480+8*slot]` (TlsSlots),
 * the same 9-byte instruction with another displacement. */
#define _GNU_SOURCE
#include "runtime.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <pthread.h>
#include <sched.h>
#include <time.h>
#include <setjmp.h>
#include <errno.h>
#include <unistd.h>
#ifdef _WIN32
#include <windows.h>
#else
#include <sys/syscall.h>
#include <sys/mman.h>
#include <asm/prctl.h>
#endif
#define ERR(n) ((int32_t)(UINT32_C(0x80020000)|(n)))
#ifdef _WIN32
/* bbport-dmc-timer: Windows times out every wait (winpthreads condition variables and semaphores,
 * WaitForSingleObject) on the system timer tick, 15.6 ms unless a process asks for less. DmC's
 * Bink cutscenes wait in short timed steps: on the default tick a frame took ~156 ms (8 FPS, GPU
 * idle) while gameplay ran at 150 FPS. timeBeginPeriod(1) makes the tick 1 ms for this process,
 * as games and emulators do. BB_TIMER_1MS=0 leaves the system default (A/B). */
__attribute__((constructor)) static void dmc_timer_resolution(void) {
    const char *env = getenv("BB_TIMER_1MS");
    if (env && env[0] == '0') { printf("Runtime: Windows timer resolution left at the default (BB_TIMER_1MS=0)\n"); return; }
    HMODULE winmm = LoadLibraryA("winmm.dll");
    typedef UINT (WINAPI *TimeBeginPeriod)(UINT);
    TimeBeginPeriod begin = winmm ? (TimeBeginPeriod)(void *)GetProcAddress(winmm, "timeBeginPeriod") : NULL;
    printf("Runtime: Windows timer resolution 1 ms: %s\n", begin && begin(1) == 0 ? "on" : "not available");
}
#endif
#define ATTR_MAGIC UINT32_C(0x41545452)
#define STACK_MARGIN (256*1024)
#define MIN_STACK (64*1024)
#define DEFAULT_STACK (1024*1024)
#define DEFAULT_PRIO 700

typedef void *(ABI *GuestEntry)(void *);
typedef struct ThreadAttr {
    uint32_t magic;
    int detached, policy, prio, inherit;
    uint64_t stack, guard, affinity;
    struct ThreadAttr *next;
} ThreadAttr;
typedef struct GuestThread {
    /* bbport-dmc: first field = thread id, as FreeBSD's struct pthread (long tid). Guest code
     * reads it straight from the handle (UE3: ThreadID = *(int *)handle after scePthreadCreate),
     * so it must equal scePthreadGetthreadid() and be set before the thread is created. */
    int64_t tid;
    /* Guest-visible TCB is allocated separately; this is the ScePthread handle. */
    uint64_t *tcb;
    unsigned char *tls_block;
    pthread_t host;
    GuestEntry entry;
    void *argument, *result;
    ThreadAttr attr;
    char name[32];
    int detached, finished, joined, host_owned;
#ifdef _WIN32
    bb_jmp_buf exit_jump; /* no SEH unwinding through guest frames */
#else
    jmp_buf exit_jump;
#endif
    struct GuestThread *next;
} GuestThread;

static pthread_mutex_t lock=PTHREAD_MUTEX_INITIALIZER;
static ThreadAttr *attributes;
static GuestThread *threads;
static _Thread_local GuestThread *current;
static _Thread_local int32_t guest_errno;
static const unsigned char *tls_template;
static uint64_t tls_filesz, tls_memsz, tls_align=16;
static size_t created, joined_count, exited;

void runtime_set_main_tls(const void *data,uint64_t filesz,uint64_t memsz,uint64_t align) {
    tls_template=data; tls_filesz=filesz; tls_memsz=memsz; tls_align=align ? align : 16;
}
static uint64_t tls_offset(void) { return (tls_memsz+tls_align-1)&~(tls_align-1); }
#ifdef _WIN32
/* TEB TlsSlots[64] start at gs:0x1480; slots 64+ live elsewhere and cannot be used. */
static DWORD tls_slot=TLS_OUT_OF_INDEXES;
uint32_t runtime_thread_tcb_offset(void) {
    if (tls_slot==TLS_OUT_OF_INDEXES) {
        tls_slot=TlsAlloc();
        if (tls_slot>=64) { fprintf(stderr,"STOP: no TEB TLS slot below 64 (got %lu)\n",tls_slot); exit(21); }
    }
    return 0x1480+8*(uint32_t)tls_slot;
}
static void set_gs(void *base) {
    runtime_thread_tcb_offset();
    if (!TlsSetValue(tls_slot,base)) { fprintf(stderr,"STOP: TlsSetValue failed (%lu)\n",GetLastError()); exit(21); }
}
#define tls_block_alloc(size) _aligned_malloc(size,64)
#else
static void set_gs(void *base) {
    if (syscall(SYS_arch_prctl,ARCH_SET_GS,(unsigned long)base)) { perror("STOP: arch_prctl(ARCH_SET_GS)"); exit(21); }
}
#define tls_block_alloc(size) aligned_alloc(64,size)
#endif
/* Build TCB/static TLS for the calling host thread and point GS at it. */
static void attach(GuestThread *t) {
    uint64_t offset=tls_offset();
    size_t total=offset+256;
    unsigned char *block=tls_block_alloc((total+63)&~(size_t)63);
    if (!block) { fputs("Cannot allocate guest TLS\n",stderr); exit(1); }
    memset(block,0,total);
    if (tls_filesz) memcpy(block,tls_template,tls_filesz);
    uint64_t *tcb=(uint64_t *)(block+offset);
    static uint64_t dtv[3];
    tcb[0]=(uint64_t)(uintptr_t)tcb;         /* tcb_self */
    tcb[1]=(uint64_t)(uintptr_t)dtv;         /* tcb_dtv (static module only) */
    tcb[2]=(uint64_t)(uintptr_t)t;           /* tcb_thread */
    t->tls_block=block; t->tcb=tcb;
    set_gs(tcb);
    current=t;
}
static int64_t next_tid=100000; /* bbport-dmc: FreeBSD thread ids start at 100000 */
static GuestThread *new_thread(void) {
    GuestThread *t=calloc(1,sizeof(*t));
    if (!t) return NULL;
    t->tid=__atomic_fetch_add(&next_tid,1,__ATOMIC_RELAXED);
    t->attr=(ThreadAttr){.magic=ATTR_MAGIC,.policy=1,.prio=DEFAULT_PRIO,.stack=DEFAULT_STACK,.affinity=0x7f};
    return t;
}
static void publish(GuestThread *t) {
    pthread_mutex_lock(&lock); t->next=threads; threads=t; pthread_mutex_unlock(&lock);
}
/* The guest name of the calling thread, or NULL for a thread the runtime never saw (fault
 * reports; creates nothing). */
const char *runtime_thread_current_name(void) { return current ? current->name : NULL; }
/* Host threads that call into guest code without being created by the guest
 * (the main thread, test threads) get a record on first use. */
GuestThread *runtime_thread_current(void) {
    if (current) return current;
    GuestThread *t=new_thread();
    if (!t) { fputs("Cannot allocate guest thread\n",stderr); exit(1); }
    t->host=pthread_self(); t->host_owned=1;
    snprintf(t->name,sizeof(t->name),"host");
    attach(t); publish(t);
    return t;
}
/* Host threads that call guest code (HLE decoders invoking guest callbacks) need
 * a TCB/TLS like guest threads; the record lives until process exit. */
void runtime_thread_attach_host(const char *name) {
    GuestThread *t=runtime_thread_current();
    snprintf(t->name,sizeof(t->name),"%s",name ? name : "host");
}
void runtime_thread_attach_main(void) {
    GuestThread *t=runtime_thread_current();
    snprintf(t->name,sizeof(t->name),"main");
}
static GuestThread *find_thread(void *handle) {
    GuestThread *found=NULL;
    pthread_mutex_lock(&lock);
    for (GuestThread *t=threads;t;t=t->next) if (t==handle) { found=t; break; }
    pthread_mutex_unlock(&lock);
    return found;
}
static ThreadAttr *find_attr(ThreadAttr **slot) {
    if (!slot || !*slot) return NULL;
    ThreadAttr *found=NULL;
    pthread_mutex_lock(&lock);
    for (ThreadAttr *a=attributes;a;a=a->next) if (a==*slot && a->magic==ATTR_MAGIC) { found=a; break; }
    pthread_mutex_unlock(&lock);
    return found;
}

static ABI void *thread_self(void) { return runtime_thread_current(); }
static ABI int32_t *guest_error(void) { return &guest_errno; }
int32_t *runtime_errno(void) { return &guest_errno; }

static ABI int32_t attr_init(ThreadAttr **out) {
    if (!out) return ERR(22);
    ThreadAttr *a=calloc(1,sizeof(*a));
    if (!a) return ERR(12);
    *a=(ThreadAttr){.magic=ATTR_MAGIC,.policy=1,.prio=DEFAULT_PRIO,.inherit=4,.stack=DEFAULT_STACK,.guard=4096,.affinity=0x7f};
    pthread_mutex_lock(&lock); a->next=attributes; attributes=a; pthread_mutex_unlock(&lock);
    *out=a; return 0;
}
static ABI int32_t attr_destroy(ThreadAttr **slot) {
    ThreadAttr *a=find_attr(slot);
    if (!a) return ERR(22);
    pthread_mutex_lock(&lock);
    ThreadAttr **link=&attributes;
    while (*link!=a) link=&(*link)->next;
    *link=a->next; a->magic=0;
    pthread_mutex_unlock(&lock);
    free(a); *slot=NULL; return 0;
}
static ABI int32_t attr_get(void *thread,ThreadAttr **out) {
    ThreadAttr *a=find_attr(out);
    if (!a || !thread) return ERR(22);
    GuestThread *t=find_thread(thread);
    if (!t) return ERR(3);
    ThreadAttr *next=a->next;
    *a=t->attr; a->magic=ATTR_MAGIC; a->next=next;
    a->detached=t->detached;
    return 0;
}
static ABI int32_t attr_set_stack(ThreadAttr **slot,uint64_t size) {
    ThreadAttr *a=find_attr(slot);
    if (!a || size<16384) return ERR(22);
    a->stack=size; return 0;
}
static ABI int32_t attr_get_stack(ThreadAttr **slot,uint64_t *size) {
    ThreadAttr *a=find_attr(slot);
    if (!a || !size) return ERR(22);
    *size=a->stack; return 0;
}
static ABI int32_t attr_set_detach(ThreadAttr **slot,int state) {
    ThreadAttr *a=find_attr(slot);
    if (!a || (state!=0 && state!=1)) return ERR(22);
    a->detached=state; return 0;
}
static ABI int32_t attr_get_detach(ThreadAttr **slot,int *state) {
    ThreadAttr *a=find_attr(slot);
    if (!a || !state) return ERR(22);
    *state=a->detached; return 0;
}
static ABI int32_t attr_set_policy(ThreadAttr **slot,int policy) {
    ThreadAttr *a=find_attr(slot);
    if (!a || policy<1 || policy>3) return ERR(22);
    a->policy=policy; return 0;
}
static ABI int32_t attr_set_inherit(ThreadAttr **slot,int inherit) {
    ThreadAttr *a=find_attr(slot);
    if (!a || (inherit!=0 && inherit!=4)) return ERR(22);
    a->inherit=inherit; return 0;
}
static ABI int32_t attr_set_param(ThreadAttr **slot,const int *param) {
    ThreadAttr *a=find_attr(slot);
    if (!a || !param) return ERR(22);
    a->prio=*param; return 0;
}
static ABI int32_t attr_get_param(ThreadAttr **slot,int *param) {
    ThreadAttr *a=find_attr(slot);
    if (!a || !param) return ERR(22);
    *param=a->prio; return 0;
}
static ABI int32_t attr_set_affinity(ThreadAttr **slot,uint64_t mask) {
    ThreadAttr *a=find_attr(slot);
    if (!a) return ERR(22);
    a->affinity=mask; return 0;
}
static ABI int32_t attr_affinity(ThreadAttr **slot,uint64_t *mask) {
    ThreadAttr *a=find_attr(slot);
    if (!a || !mask) return ERR(22);
    *mask=a->affinity; return 0;
}
static ABI int32_t attr_set_guard(ThreadAttr **slot,uint64_t size) {
    ThreadAttr *a=find_attr(slot);
    if (!a) return ERR(22);
    a->guard=size; return 0;
}

/* Linux thread names hold 15 characters; longer ones would be rejected. */
static void set_host_name(const char *name) {
    char host[16]={0};
    memcpy(host,name,strnlen(name,sizeof(host)-1));
    pthread_setname_np(pthread_self(),host);
}
#ifdef _WIN32
#define exit_setjmp(t) bb_setjmp((t)->exit_jump)
#define exit_longjmp(t) bb_longjmp((t)->exit_jump,1)
#else
#define exit_setjmp(t) setjmp((t)->exit_jump)
#define exit_longjmp(t) longjmp((t)->exit_jump,1)
#endif
static void *host_start(void *p) {
    GuestThread *t=p;
    attach(t);
    set_host_name(t->name);
    if (!exit_setjmp(t)) t->result=t->entry(t->argument);
    runtime_kernel_thread_exit();
    runtime_thread_keys_cleanup();
    pthread_mutex_lock(&lock); t->finished=1; ++exited; pthread_mutex_unlock(&lock);
    return t->result;
}
static int32_t create(GuestThread **out,ThreadAttr **attr_slot,GuestEntry entry,void *argument,const char *name) {
    if (!out || !entry) return ERR(22);
    ThreadAttr *a=NULL;
    if (attr_slot && !(a=find_attr(attr_slot))) return ERR(22);
    GuestThread *t=new_thread();
    if (!t) return ERR(12);
    if (a) { t->attr=*a; t->attr.next=NULL; }
    t->entry=entry; t->argument=argument; t->detached=t->attr.detached;
    snprintf(t->name,sizeof(t->name),"%s",name ? name : "guest");
    pthread_attr_t host;
    pthread_attr_init(&host);
    uint64_t stack=t->attr.stack<MIN_STACK ? MIN_STACK : t->attr.stack;
    /* Stacks below 1 TiB as on PS4; guest code may pack stack addresses. */
    size_t stack_bytes=(size_t)stack+STACK_MARGIN;
#ifdef _WIN32
    /* Windows places the stack itself (low: no high-entropy ASLR) and commits all of it:
     * guest code has no stack probes and would step over the guard page. */
    pthread_attr_setstacksize(&host,stack_bytes);
#else
    void *stack_memory=runtime_low_map(stack_bytes,PROT_READ|PROT_WRITE);
    if (stack_memory) pthread_attr_setstack(&host,stack_memory,stack_bytes);
    else pthread_attr_setstacksize(&host,stack_bytes);
#endif
    publish(t);
    /* Publish the handle before the thread can run and inspect itself. */
    *out=t;
    int e=pthread_create(&t->host,&host,host_start,t);
    pthread_attr_destroy(&host);
    if (e) { fprintf(stderr,"STOP: host pthread_create failed: %d\n",e); exit(21); }
    if (t->detached) pthread_detach(t->host);
    pthread_mutex_lock(&lock); ++created; pthread_mutex_unlock(&lock);
    printf("Runtime: guest thread '%s' created (stack=%llu, prio=%d)\n",t->name,(unsigned long long)stack,t->attr.prio);
    return 0;
}
static ABI int32_t thread_create(GuestThread **out,ThreadAttr **attr,GuestEntry entry,void *argument,const char *name) {
    return create(out,attr,entry,argument,name);
}
static ABI int32_t thread_join(GuestThread *t,void **result) {
    if (!find_thread(t) || t->host_owned) return ERR(3);
    if (t==current) return ERR(11);
    if (t->detached || t->joined) return ERR(22);
    t->joined=1;
    void *value=NULL;
    int e=pthread_join(t->host,&value);
    if (e) { fprintf(stderr,"STOP: host pthread_join failed: %d\n",e); exit(21); }
    if (result) *result=t->result;
    pthread_mutex_lock(&lock); ++joined_count; pthread_mutex_unlock(&lock);
    return 0;
}
static ABI int32_t thread_detach(GuestThread *t) {
    if (!find_thread(t)) return ERR(3);
    if (t->detached) return ERR(22);
    t->detached=1;
    if (!t->host_owned) pthread_detach(t->host);
    return 0;
}
static ABI __attribute__((noreturn)) void thread_exit(void *value) {
    GuestThread *t=runtime_thread_current();
    if (t->host_owned) { fputs("STOP: pthread_exit on host-owned/main thread\n",stderr); exit(21); }
    t->result=value;
    /* No host unwinder: guest frames have no registered FDEs. */
    exit_longjmp(t);
}
/* bbport-order-win (113): winpthreads' nanosleep sleeps whole milliseconds (50 us -> Sleep(0), a
   spin). A high-resolution waitable timer sleeps microseconds (Windows 10 1803+). */
#ifdef _WIN32
static void bb_order_sleep_us(int us) {
    static __thread HANDLE timer;
    static __thread int tried;
    static int told;
    if (!tried) {
        tried = 1;
        timer = CreateWaitableTimerExW(NULL, NULL, 0x00000002 /* HIGH_RESOLUTION */,
                                       TIMER_ALL_ACCESS);
        if (!__atomic_exchange_n(&told, 1, __ATOMIC_RELAXED)) {
            fprintf(stderr, "bbport-order (113): Task Kernel tidur %d us lewat %s\n", us,
                    timer ? "timer resolusi tinggi" : "Sleep(1)");
        }
    }
    if (timer) {
        LARGE_INTEGER due;
        due.QuadPart = -(LONGLONG)us * 10; /* 100 ns units, relative */
        if (SetWaitableTimer(timer, &due, 0, NULL, NULL, FALSE)) {
            WaitForSingleObject(timer, INFINITE);
            return;
        }
    }
    Sleep(1);
}
#else
static void bb_order_sleep_us(int us) {
    struct timespec ts = {0, (long)us * 1000L};
    nanosleep(&ts, NULL);
}
#endif
static ABI int32_t thread_yield(void) { /* bbport-order (74) */
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
        const char *name = runtime_thread_current_name(); /* bbport-order-win (113) */
        task_kernel = name && strncmp(name, "Task Kernel", 11) == 0;
    }
    if (sleep_us > 0 && task_kernel) {
        bb_order_sleep_us(sleep_us); /* bbport-order-win (113) */
    } else {
        sched_yield();
    }
    return 0;
}
static ABI int32_t thread_get_prio(GuestThread *t,int *prio) {
    if (!find_thread(t)) return ERR(3);
    if (!prio) return ERR(22);
    *prio=t->attr.prio; return 0;
}
static ABI int32_t thread_set_prio(GuestThread *t,int prio) {
    if (!find_thread(t)) return ERR(3);
    t->attr.prio=prio; return 0;
}
static ABI int32_t thread_set_affinity(GuestThread *t,uint64_t mask) {
    if (!find_thread(t)) return ERR(3);
    t->attr.affinity=mask; return 0;
}
static ABI int32_t thread_get_affinity(GuestThread *t,uint64_t *mask) {
    if (!find_thread(t)) return ERR(3);
    if (!mask) return ERR(22);
    *mask=t->attr.affinity; return 0;
}
static ABI int32_t thread_rename(GuestThread *t,const char *name) {
    if (!find_thread(t)) return ERR(3);
    if (!name) return ERR(22);
    snprintf(t->name,sizeof(t->name),"%s",name);
    if (t==current) set_host_name(t->name);
    return 0;
}
static ABI int32_t thread_equal(GuestThread *a,GuestThread *b) { return a==b; }
/* SacredFire: the thread's name into a 32-byte buffer, and its kernel thread id. */
static ABI int32_t thread_getname(GuestThread *t,char *name) {
    if (!find_thread(t)) return ERR(3);
    if (!name) return ERR(22);
    memcpy(name,t->name,sizeof(t->name)); return 0;
}
/* bbport-dmc: the guest thread id (first field of the ScePthread handle), not the host's. */
static ABI int32_t thread_getthreadid(void) { return (int32_t)runtime_thread_current()->tid; }
/* Deferred cancellation: a thread without cancellation points keeps running, as on the console; the
 * request is noted so the caller sees success. No guest thread of this game is expected to reach a
 * cancellation point; a cancel that must take effect would need the point implemented. */
static unsigned cancels;
static ABI int32_t thread_cancel(GuestThread *t) {
    if (!find_thread(t)) return ERR(3);
    if (__atomic_fetch_add(&cancels,1,__ATOMIC_RELAXED)<4) printf("Runtime: scePthreadCancel(%s) noted; deferred cancellation never fires here\n",t->name);
    return 0;
}
/* POSIX scheduling parameters: the policy and priority recorded for the thread (SCHED_OTHER 2,
 * FIFO 1, RR 3 as on FreeBSD); the host scheduler is not changed. */
typedef struct { int32_t priority; } GuestSchedParam;
static ABI int32_t posix_getschedparam(GuestThread *t,int32_t *policy,GuestSchedParam *param) {
    if (!find_thread(t)) return 3;
    if (!policy || !param) return 22;
    *policy=t->attr.policy; param->priority=t->attr.prio; return 0;
}
static ABI int32_t posix_setschedparam(GuestThread *t,int32_t policy,const GuestSchedParam *param) {
    if (!find_thread(t)) return 3;
    if (!param || policy<1 || policy>3) return 22;
    t->attr.policy=policy; t->attr.prio=param->priority; return 0;
}
/* bbport-dmc: the scePthread* versions: same behaviour, SCE error codes (0x80020000 + errno). */
static ABI int32_t sce_getschedparam(GuestThread *t,int32_t *policy,GuestSchedParam *param) {
    const int32_t e=posix_getschedparam(t,policy,param); return e ? ERR(e) : 0;
}
static ABI int32_t sce_setschedparam(GuestThread *t,int32_t policy,const GuestSchedParam *param) {
    const int32_t e=posix_setschedparam(t,policy,param); return e ? ERR(e) : 0;
}

/* POSIX (libScePosix) variants return positive errno values. */
static int32_t posix(int32_t r) { return r ? (int32_t)((uint32_t)r&0xffff) : 0; }
static ABI int32_t posix_attr_init(ThreadAttr **a) { return posix(attr_init(a)); }
static ABI int32_t posix_attr_destroy(ThreadAttr **a) { return posix(attr_destroy(a)); }
static ABI int32_t posix_attr_set_detach(ThreadAttr **a,int s) { return posix(attr_set_detach(a,s)); }
static ABI int32_t posix_attr_set_stack(ThreadAttr **a,uint64_t s) { return posix(attr_set_stack(a,s)); }
static ABI int32_t posix_attr_set_param(ThreadAttr **a,const int *p) { return posix(attr_set_param(a,p)); }
static ABI int32_t posix_create(GuestThread **t,ThreadAttr **a,GuestEntry e,void *arg) { return posix(create(t,a,e,arg,"posix")); }
static ABI int32_t posix_create_name(GuestThread **t,ThreadAttr **a,GuestEntry e,void *arg,const char *name) { return posix(create(t,a,e,arg,name)); }
static ABI int32_t posix_join(GuestThread *t,void **r) { return posix(thread_join(t,r)); }

#ifdef _WIN32
/* bbport-dmc-sampler4: BB_SAMPLE=1 (Windows; Linux has BB_SAMPLE_THREAD). Every millisecond each
 * guest thread is suspended for a moment: its instruction pointer and, from a scan of its stack,
 * the nearest return addresses into sacredfire.exe (the port) and into the game are noted. Every
 * 5 s: per thread, the share of time in game code and blocked in the kernel; then the hottest
 * (thread, where, port caller, game caller) entries. Host code: module+offset (llvm-symbolizer
 * --relative-address for sacredfire.exe); game code: guest+offset from 0x800000000. */
enum { DMC_SLOTS = 8192, DMC_TOP = 40, DMC_NAMES = 64, DMC_SCAN = 1024 };
typedef struct { uint64_t rip, host, host2, guest, guest2, guest3; uint32_t count; char name[24]; } DmcSample;
static DmcSample dmc_samples[DMC_SLOTS];
static uint64_t dmc_exe_lo, dmc_exe_hi;
static int dmc_is_guest(uint64_t a) { return a >= 0x800000000ull && a < 0x810000000ull; }
/* Guest code: the eboot's text and the linked modules (libc, Fios2, NTJobCode) after 0x4260000. */
static int dmc_is_guest_code(uint64_t a) {
    const uint64_t o = a - 0x800000000ull;
    return a >= 0x800000000ull && ((o >= 0x1000ull && o < 0x2f7c000ull) || (o >= 0x4260000ull && o < 0x4800000ull));
}
/* A plausible return address: the bytes before it are a call (e8 rel32, ff /2 forms). */
static int dmc_after_call(uint64_t a) {
    /* Read through ReadProcessMemory: a stale stack value may point at an unmapped page. */
    unsigned char bytes[8];
    SIZE_T got = 0;
    if (!ReadProcessMemory(GetCurrentProcess(), (LPCVOID)(uintptr_t)(a - 8), bytes, 8, &got) || got != 8) return 0;
    const unsigned char *p = bytes + 8;
    if (p[-5] == 0xe8) return 1;
    if (p[-2] == 0xff && (p[-1] & 0xf8) == 0xd0) return 1;                 /* call reg */
    if (p[-2] == 0xff && (p[-1] & 0xf8) == 0x10 && (p[-1] & 7) != 4 && (p[-1] & 7) != 5) return 1; /* call [reg] */
    if (p[-3] == 0xff && (p[-2] & 0xf8) == 0x50) return 1;                 /* call [reg+d8] */
    if (p[-6] == 0xff && (p[-5] == 0x15 || (p[-5] & 0xf8) == 0x90)) return 1; /* call [rip+d32] / [reg+d32] */
    if (p[-3] == 0x41 && p[-2] == 0xff && (p[-1] & 0xf8) == 0xd0) return 1; /* call r8-r15 */
    return 0;
}
static void dmc_where(uint64_t rip, char *out, size_t size) {
    HMODULE m = NULL;
    if (!rip) { snprintf(out, size, "-"); return; }
    if (dmc_is_guest(rip)) { snprintf(out, size, "guest+0x%llx", (unsigned long long)(rip - 0x800000000ull)); return; }
    if (GetModuleHandleExA(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS | GET_MODULE_HANDLE_EX_FLAG_UNCHANGED_REFCOUNT,
                           (LPCSTR)(uintptr_t)rip, &m) && m) {
        char path[MAX_PATH] = "?";
        GetModuleFileNameA(m, path, sizeof(path));
        const char *base = strrchr(path, '\\');
        snprintf(out, size, "%s+0x%llx", base ? base + 1 : path, (unsigned long long)(rip - (uint64_t)(uintptr_t)m));
    } else {
        snprintf(out, size, "0x%llx", (unsigned long long)rip);
    }
}
static int dmc_cmp(const void *a, const void *b) {
    const DmcSample *x = a, *y = b;
    return x->count < y->count ? 1 : x->count > y->count ? -1 : 0;
}
static void dmc_report(uint64_t total) {
    static DmcSample sorted[DMC_SLOTS];
    struct { char name[24]; uint32_t count, guest, kernel; } names[DMC_NAMES];
    int nnames = 0, n = 0;
    for (int i = 0; i < DMC_SLOTS; ++i) {
        if (!dmc_samples[i].count) continue;
        sorted[n++] = dmc_samples[i];
        int k = 0;
        while (k < nnames && strcmp(names[k].name, dmc_samples[i].name)) ++k;
        if (k == nnames && nnames < DMC_NAMES) { memset(&names[k], 0, sizeof(names[k])); memcpy(names[k].name, dmc_samples[i].name, 24); ++nnames; }
        if (k < nnames) {
            char where[160]; dmc_where(dmc_samples[i].rip, where, sizeof(where));
            names[k].count += dmc_samples[i].count;
            if (!strncmp(where, "guest+", 6)) names[k].guest += dmc_samples[i].count;
            if (!strncmp(where, "ntdll", 5) || !strncmp(where, "win32u", 6) || !strncmp(where, "KERNELBASE", 10)) names[k].kernel += dmc_samples[i].count;
        }
    }
    qsort(sorted, n, sizeof(*sorted), dmc_cmp);
    printf("Sampler: %llu samples in 5 s (1 per ms per guest thread)\n", (unsigned long long)total);
    for (int k = 0; k < nnames; ++k)
        if (names[k].count * 50 >= total / 10)
            printf("Sampler thread %-24s %6u samples: guest code %3u%%, blocked in the kernel %3u%%\n", names[k].name,
                   names[k].count, names[k].guest * 100 / names[k].count, names[k].kernel * 100 / names[k].count);
    for (int i = 0; i < n && i < DMC_TOP; ++i) {
        char where[160], host[160], host2[160], guest[48], guest2[48], guest3[48];
        dmc_where(sorted[i].rip, where, sizeof(where));
        dmc_where(sorted[i].host, host, sizeof(host));
        dmc_where(sorted[i].host2, host2, sizeof(host2));
        dmc_where(sorted[i].guest, guest, sizeof(guest));
        dmc_where(sorted[i].guest2, guest2, sizeof(guest2));
        dmc_where(sorted[i].guest3, guest3, sizeof(guest3));
        printf("Sampler hot %2d: %6u  %-20s %-24s port %s < %s  game %s < %s < %s\n", i + 1, sorted[i].count,
               sorted[i].name, where, host, host2, guest, guest2, guest3);
    }
    fflush(stdout);
    memset(dmc_samples, 0, sizeof(dmc_samples));
}
static DWORD WINAPI dmc_sampler(void *arg) {
    (void)arg;
    static uint64_t stack[DMC_SCAN];
    HMODULE exe = GetModuleHandleA(NULL);
    const IMAGE_DOS_HEADER *dos = (const IMAGE_DOS_HEADER *)exe;
    const IMAGE_NT_HEADERS *nt = (const IMAGE_NT_HEADERS *)((const char *)exe + dos->e_lfanew);
    dmc_exe_lo = (uint64_t)(uintptr_t)exe;
    dmc_exe_hi = dmc_exe_lo + nt->OptionalHeader.SizeOfImage;
    uint64_t total = 0;
    ULONGLONG last = GetTickCount64();
    for (;;) {
        Sleep(1);
        pthread_mutex_lock(&lock);
        for (GuestThread *t = threads; t; t = t->next) {
            if (t->finished) continue;
            HANDLE h = (HANDLE)pthread_gethandle(t->host);
            if (!h || GetThreadId(h) == GetCurrentThreadId()) continue;
            if (SuspendThread(h) == (DWORD)-1) continue;
            CONTEXT c; memset(&c, 0, sizeof(c)); c.ContextFlags = CONTEXT_CONTROL;
            BOOL ok = GetThreadContext(h, &c);
            uint64_t host = 0, host2 = 0, guest = 0, guest2 = 0, guest3 = 0;
            if (ok) {
                SIZE_T got = 0;
                ReadProcessMemory(GetCurrentProcess(), (LPCVOID)(uintptr_t)c.Rsp, stack, sizeof(stack), &got);
                const uint64_t rip = c.Rip;
                if (rip >= dmc_exe_lo && rip < dmc_exe_hi) host = rip;
                if (dmc_is_guest_code(rip)) guest = rip;
                for (SIZE_T i = 0; i < got / 8 && (!host2 || !guest3); ++i) {
                    const uint64_t v = stack[i];
                    if (v >= dmc_exe_lo + 0x1000 && v < dmc_exe_hi && dmc_after_call(v)) {
                        if (!host) host = v; else if (!host2 && v != host) host2 = v;
                    } else if (dmc_is_guest_code(v) && dmc_after_call(v)) {
                        if (!guest) guest = v; else if (!guest2) guest2 = v; else if (!guest3) guest3 = v;
                    }
                }
            }
            ResumeThread(h);
            if (!ok) continue;
            const uint64_t rip = c.Rip;
            uint32_t hash = (uint32_t)(((rip ^ (host << 7) ^ (host2 << 3) ^ (guest << 13) ^ (guest2 << 17) ^ (guest3 << 21)) * 0x9E3779B97F4A7C15ull) >> 40);
            for (const char *q = t->name; *q; ++q) hash = hash * 31u + (unsigned char)*q;
            for (uint32_t i = 0; i < DMC_SLOTS; ++i) {
                DmcSample *e = &dmc_samples[(hash + i) % DMC_SLOTS];
                if (!e->count) { e->rip = rip; e->host = host; e->host2 = host2; e->guest = guest; e->guest2 = guest2; e->guest3 = guest3;
                                 snprintf(e->name, sizeof(e->name), "%s", t->name); }
                if (e->rip == rip && e->host == host && e->host2 == host2 && e->guest == guest && e->guest2 == guest2 && e->guest3 == guest3 &&
                    !strncmp(e->name, t->name, sizeof(e->name) - 1)) { ++e->count; break; }
            }
            ++total;
        }
        pthread_mutex_unlock(&lock);
        if (GetTickCount64() - last >= 5000) { dmc_report(total); total = 0; last = GetTickCount64(); }
    }
    return 0;
}
__attribute__((constructor)) static void dmc_sampler_start(void) {
    const char *env = getenv("BB_SAMPLE");
    if (env && env[0] == '1') {
        printf("Runtime: CPU sampler on (BB_SAMPLE=1): a report every 5 s\n");
        CreateThread(NULL, 0, dmc_sampler, NULL, 0, NULL);
    }
}
#endif
uintptr_t runtime_thread_resolve(const char *name) {
    static const struct { const char *nid; void *fn; } table[]={
        {"aI+OeCz8xrQ#libkernel",thread_self}, {"EotR8a3ASf4",thread_self},
        {"9BcDykPmo1I#libkernel",guest_error},
        {"nsYoNRywwNg#libkernel",attr_init}, {"62KCwEMmzcM#libkernel",attr_destroy},
        {"x1X76arYMxU#libkernel",attr_get}, {"8+s5BzZjxSg#libkernel",attr_affinity},
        {"UTXzJbWhhTE#libkernel",attr_set_stack}, {"-Wreprtu0Qs#libkernel",attr_set_detach},
        {"4+h9EzwKF4I#libkernel",attr_set_policy}, {"DzES9hQF4f4#libkernel",attr_set_param},
        {"3qxgM4ezETA#libkernel",attr_set_affinity}, {"eXbUSpEaTsA#libkernel",attr_set_inherit},
        {"JaRMy+QcpeU#libkernel",attr_get_detach}, {"-fA+7ZlGDQs#libkernel",attr_get_stack},
        {"FXPWHNk8Of0#libkernel",attr_get_param}, {"El+cQ20DynU#libkernel",attr_set_guard},
        {"6UgtwV+0zb4#libkernel",thread_create}, {"onNY9Byn-W8#libkernel",thread_join},
        {"4qGrR6eoP9Y#libkernel",thread_detach}, {"3kg7rT0NQIs#libkernel",thread_exit},
        {"T72hz6ffq08#libkernel",thread_yield}, {"1tKyG7RlMJo#libkernel",thread_get_prio},
        {"W0Hpm2X0uPE#libkernel",thread_set_prio}, {"bt3CTBKmGyI#libkernel",thread_set_affinity}, {"rcrVFJsQWRY#libkernel",thread_get_affinity},
        {"GBUY7ywdULE#libkernel",thread_rename}, {"3PtV6p3QNX4#libkernel",thread_equal},
        {"wtkt-teR1so",posix_attr_init}, {"zHchY8ft5pk",posix_attr_destroy},
        {"E+tyo3lp5Lw",posix_attr_set_detach}, {"2Q0z6rnBrTE",posix_attr_set_stack},
        {"euKRgm0Vn2M",posix_attr_set_param}, {"OxhIB8LB-PQ",posix_create},
        {"Jmi+9w9u0E4",posix_create_name}, {"h9CcP3J0oVM",posix_join},
        {"FJrT5LuUBAU",thread_exit},
        {"How7B8Oet6k#libkernel",thread_getname}, {"EI-5-jlq2dE#libkernel",thread_getthreadid}, {"qBDmpCyGssE#libkernel",thread_cancel},
        {"FIs3-UQT9sg",posix_getschedparam}, {"Xs9hdiD7sAA",posix_setschedparam},
        {"P41kTWUS3EI#libkernel",sce_getschedparam}, {"oIRFTjoILbg#libkernel",sce_setschedparam}, /* bbport-dmc */
    };
    for (size_t i=0;i<sizeof(table)/sizeof(*table);++i)
        if (runtime_nid_equals(name,table[i].nid)) return (uintptr_t)table[i].fn;
    return 0;
}
void runtime_thread_report(void) {
    pthread_mutex_lock(&lock);
    printf("Runtime: guest threads created=%zu, exited=%zu, joined=%zu\n",created,exited,joined_count);
    pthread_mutex_unlock(&lock);
}

