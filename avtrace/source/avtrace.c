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
 * avtrace 0.2: PS3AV transport trace for VSH 4.92, with an optional,
 * marker-selected rewrite of the native DVD-start batch.
 *
 * Load at runtime from the XMB through webMAN:
 *
 *   http://<ps3>/loadprx.ps3?prx=/dev_hdd0/tmp/avtrace.sprx
 *
 * It records every batch VSH sends to the AV controller (syscall 369) and
 * every non-empty reply VSH receives (syscall 368), with timestamps and raw
 * results.
 *
 * Without a rewrite marker it changes no byte that VSH sends or receives.
 * Capture 0002 showed that native DVD playback sends the XMB's AV MULTI RGB
 * batch with two words changed: VIDEO_MODE.video_out_format 0 -> 9 and
 * AV_VIDEO_CS cs_out/cs_in RGB8/RGB8 -> YUV444_8/YUV444_8.  A marker selects
 * a rewrite of exactly that batch, just before it is sent:
 *
 *   avtrace.rgb_full  restore both words (byte-identical to XMB RGB)
 *   avtrace.rgb_out   set cs_out to RGB8 only, keeping YUV444 input
 *
 * Boot-safety rules:
 *   - the disable marker is checked first;
 *   - nothing happens for START_DELAY_SECONDS after loading;
 *   - the only periodic work is a once-a-second drain of our own memory;
 *   - every risky step is logged before and after.
 *
 * Remove it by rebooting.  The receive path is observed after the call
 * returns, so no thread waits inside plugin code, but a reboot is still the
 * simplest guaranteed removal.
 */

SYS_MODULE_INFO(avtrace, 0, 0, 2);
SYS_MODULE_START(avtrace_start);
SYS_MODULE_STOP(avtrace_stop);

#define BUILD_START_LINE          "avtrace 0.2 starting"

#define LOG_PATH                  "/dev_hdd0/tmp/avtrace.log"
#define TRACE_PATH                "/dev_hdd0/tmp/avtrace.bin"
#define DISABLE_MARKER_PATH       "/dev_hdd0/tmp/avtrace.disable"
#define RGB_FULL_MARKER_PATH      "/dev_hdd0/tmp/avtrace.rgb_full"
#define RGB_OUT_MARKER_PATH       "/dev_hdd0/tmp/avtrace.rgb_out"

#define REWRITE_NONE              0u
#define REWRITE_RGB_FULL          1u
#define REWRITE_RGB_OUT           2u

#define START_DELAY_SECONDS       10u
#define DRAIN_INTERVAL_US         1000000u
#define TRACE_FILE_LIMIT          (8u * 1024u * 1024u)

#define WORKER_PRIORITY           3000
#define WORKER_STACK_SIZE         0x4000

/* VSH send wrapper: replaced by a branch to avtrace_send_hook. */
#define VSH_SEND_ADDRESS          0x005DED54u
#define VSH_SEND_ORIGINAL         0xFBA1FFE8u

/* Nop after the only call to the receive wrapper: replaced by a bl. */
#define VSH_RECV_SIGNATURE_ADDRESS 0x005DBF9Cu
#define VSH_RECV_PATCH_ADDRESS    0x005DBFA8u
#define VSH_RECV_PATCH_INDEX      3u
#define VSH_RECV_ORIGINAL         0x60000000u

#define SYSCALL8_OPCODE_PS3MAPI           0x7777u
#define PS3MAPI_OPCODE_SET_PROC_MEM       0x0032u
#define SYSCALL_DBG_WRITE_PROCESS_MEMORY  905u

#define TRACE_SLOT_COUNT          64u
#define TRACE_SLOT_MASK           (TRACE_SLOT_COUNT - 1u)
#define TRACE_DATA_MAX            2048u

#define KIND_SEND                 1u
#define KIND_RECV                 2u

typedef struct TraceSlot {
	volatile uint32_t sequence;
	volatile uint32_t kind;
	volatile uint64_t timebase;
	volatile uint32_t requested;
	volatile uint32_t result;
	volatile uint32_t copied;
	volatile uint32_t rewrite;
	volatile uint8_t data[TRACE_DATA_MAX];
} TraceSlot;

typedef struct TraceObserver {
	volatile uint32_t head;
	volatile uint32_t in_flight;
	volatile uint32_t recv_zero;
	volatile uint32_t recv_negative;
	volatile uint32_t recv_last_error;
	volatile uint32_t rewrite_mode;
	volatile uint32_t rewrites;
	volatile uint32_t pad[9];
	TraceSlot slots[TRACE_SLOT_COUNT];
} TraceObserver;

