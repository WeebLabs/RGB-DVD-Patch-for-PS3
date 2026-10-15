#include <stdint.h>
#include <stddef.h>
#include <string.h>

#include <cell/cell_fs.h>
#include <sys/process.h>
#include <sys/prx.h>
#include <sys/ppu_thread.h>
#include <sys/syscall.h>
#include <sys/timer.h>

/*
 * disc_rgb_fix 2.0.1
 *
 * Keeps AV MULTI electrically RGB during native DVD playback on 4.92 CEX
 * (Evilnat / Cobra 8.5), by correcting one PS3AV batch just before VSH
 * sends it.  See logs/0002-dvd-playback and logs/0003-dvd-rgb-full.
 *
 * Native DVD playback sends the XMB's AV MULTI RGB batch with two words
 * changed: VIDEO_MODE.video_out_format 0 -> 9 and AV_VIDEO_CS cs_out/cs_in
 * RGB8/RGB8 -> YUV444_8/YUV444_8.  On AV MULTI, YUV444 out is a component
 * signal.  The send hook (rgbfix_hook.S) sets exactly that batch back to the
 * XMB RGB bytes.  Nothing else is changed.
 *
 * Boot-safety rules:
 *   - module start only creates one thread;
 *   - the thread checks the disable marker first;
 *   - it waits START_DELAY_SECONDS before touching VSH;
 *   - afterwards it only checks its own counter once a second;
 *   - every risky step is logged before and after.
 */

SYS_MODULE_INFO(disc_rgb_fix, 0, 2, 1);
SYS_MODULE_START(disc_rgb_fix_start);
SYS_MODULE_STOP(disc_rgb_fix_stop);

#define BUILD_START_LINE          "disc_rgb_fix 2.0.1 starting"

#define LOG_PATH                  "/dev_hdd0/tmp/disc_rgb_fix.log"
#define DISABLE_MARKER_PATH       "/dev_hdd0/tmp/disc_rgb_fix.disable"

#define START_DELAY_SECONDS       5u

#define WORKER_PRIORITY           3000
#define WORKER_STACK_SIZE         0x2000

/* VSH send wrapper: replaced by a branch to rgbfix_send_hook. */
#define VSH_SEND_ADDRESS          0x005DED54u
#define VSH_SEND_ORIGINAL         0xFBA1FFE8u

#define SYSCALL8_OPCODE_PS3MAPI           0x7777u
#define PS3MAPI_OPCODE_SET_PROC_MEM       0x0032u
#define SYSCALL_DBG_WRITE_PROCESS_MEMORY  905u

typedef struct FixObserver {
	volatile uint32_t in_flight;
	volatile uint32_t rewrites;
	volatile uint32_t last_result;
	volatile uint32_t pad[5];
} FixObserver;

/* The assembly hard-codes these offsets. */
typedef char check_observer_layout[
	(offsetof(FixObserver, rewrites) == 4 &&
	 offsetof(FixObserver, last_result) == 8) ? 1 : -1];

/* Exactly the 4.92 send wrapper, 0x005DED54 to 0x005DEDA4. */
static const uint32_t g_send_signature[] = {
	0xFBA1FFE8u, 0x7C0802A6u, 0x7C9D2378u, 0xF8010010u,
	0x38A00002u, 0x78840020u, 0x39600171u, 0x44000002u,
	0x7FBD1A78u, 0x3C008021u, 0x7FA9FE70u, 0x60000403u,
	0x7D23EA78u, 0xEBA1FFE8u, 0x7C634850u, 0x7C63FE70u,
	0x7C630038u, 0xE8010010u, 0x7C6307B4u, 0x7C0803A6u,
	0x4E800020u
};

extern const uint32_t rgbfix_send_hook[];
extern const uint32_t rgbfix_observer_hi[];
extern const uint32_t rgbfix_observer_lo[];

static FixObserver g_observer __attribute__((aligned(128)));

static volatile int g_stop_requested = 0;
static volatile int g_stop_result = SYS_PRX_STOP_OK;
static sys_ppu_thread_t g_worker = SYS_PPU_THREAD_ID_INVALID;
static uint32_t g_send_branch = 0;

static inline void module_thread_exit(uint64_t value)
{
	system_call_1(41, value);
}

static inline sys_prx_id_t module_id_from_address(const void *address)
{
	system_call_1(461, (uint64_t)(uint32_t)(uintptr_t)address);
	return (sys_prx_id_t)p1;
}

static inline void memory_barrier(void)
{
	__asm__ volatile("sync" : : : "memory");
}

static int file_exists(const char *path)
{
	CellFsStat stat;
	return cellFsStat(path, &stat) == CELL_FS_SUCCEEDED;
}

