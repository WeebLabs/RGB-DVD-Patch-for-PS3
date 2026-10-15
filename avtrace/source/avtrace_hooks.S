/*
 * avtrace record-only hooks for the 4.92 VSH PS3AV transport.
 *
 * Observer layout (see TraceObserver in avtrace.c):
 *
 *   +0x00  head            sequence counter, reserved with lwarx/stwcx.
 *   +0x04  in_flight       threads currently inside a hook
 *   +0x08  recv_zero       receive calls that returned 0 bytes
 *   +0x0C  recv_negative   receive calls that returned an error
 *   +0x10  recv_last_error last negative receive result
 *   +0x14  rewrite_mode    0 = trace only, 1 = full XMB RGB, 2 = cs_out only
 *   +0x18  rewrites        DVD-start batches rewritten
 *   +0x40  slots[64]       2080 bytes each
 *
 * Slot layout:
 *
 *   +0x00  sequence        0 while being written, committed last
 *   +0x04  kind            1 = send, 2 = receive
 *   +0x08  timebase        mftb when the record was started
 *   +0x10  requested       send length or receive capacity
 *   +0x14  result          raw syscall result (send: 0xFFFFFFFF until done)
 *   +0x18  copied          bytes copied into data, at most 2048
 *   +0x1C  rewrite         rewrite mode applied to this batch, else 0
 *   +0x20  data[2048]      bytes as actually sent
 *
 * Neither hook calls a function.  With rewrite_mode 0, neither changes any
 * byte that VSH sends or receives.
 */

#define TRACE_SLOT_SIZE   2080
#define TRACE_SLOT_MASK   63
#define TRACE_SLOTS_BASE  64
#define TRACE_DATA_MAX    2048


	.section ".text.avtrace_send_hook","ax",@progbits
	.align 2

	/*
	 * Complete replacement for the VSH send wrapper at 0x005DED54, entered
	 * by a plain branch written over its first instruction.  The caller's
	 * bl set LR, so this returns directly to the caller.
	 *
	 *   r3 = batch buffer, r4 = batch length
	 *
	 * Behaviour is identical to the original: syscall 369 with r5 = 2, then
	 * return 0 if the syscall result equals the length, else 0x80210403.
	 * The batch is copied before the syscall and the raw result after it.
	 */
	.globl avtrace_send_hook
	.type avtrace_send_hook,@function
avtrace_send_hook:
	stdu    1,-160(1)
	mflr    0
	std     0,176(1)
	std     27,112(1)
	std     28,120(1)
	std     29,128(1)
	std     30,136(1)
	std     31,144(1)

	mr      29,4
	mr      28,3

	.globl avtrace_send_observer_hi
avtrace_send_observer_hi:
	lis     11,0

	.globl avtrace_send_observer_lo
avtrace_send_observer_lo:
	ori     11,11,0

	mr      30,11

	addi    10,30,4
.Lsend_enter:
	lwarx   9,0,10
	addi    9,9,1
	stwcx.  9,0,10
	bne-    .Lsend_enter

