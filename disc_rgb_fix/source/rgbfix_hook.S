/*
 * disc_rgb_fix 2.0 send hook for the 4.92 VSH PS3AV transport.
 *
 * Observer layout (see FixObserver in disc_rgb_fix.c):
 *
 *   +0x00  in_flight     threads currently inside the hook
 *   +0x04  rewrites      DVD-start batches rewritten
 *   +0x08  last_result   raw syscall 369 result for the last rewritten batch
 *
 * Complete replacement for the VSH send wrapper at 0x005DED54, entered by a
 * plain branch written over its first instruction.  The caller's bl set LR,
 * so this returns directly to the caller.
 *
 *   r3 = batch buffer, r4 = batch length
 *
 * Behaviour is identical to the original wrapper (syscall 369 with r5 = 2,
 * return 0 if the result equals the length, else 0x80210403), except for
 * one batch.  Native DVD playback starts with the XMB's AV MULTI RGB batch
 * carrying two changed words (captures 0002/0003):
 *
 *   +0x30  VIDEO_MODE.video_out_format        0          -> 9
 *   +0x4C  AV_VIDEO_CS av_cs_out, av_cs_in    RGB8/RGB8  -> YUV444_8/YUV444_8
 *
 * Only an exact AVB_PARAM batch {VIDEO_MODE head 1, out_format 9;
 * AV_VIDEO_CS AVMULTI, YUV444_8/YUV444_8} is touched, and both words are
 * set back to 0, making it byte-identical to the XMB RGB batch.
 *
 * No function is called.
 */

	.section ".text.rgbfix_send_hook","ax",@progbits
	.align 2

	.globl rgbfix_send_hook
	.type rgbfix_send_hook,@function
rgbfix_send_hook:
	stdu    1,-160(1)
	mflr    0
	std     0,176(1)
	std     28,120(1)
	std     29,128(1)
	std     30,136(1)
	std     31,144(1)

	mr      29,4
	mr      28,3

	.globl rgbfix_observer_hi
rgbfix_observer_hi:
	lis     11,0

	.globl rgbfix_observer_lo
rgbfix_observer_lo:
	ori     11,11,0

	mr      30,11
	li      31,0

.Lenter:
	lwarx   9,0,30
	addi    9,9,1
	stwcx.  9,0,30
	bne-    .Lenter

	clrldi  9,29,32
	cmplwi  7,9,0x50
	blt     7,.Lsend
	clrldi  10,28,32

	lwz     9,0(10)
	lis     0,0x0205
	ori     0,0,0x0054
	cmpw    7,9,0
	bne     7,.Lsend
	lwz     9,4(10)
	lis     0,0x0400
	ori     0,0,0x0001
	cmpw    7,9,0
	bne     7,.Lsend
	lwz     9,8(10)
	lis     0,0x0001
	cmpw    7,9,0
	bne     7,.Lsend
	lwz     9,12(10)
	cmpw    7,9,0
	bne     7,.Lsend
	lwz     9,16(10)
	lis     0,0x0205
	ori     0,0,0x002c
	cmpw    7,9,0
	bne     7,.Lsend
	lwz     9,20(10)
	lis     0,0x0100
	ori     0,0,0x0002
	cmpw    7,9,0
	bne     7,.Lsend
	lwz     9,24(10)
	cmpwi   7,9,1
	bne     7,.Lsend
	lwz     9,48(10)
	cmpwi   7,9,9
	bne     7,.Lsend
	lwz     9,64(10)
	lis     0,0x0205
	ori     0,0,0x0014
	cmpw    7,9,0
	bne     7,.Lsend
	lwz     9,68(10)
	lis     0,0x0001
	ori     0,0,0x0001
	cmpw    7,9,0
	bne     7,.Lsend
	lhz     9,72(10)
	cmpwi   7,9,0x10
	bne     7,.Lsend
	lwz     9,76(10)
	cmpw    7,9,0
	bne     7,.Lsend

	li      0,0
	stw     0,48(10)
	stw     0,76(10)
	li      31,1

	addi    10,30,4
.Lcount:
	lwarx   9,0,10
	addi    9,9,1
	stwcx.  9,0,10
	bne-    .Lcount

.Lsend:
	mr      3,28
	mr      4,29
	li      5,2
	clrldi  4,4,32
	li      11,369
	sc

	cmpwi   7,31,0
	beq     7,.Lleave
	stw     3,8(30)

.Lleave:
	lwarx   9,0,30
	addi    9,9,-1
	stwcx.  9,0,30
	bne-    .Lleave

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
	ld      28,120(1)
	ld      29,128(1)
	ld      30,136(1)
	ld      31,144(1)
	addi    1,1,160
	blr

	.size rgbfix_send_hook,.-rgbfix_send_hook