static void log_line(const char *message)
{
	char line[160];
	size_t length = strlen(message);
	int fd;
	uint64_t written;

	if (length > sizeof(line) - 2) {
		length = sizeof(line) - 2;
	}
	memcpy(line, message, length);
	line[length++] = '\n';

	if (cellFsOpen(LOG_PATH,
	               CELL_FS_O_CREAT | CELL_FS_O_WRONLY | CELL_FS_O_APPEND,
	               &fd, NULL, 0) != CELL_FS_SUCCEEDED) {
		return;
	}
	cellFsWrite(fd, line, length, &written);
	cellFsClose(fd);
}

static void log_hex32(const char *prefix, uint32_t value)
{
	static const char digits[] = "0123456789ABCDEF";
	char line[112];
	size_t prefix_length = strlen(prefix);
	size_t i;

	if (prefix_length > sizeof(line) - 11) {
		return;
	}
	memcpy(line, prefix, prefix_length);
	line[prefix_length++] = '0';
	line[prefix_length++] = 'x';
	for (i = 0; i < 8; ++i) {
		line[prefix_length + i] =
			digits[(value >> ((7 - i) * 4)) & 0x0Fu];
	}
	line[prefix_length + 8] = '\0';
	log_line(line);
}

static int ps3mapi_write_memory(uint32_t pid, uint32_t address,
	                            const void *source, uint32_t size)
{
	system_call_6(8,
	              SYSCALL8_OPCODE_PS3MAPI,
	              PS3MAPI_OPCODE_SET_PROC_MEM,
	              (uint64_t)pid,
	              (uint64_t)address,
	              (uint64_t)(uint32_t)(uintptr_t)source,
	              (uint64_t)size);
	return (int)p1;
}

static int debug_write_memory(uint32_t pid, uint32_t address,
	                          const void *source, uint32_t size)
{
	system_call_4(SYSCALL_DBG_WRITE_PROCESS_MEMORY,
	              (uint64_t)pid,
	              (uint64_t)address,
	              (uint64_t)size,
	              (uint64_t)(uint32_t)(uintptr_t)source);
	return (int)p1;
}

static uint32_t read_word(uint32_t address)
{
	return *(volatile const uint32_t *)(uintptr_t)address;
}

static void flush_instruction_word(uint32_t address)
{
	void *target = (void *)(uintptr_t)address;

	__asm__ volatile(
		"dcbst 0,%0\n"
		"sync\n"
		"icbi 0,%0\n"
		"isync\n"
		:
		: "r"(target)
		: "memory");
}

static int write_word(uint32_t address, uint32_t value)
{
	uint32_t pid = (uint32_t)sys_process_getpid();

	ps3mapi_write_memory(pid, address, &value, sizeof(value));
	flush_instruction_word(address);
	if (read_word(address) == value) {
		return 0;
	}

	debug_write_memory(pid, address, &value, sizeof(value));
	flush_instruction_word(address);
	if (read_word(address) == value) {
		return 0;
	}

	return -1;
}

static int send_wrapper_matches(void)
{
	size_t i;

	for (i = 0; i < sizeof(g_send_signature) / sizeof(g_send_signature[0]);
	     ++i) {
		if (read_word(VSH_SEND_ADDRESS + (uint32_t)(i * 4u)) !=
		    g_send_signature[i]) {
			return 0;
		}
	}
	return 1;
}

static int make_branch(uint32_t source, uint32_t target,
	                   uint32_t *instruction)
{
	int64_t displacement = (int64_t)(uint64_t)target -
	                       (int64_t)(uint64_t)source;

	if ((displacement & 3) != 0 ||
	    displacement < -0x02000000LL ||
	    displacement > 0x01FFFFFCLL) {
		return -1;
	}

	*instruction = 0x48000000u | ((uint32_t)displacement & 0x03FFFFFCu);
	return 0;
}

static int install_hook(void)
{
	uint32_t observer = (uint32_t)(uintptr_t)&g_observer;
	uint32_t hook = (uint32_t)(uintptr_t)rgbfix_send_hook;
	uint32_t hi_address = (uint32_t)(uintptr_t)rgbfix_observer_hi;
	uint32_t lo_address = (uint32_t)(uintptr_t)rgbfix_observer_lo;
	uint32_t branch;

	log_hex32("INFO: observer ", observer);
	log_hex32("INFO: send hook ", hook);

	log_line("STEP: checking 4.92 VSH send wrapper bytes");
	if (!send_wrapper_matches()) {
		log_line("ERROR: send wrapper does not match 4.92; nothing installed");
		return -1;
	}
	log_line("CHECK: send wrapper matches");

	if (make_branch(VSH_SEND_ADDRESS, hook, &branch) != 0) {
		log_line("ERROR: hook is outside relative-branch range; nothing installed");
		return -1;
	}

	log_line("STEP: writing observer address into hook code");
	if ((read_word(hi_address) & 0xFFFF0000u) != 0x3D600000u ||
	    (read_word(lo_address) & 0xFFFF0000u) != 0x616B0000u ||
	    write_word(hi_address,
	               0x3D600000u | ((observer >> 16) & 0xFFFFu)) != 0 ||
	    write_word(lo_address,
	               0x616B0000u | (observer & 0xFFFFu)) != 0) {
		log_line("ERROR: could not prepare hook code; nothing installed");
		return -1;
	}
	log_line("CHECK: hook code prepared");

	log_hex32("STEP: writing send branch ", branch);
	if (write_word(VSH_SEND_ADDRESS, branch) != 0) {
		log_line("ERROR: send branch write failed; nothing installed");
		return -1;
	}
	g_send_branch = branch;
	log_line("READY: DVD-start AV MULTI batch will be kept RGB");
	return 0;
}