.Lsend_reserve:
	lwarx   27,0,30
	addi    27,27,1
	stwcx.  27,0,30
	bne-    .Lsend_reserve

	addi    9,27,-1
	andi.   9,9,TRACE_SLOT_MASK
	mulli   9,9,TRACE_SLOT_SIZE
	addi    9,9,TRACE_SLOTS_BASE
	add     31,9,30

	li      0,0
	stw     0,0(31)
	li      0,1
	stw     0,4(31)
	mftb    0
	std     0,8(31)
	stw     29,16(31)
	li      0,-1
	stw     0,20(31)
	li      0,0
	stw     0,28(31)

	/*
	 * Optional DVD-start rewrite (observer +0x14 = mode, 0 = trace only).
	 * Only an exact AVB_PARAM batch {VIDEO_MODE head 1, out_format 9;
	 * AV_VIDEO_CS AVMULTI, cs_out YUV444_8, cs_in YUV444_8} is touched.
	 *   mode 1: out_format 9 -> 0 and cs 0x00010001 -> 0 (XMB RGB bytes)
	 *   mode 2: cs 0x00010001 -> 0x00000001 (cs_out RGB8 only)
	 * The slot's reserved word records the mode applied.
	 */
	lwz     7,20(30)
	cmpwi   7,7,0
	beq     7,.Lsend_no_rewrite
	clrldi  9,29,32
	cmplwi  7,9,0x50
	blt     7,.Lsend_no_rewrite
	clrldi  10,28,32

	lwz     9,0(10)
	lis     0,0x0205
	ori     0,0,0x0054
	cmpw    7,9,0
	bne     7,.Lsend_no_rewrite
	lwz     9,4(10)
	lis     0,0x0400
	ori     0,0,0x0001
	cmpw    7,9,0
	bne     7,.Lsend_no_rewrite
	lwz     9,8(10)
	lis     0,0x0001
	cmpw    7,9,0
	bne     7,.Lsend_no_rewrite
	lwz     9,12(10)
	cmpw    7,9,0
	bne     7,.Lsend_no_rewrite
	lwz     9,16(10)
	lis     0,0x0205
	ori     0,0,0x002c
	cmpw    7,9,0
	bne     7,.Lsend_no_rewrite
	lwz     9,20(10)
	lis     0,0x0100
	ori     0,0,0x0002
	cmpw    7,9,0
	bne     7,.Lsend_no_rewrite
	lwz     9,24(10)
	cmpwi   7,9,1
	bne     7,.Lsend_no_rewrite
	lwz     9,48(10)
	cmpwi   7,9,9
	bne     7,.Lsend_no_rewrite
	lwz     9,64(10)
	lis     0,0x0205
	ori     0,0,0x0014
	cmpw    7,9,0
	bne     7,.Lsend_no_rewrite
	lwz     9,68(10)
	lis     0,0x0001
	ori     0,0,0x0001
	cmpw    7,9,0
	bne     7,.Lsend_no_rewrite
	lhz     9,72(10)
	cmpwi   7,9,0x10
	bne     7,.Lsend_no_rewrite
	lwz     9,76(10)
	cmpw    7,9,0
	bne     7,.Lsend_no_rewrite

	cmpwi   7,7,1
	bne     7,.Lsend_rewrite_out_only
	li      0,0
	stw     0,48(10)
	stw     0,76(10)
	b       .Lsend_rewritten
.Lsend_rewrite_out_only:
	cmpwi   7,7,2
	bne     7,.Lsend_no_rewrite
	li      0,1
	stw     0,76(10)
.Lsend_rewritten:
	stw     7,28(31)
	addi    10,30,24
.Lsend_count_rewrite:
	lwarx   9,0,10
	addi    9,9,1
	stwcx.  9,0,10
	bne-    .Lsend_count_rewrite

.Lsend_no_rewrite:
	clrldi  8,29,32
	cmplwi  7,8,TRACE_DATA_MAX
	ble     7,.Lsend_length_ok
	li      8,TRACE_DATA_MAX
.Lsend_length_ok:
	stw     8,24(31)

	cmpwi   7,8,0
	beq     7,.Lsend_syscall
	clrldi  10,28,32
	addi    9,31,32
	mtctr   8
.Lsend_copy:
	lbz     0,0(10)
	stb     0,0(9)
	addi    10,10,1
	addi    9,9,1
	bdnz    .Lsend_copy

.Lsend_syscall:
	mr      3,28
	mr      4,29
	li      5,2
	clrldi  4,4,32
	li      11,369
	sc

	stw     3,20(31)
	lwsync
	stw     27,0(31)

	addi    10,30,4