/* The assembly hard-codes these offsets. */
typedef char check_slot_size[(sizeof(TraceSlot) == 2080) ? 1 : -1];
typedef char check_slots_offset[
	(offsetof(TraceObserver, slots) == 64) ? 1 : -1];
typedef char check_mode_offset[
	(offsetof(TraceObserver, rewrite_mode) == 0x14 &&
	 offsetof(TraceObserver, rewrites) == 0x18) ? 1 : -1];

/* Exactly the 4.92 send wrapper, 0x005DED54 to 0x005DEDA4. */
static const uint32_t g_send_signature[] = {
	0xFBA1FFE8u, 0x7C0802A6u, 0x7C9D2378u, 0xF8010010u,
	0x38A00002u, 0x78840020u, 0x39600171u, 0x44000002u,
	0x7FBD1A78u, 0x3C008021u, 0x7FA9FE70u, 0x60000403u,
	0x7D23EA78u, 0xEBA1FFE8u, 0x7C634850u, 0x7C63FE70u,
	0x7C630038u, 0xE8010010u, 0x7C6307B4u, 0x7C0803A6u,
	0x4E800020u
};

/* The receive call site, 0x005DBF9C to 0x005DBFB4; index 3 is the nop. */
static const uint32_t g_recv_signature[] = {
	0x7AC30020u, 0x38800800u, 0x48002E05u, 0x60000000u,
	0x2F830000u, 0x7C7D1B78u, 0x409DFFE8u
};

/* The receive wrapper itself must also be unchanged. */
static const uint32_t g_recv_wrapper_signature[] = {
	0x78840020u, 0x7C0802A6u, 0x38A00001u, 0xF8010010u,
	0x39600170u, 0x44000002u, 0xE8010010u, 0x7C6307B4u,
	0x7C0803A6u, 0x4E800020u
};
#define VSH_RECV_WRAPPER_ADDRESS  0x005DEDA8u

extern const uint32_t avtrace_send_hook[];
extern const uint32_t avtrace_send_observer_hi[];
extern const uint32_t avtrace_send_observer_lo[];
extern const uint32_t avtrace_recv_hook[];
extern const uint32_t avtrace_recv_observer_hi[];
extern const uint32_t avtrace_recv_observer_lo[];

static TraceObserver g_observer __attribute__((aligned(128)));

static volatile int g_stop_requested = 0;
static sys_ppu_thread_t g_worker = SYS_PPU_THREAD_ID_INVALID;

static uint32_t g_send_branch = 0;
static uint32_t g_recv_branch = 0;
static int g_trace_file_full = 0;
static uint32_t g_trace_bytes = 0;

/* Reader-side scratch; only the worker thread uses it. */
static TraceSlot g_copy;

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

static void append_file(const char *path, const void *data, uint64_t size)
{
	int fd;
	uint64_t written;

	if (cellFsOpen(path,
	               CELL_FS_O_CREAT | CELL_FS_O_WRONLY | CELL_FS_O_APPEND,
	               &fd, NULL, 0) != CELL_FS_SUCCEEDED) {
		return;
	}
	cellFsWrite(fd, data, size, &written);
	cellFsClose(fd);
}