static void remove_hook(void)
{
	if (g_send_branch == 0) {
		return;
	}
	if (read_word(VSH_SEND_ADDRESS) == g_send_branch &&
	    write_word(VSH_SEND_ADDRESS, VSH_SEND_ORIGINAL) == 0) {
		log_line("RESTORED: send wrapper");
	} else {
		log_line("ERROR: send wrapper not restored; reboot");
	}
	g_send_branch = 0;
}

static void worker_thread(uint64_t argument)
{
	uint32_t waited;
	uint32_t logged_rewrites = 0;

	(void)argument;
	log_line(BUILD_START_LINE);

	if (file_exists(DISABLE_MARKER_PATH)) {
		log_line("DISABLED: disc_rgb_fix.disable is present; nothing installed");
		sys_ppu_thread_exit(0);
	}
	log_line("CHECK: disable marker absent");
	log_line("WAIT: letting the XMB finish starting");

	for (waited = 0; waited < START_DELAY_SECONDS && !g_stop_requested;
	     ++waited) {
		sys_timer_sleep(1);
	}
	if (g_stop_requested) {
		log_line("STOP: requested during start delay; nothing installed");
		sys_ppu_thread_exit(0);
	}

	memset((void *)&g_observer, 0, sizeof(g_observer));
	memory_barrier();

	if (install_hook() != 0) {
		sys_ppu_thread_exit(0);
	}

	while (!g_stop_requested) {
		uint32_t rewrites;

		sys_timer_sleep(1);
		memory_barrier();
		rewrites = g_observer.rewrites;
		if (rewrites != logged_rewrites) {
			log_hex32("REWRITE: DVD-start batch kept RGB; total ", rewrites);
			log_hex32("REWRITE: send result (0x74 = accepted) ",
			          g_observer.last_result);
			logged_rewrites = rewrites;
		}
	}

	remove_hook();
	sys_ppu_thread_exit(0);
}

int disc_rgb_fix_start(uint64_t argument)
{
	g_stop_requested = 0;
	if (sys_ppu_thread_create(&g_worker,
	                          worker_thread,
	                          argument,
	                          WORKER_PRIORITY,
	                          WORKER_STACK_SIZE,
	                          SYS_PPU_THREAD_CREATE_JOINABLE,
	                          "disc_rgb_fix") != 0) {
		g_worker = SYS_PPU_THREAD_ID_INVALID;
	}

	module_thread_exit(0);
	return SYS_PRX_RESIDENT;
}

static void stop_thread(uint64_t argument)
{
	uint64_t exit_code;
	int waited;

	(void)argument;
	g_stop_requested = 1;

	if (g_worker != SYS_PPU_THREAD_ID_INVALID) {
		sys_ppu_thread_join(g_worker, &exit_code);
		g_worker = SYS_PPU_THREAD_ID_INVALID;
	} else {
		remove_hook();
	}

	/* Refuse to unload while any thread is still inside hook code. */
	sys_timer_usleep(200000);
	for (waited = 0; waited < 50 && g_observer.in_flight != 0; ++waited) {
		sys_timer_usleep(100000);
	}
	if (g_observer.in_flight != 0) {
		log_line("ERROR: a thread is still inside hook code; unload refused, reboot instead");
		g_stop_result = SYS_PRX_STOP_FAILED;
	} else {
		log_line("STOPPED: hook removed; safe to unload");
	}

	sys_ppu_thread_exit(0);
}

static void finalize_module(void)
{
	uint64_t meminfo[5] = { 0x28, 2, 0, 0, 0 };
	sys_prx_id_t module_id = module_id_from_address(finalize_module);

	system_call_3(482,
	              (uint64_t)module_id,
	              0,
	              (uint64_t)(uint32_t)(uintptr_t)meminfo);
}

int disc_rgb_fix_stop(void)
{
	sys_ppu_thread_t thread;
	uint64_t exit_code;

	if (sys_ppu_thread_create(&thread,
	                          stop_thread,
	                          0,
	                          0,
	                          0x2000,
	                          SYS_PPU_THREAD_CREATE_JOINABLE,
	                          "disc_rgb_stop") == 0) {
		sys_ppu_thread_join(thread, &exit_code);
	} else {
		g_stop_requested = 1;
		remove_hook();
	}

	if (g_stop_result != SYS_PRX_STOP_OK) {
		module_thread_exit(0);
		return SYS_PRX_STOP_FAILED;
	}

	finalize_module();
	module_thread_exit(0);
	return SYS_PRX_STOP_OK;
}