.Lsend_leave:
	lwarx   9,0,10
	addi    9,9,-1
	stwcx.  9,0,10
	bne-    .Lsend_leave

	/* Original result mapping from 0x005DED74. */
	xor     29,29,3
	lis     0,-32735
	srawi   9,29,31
	ori     0,0,1027
	xor     3,9,29
	subf    3,3,9
	srawi   3,3,31
	and     3,3,0
	extsw   3,3

	ld      0,176(1)
	mtlr    0
	ld      27,112(1)
	ld      28,120(1)
	ld      29,128(1)
	ld      30,136(1)
	ld      31,144(1)
	addi    1,1,160
	blr

	.size avtrace_send_hook,.-avtrace_send_hook


	.section ".text.avtrace_recv_hook","ax",@progbits
	.align 2

	/*
	 * Observer called by a bl written over the nop at 0x005DBFA8, directly
	 * after the receive wrapper returns to its only caller.
	 *
	 *   r3  = receive result (already sign-extended by the wrapper)
	 *   r22 = receive buffer (capacity 2048 at this call site)
	 *
	 * Positive results are recorded with their bytes.  Zero and negative
	 * results are only counted, so an empty polling loop cannot flood the
	 * ring.  Every register except LR is restored; LR is dead here because
	 * the caller reloads it from its own frame.
	 */
	.globl avtrace_recv_hook
	.type avtrace_recv_hook,@function
avtrace_recv_hook:
	stdu    1,-208(1)
	std     0,112(1)
	std     3,120(1)
	std     4,128(1)
	std     5,136(1)
	std     6,144(1)
	std     7,152(1)
	std     8,160(1)
	std     9,168(1)
	std     10,176(1)
	std     11,184(1)
	mfcr    0
	std     0,192(1)
	mfctr   0
	std     0,200(1)

	.globl avtrace_recv_observer_hi
avtrace_recv_observer_hi:
	lis     11,0

	.globl avtrace_recv_observer_lo
avtrace_recv_observer_lo:
	ori     11,11,0

	addi    10,11,4
.Lrecv_enter:
	lwarx   9,0,10
	addi    9,9,1
	stwcx.  9,0,10
	bne-    .Lrecv_enter

	extsw   8,3
	cmpwi   7,8,0
	bgt     7,.Lrecv_record
	blt     7,.Lrecv_error
	addi    10,11,8
	b       .Lrecv_count
.Lrecv_error:
	stw     8,16(11)
	addi    10,11,12
.Lrecv_count:
	lwarx   9,0,10
	addi    9,9,1
	stwcx.  9,0,10
	bne-    .Lrecv_count
	b       .Lrecv_leave

.Lrecv_record:
	lwarx   7,0,11
	addi    7,7,1
	stwcx.  7,0,11
	bne-    .Lrecv_record

	addi    9,7,-1
	andi.   9,9,TRACE_SLOT_MASK
	mulli   9,9,TRACE_SLOT_SIZE
	addi    9,9,TRACE_SLOTS_BASE
	add     6,9,11

	li      0,0
	stw     0,0(6)
	li      0,2
	stw     0,4(6)
	mftb    0
	std     0,8(6)
	li      0,TRACE_DATA_MAX
	stw     0,16(6)
	stw     8,20(6)

	mr      5,8
	cmplwi  7,5,TRACE_DATA_MAX
	ble     7,.Lrecv_length_ok
	li      5,TRACE_DATA_MAX
.Lrecv_length_ok:
	stw     5,24(6)
	li      0,0
	stw     0,28(6)

	clrldi  10,22,32
	addi    9,6,32
	mtctr   5
.Lrecv_copy:
	lbz     0,0(10)
	stb     0,0(9)
	addi    10,10,1
	addi    9,9,1
	bdnz    .Lrecv_copy

	lwsync
	stw     7,0(6)

.Lrecv_leave:
	addi    10,11,4
.Lrecv_leave_loop:
	lwarx   9,0,10
	addi    9,9,-1
	stwcx.  9,0,10
	bne-    .Lrecv_leave_loop

	ld      0,200(1)
	mtctr   0
	ld      0,192(1)
	mtcrf   0xff,0
	ld      11,184(1)
	ld      10,176(1)
	ld      9,168(1)
	ld      8,160(1)
	ld      7,152(1)
	ld      6,144(1)
	ld      5,136(1)
	ld      4,128(1)
	ld      3,120(1)
	ld      0,112(1)
	addi    1,1,208
	blr

	.size avtrace_recv_hook,.-avtrace_recv_hook