static void log_line(const char *message)
{
	char line[160];
	size_t length = strlen(message);

	if (length > sizeof(line) - 2) {
		length = sizeof(line) - 2;
	}
	memcpy(line, message, length);
	line[length++] = '\n';
	append_file(LOG_PATH, line, length);
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

static int words_match(uint32_t address, const uint32_t *expected,
	                   size_t count, size_t skip_index,
	                   uint32_t skip_value)
{
	size_t i;

	for (i = 0; i < count; ++i) {
		uint32_t actual = read_word(address + (uint32_t)(i * 4u));

		if (i == skip_index && skip_value != 0 && actual == skip_value) {
			continue;
		}
		if (actual != expected[i]) {
			return 0;
		}
	}
	return 1;
}

static int make_branch(uint32_t source, uint32_t target, int link,
	                   uint32_t *instruction)
{
	int64_t displacement = (int64_t)(uint64_t)target -
	                       (int64_t)(uint64_t)source;

	if ((displacement & 3) != 0 ||
	    displacement < -0x02000000LL ||
	    displacement > 0x01FFFFFCLL) {
		return -1;
	}

	*instruction = 0x48000000u |
	               ((uint32_t)displacement & 0x03FFFFFCu) |
	               (link ? 1u : 0u);
	return 0;
}

/* Patch "lis r11,hi / ori r11,r11,lo" in our own hook code. */
static int set_observer_pair(const uint32_t *hi_label,
	                         const uint32_t *lo_label,
	                         uint32_t observer)
{
	uint32_t hi_address = (uint32_t)(uintptr_t)hi_label;
	uint32_t lo_address = (uint32_t)(uintptr_t)lo_label;

	if ((read_word(hi_address) & 0xFFFF0000u) != 0x3D600000u ||
	    (read_word(lo_address) & 0xFFFF0000u) != 0x616B0000u) {
		return -1;
	}
	if (write_word(hi_address,
	               0x3D600000u | ((observer >> 16) & 0xFFFFu)) != 0 ||
	    write_word(lo_address,
	               0x616B0000u | (observer & 0xFFFFu)) != 0) {
		return -1;
	}
	return 0;
}

static int install_hooks(void)
{
	uint32_t observer = (uint32_t)(uintptr_t)&g_observer;
	uint32_t send_hook = (uint32_t)(uintptr_t)avtrace_send_hook;
	uint32_t recv_hook = (uint32_t)(uintptr_t)avtrace_recv_hook;
	uint32_t send_branch;
	uint32_t recv_branch;

	log_hex32("INFO: observer ", observer);
	log_hex32("INFO: send hook ", send_hook);
	log_hex32("INFO: receive hook ", recv_hook);

	log_line("STEP: checking 4.92 VSH send wrapper bytes");
	if (!words_match(VSH_SEND_ADDRESS, g_send_signature,
	                 sizeof(g_send_signature) / sizeof(g_send_signature[0]),
	                 (size_t)-1, 0)) {
		log_line("ERROR: send wrapper does not match 4.92; nothing installed");
		return -1;
	}
	log_line("STEP: checking 4.92 VSH receive call site and wrapper bytes");
	if (!words_match(VSH_RECV_SIGNATURE_ADDRESS, g_recv_signature,
	                 sizeof(g_recv_signature) / sizeof(g_recv_signature[0]),
	                 (size_t)-1, 0) ||
	    !words_match(VSH_RECV_WRAPPER_ADDRESS, g_recv_wrapper_signature,
	                 sizeof(g_recv_wrapper_signature) /
	                     sizeof(g_recv_wrapper_signature[0]),
	                 (size_t)-1, 0)) {
		log_line("ERROR: receive path does not match 4.92; nothing installed");
		return -1;
	}
	log_line("CHECK: all VSH signatures match");

	if (make_branch(VSH_SEND_ADDRESS, send_hook, 0, &send_branch) != 0 ||
	    make_branch(VSH_RECV_PATCH_ADDRESS, recv_hook, 1,
	                &recv_branch) != 0) {
		log_line("ERROR: hook is outside relative-branch range; nothing installed");
		return -1;
	}

	log_line("STEP: writing observer address into hook code");
	if (set_observer_pair(avtrace_send_observer_hi,
	                      avtrace_send_observer_lo, observer) != 0 ||
	    set_observer_pair(avtrace_recv_observer_hi,
	                      avtrace_recv_observer_lo, observer) != 0) {
		log_line("ERROR: could not prepare hook code; nothing installed");
		return -1;
	}
	log_line("CHECK: hook code prepared");

	log_hex32("STEP: writing receive observer bl ", recv_branch);
	if (write_word(VSH_RECV_PATCH_ADDRESS, recv_branch) != 0) {
		log_line("ERROR: receive observer write failed; nothing installed");
		return -1;
	}
	g_recv_branch = recv_branch;
	log_line("CHECK: receive observer installed");

	log_hex32("STEP: writing send branch ", send_branch);
	if (write_word(VSH_SEND_ADDRESS, send_branch) != 0) {
		log_line("ERROR: send hook write failed; removing receive observer");
		if (write_word(VSH_RECV_PATCH_ADDRESS, VSH_RECV_ORIGINAL) == 0) {
			g_recv_branch = 0;
			log_line("ROLLBACK: receive observer removed");
		} else {
			log_line("ERROR: receive observer could not be removed; reboot");
		}
		return -1;
	}
	g_send_branch = send_branch;
	log_line("CHECK: send hook installed");
	log_line("READY: tracing PS3AV send and receive");
	return 0;
}

static void remove_hooks(void)
{
	if (g_send_branch != 0) {
		if (read_word(VSH_SEND_ADDRESS) == g_send_branch &&
		    write_word(VSH_SEND_ADDRESS, VSH_SEND_ORIGINAL) == 0) {
			log_line("RESTORED: send wrapper");
		} else {
			log_line("ERROR: send wrapper not restored; reboot");
		}
		g_send_branch = 0;
	}

	if (g_recv_branch != 0) {
		if (read_word(VSH_RECV_PATCH_ADDRESS) == g_recv_branch &&
		    write_word(VSH_RECV_PATCH_ADDRESS, VSH_RECV_ORIGINAL) == 0) {
			log_line("RESTORED: receive call site");
		} else {
			log_line("ERROR: receive call site not restored; reboot");
		}
		g_recv_branch = 0;
	}
}

/* Text summary line for one record, for a quick look over FTP. */
static void log_record_summary(const TraceSlot *slot)
{
	static const char digits[] = "0123456789ABCDEF";
	char line[160];
	size_t n = 0;
	uint32_t i;
	const uint32_t fields[5] = {
		slot->sequence, slot->requested, slot->result, slot->copied,
		(uint32_t)(slot->timebase >> 8)
	};
	static const char *const names[5] = {
		" seq=", " req=", " res=", " copied=", " tb>>8="
	};

	memcpy(line + n, slot->kind == KIND_SEND ? "SEND" : "RECV", 4);
	n += 4;
	if (slot->rewrite != 0) {
		memcpy(line + n, " REWRITTEN", 10);
		n += 10;
		line[n++] = (char)('0' + (slot->rewrite & 7u));
	}
	for (i = 0; i < 5; ++i) {
		size_t name_length = strlen(names[i]);
		int shift;

		memcpy(line + n, names[i], name_length);
		n += name_length;
		for (shift = 28; shift >= 0; shift -= 4) {
			line[n++] = digits[(fields[i] >> shift) & 0x0Fu];
		}
	}

	memcpy(line + n, " data=", 6);
	n += 6;
	for (i = 0; i < slot->copied && i < 24u; ++i) {
		line[n++] = digits[slot->data[i] >> 4];
		line[n++] = digits[slot->data[i] & 0x0Fu];
	}
	line[n] = '\0';
	log_line(line);
}

static void write_record(const TraceSlot *slot)
{
	uint32_t length = 32u + ((slot->copied + 3u) & ~3u);

	log_record_summary(slot);

	if (g_trace_file_full) {
		return;
	}
	if (g_trace_bytes + length > TRACE_FILE_LIMIT) {
		g_trace_file_full = 1;
		log_line("TRACE: avtrace.bin reached its size limit; summaries continue");
		return;
	}
	append_file(TRACE_PATH, (const void *)slot, length);
	g_trace_bytes += length;
}

static void drain_trace(uint32_t *last_sequence, uint32_t *dropped)
{
	uint32_t current;

	memory_barrier();
	current = g_observer.head;

	if (current - *last_sequence > TRACE_SLOT_COUNT) {
		uint32_t skipped = current - *last_sequence - TRACE_SLOT_COUNT;

		*dropped += skipped;
		*last_sequence = current - TRACE_SLOT_COUNT;
		log_hex32("TRACE: ring overrun; records skipped ", skipped);
	}

	while (*last_sequence != current) {
		uint32_t expected = *last_sequence + 1u;
		const TraceSlot *source =
			&g_observer.slots[(expected - 1u) & TRACE_SLOT_MASK];
		uint32_t copied;

		memory_barrier();
		if (source->sequence != expected) {
			/* Reserved but not yet committed; try next second. */
			break;
		}

		copied = source->copied;
		if (copied > TRACE_DATA_MAX) {
			copied = TRACE_DATA_MAX;
		}
		g_copy.sequence = source->sequence;
		g_copy.kind = source->kind;
		g_copy.timebase = source->timebase;
		g_copy.requested = source->requested;
		g_copy.result = source->result;
		g_copy.copied = copied;
		g_copy.rewrite = source->rewrite;
		memcpy((void *)g_copy.data, (const void *)source->data, copied);
		memory_barrier();

		if (source->sequence != expected) {
			/* Overwritten while copying. */
			*dropped += 1u;
			*last_sequence = expected;
			continue;
		}

		write_record(&g_copy);
		*last_sequence = expected;
	}
}

static void write_trace_header(void)
{
	static const char header[16] = {
		'A', 'V', 'T', 'R', 'A', 'C', 'E', '1',
		0, 0, 0, 32, 0, 0, 0x08, 0x00
	};

	append_file(TRACE_PATH, header, sizeof(header));
	g_trace_bytes += sizeof(header);
}

static void worker_thread(uint64_t argument)
{
	uint32_t last_sequence = 0;
	uint32_t dropped = 0;
	uint32_t waited;

	(void)argument;
	log_line(BUILD_START_LINE);

	if (file_exists(DISABLE_MARKER_PATH)) {
		log_line("DISABLED: avtrace.disable is present; nothing installed");
		sys_ppu_thread_exit(0);
	}
	log_line("CHECK: disable marker absent");

	for (waited = 0; waited < START_DELAY_SECONDS && !g_stop_requested;
	     ++waited) {
		sys_timer_sleep(1);
	}
	if (g_stop_requested) {
		log_line("STOP: requested during start delay; nothing installed");
		sys_ppu_thread_exit(0);
	}

	memset((void *)&g_observer, 0, sizeof(g_observer));
	if (file_exists(RGB_FULL_MARKER_PATH)) {
		g_observer.rewrite_mode = REWRITE_RGB_FULL;
		log_line("MODE: rgb_full; DVD-start batch will be rewritten to XMB RGB bytes");
	} else if (file_exists(RGB_OUT_MARKER_PATH)) {
		g_observer.rewrite_mode = REWRITE_RGB_OUT;
		log_line("MODE: rgb_out; DVD-start AV_VIDEO_CS cs_out will be set to RGB8");
	} else {
		log_line("MODE: trace only; nothing is rewritten");
	}
	memory_barrier();
	write_trace_header();

	if (install_hooks() != 0) {
		sys_ppu_thread_exit(0);
	}

	while (!g_stop_requested) {
		sys_timer_usleep(DRAIN_INTERVAL_US);
		drain_trace(&last_sequence, &dropped);
	}

	remove_hooks();
	sys_timer_sleep(1);
	drain_trace(&last_sequence, &dropped);

	log_hex32("SUMMARY: records ", last_sequence);
	log_hex32("SUMMARY: records dropped ", dropped);
	log_hex32("SUMMARY: batches rewritten ", g_observer.rewrites);
	log_hex32("SUMMARY: empty receive results ", g_observer.recv_zero);
	log_hex32("SUMMARY: failed receive results ", g_observer.recv_negative);
	log_hex32("SUMMARY: last failed receive result ",
	          g_observer.recv_last_error);
	sys_ppu_thread_exit(0);
}

int avtrace_start(uint64_t argument)
{
	g_stop_requested = 0;
	if (sys_ppu_thread_create(&g_worker,
	                          worker_thread,
	                          argument,
	                          WORKER_PRIORITY,
	                          WORKER_STACK_SIZE,
	                          SYS_PPU_THREAD_CREATE_JOINABLE,
	                          "avtrace") != 0) {
		g_worker = SYS_PPU_THREAD_ID_INVALID;
	}

	module_thread_exit(0);
	return SYS_PRX_RESIDENT;
}

static volatile int g_stop_result = SYS_PRX_STOP_OK;

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
		remove_hooks();
	}

	/* Refuse to unload while any thread is still inside hook code. */
	for (waited = 0; waited < 50 && g_observer.in_flight != 0; ++waited) {
		sys_timer_usleep(100000);
	}
	if (g_observer.in_flight != 0) {
		log_line("ERROR: a thread is still inside hook code; unload refused, reboot instead");
		g_stop_result = SYS_PRX_STOP_FAILED;
	} else {
		log_line("STOPPED: hooks removed; safe to unload");
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

int avtrace_stop(void)
{
	sys_ppu_thread_t thread;
	uint64_t exit_code;

	if (sys_ppu_thread_create(&thread,
	                          stop_thread,
	                          0,
	                          0,
	                          0x2000,
	                          SYS_PPU_THREAD_CREATE_JOINABLE,
	                          "avtrace_stop") == 0) {
		sys_ppu_thread_join(thread, &exit_code);
	} else {
		g_stop_requested = 1;
		remove_hooks();
	}

	if (g_stop_result != SYS_PRX_STOP_OK) {
		module_thread_exit(0);
		return SYS_PRX_STOP_FAILED;
	}

	finalize_module();
	module_thread_exit(0);
	return SYS_PRX_STOP_OK;
}
