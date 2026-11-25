; Gramma NES startup and NMI for cc65 2.19.
;
; Based on cc65's V2.19 NES crt0, with two deliberate changes: the NMI writes
; Gramma's fine-scroll values to $2005, and the iNES header / startup mapper
; programming are parameterised by the build driver via -D symbols. Coarse
; scrolling remains a nametable-column rewrite in nes_backend.c.
;
; GR_NES_MAPPER    = 0 (NROM), 1 (MMC1) or 4 (MMC3)
; GR_NES_PRG_BANKS = iNES header value (16 KB units for every mapper)
; GR_NES_CHR_BANKS = iNES header value (8 KB units)

        .export         _exit
        .export         __STARTUP__ : absolute = 1      ; Mark as startup

        .import         initlib, donelib, callmain
        .import         push0, _main, zerobss, copydata
        .import         ppubuf_flush

        ; Linker-generated symbols
        .import         __RAM_START__, __RAM_SIZE__
        .import         __SRAM_START__, __SRAM_SIZE__
        .import         __ROM0_START__, __ROM0_SIZE__
        .import         __STARTUP_LOAD__, __STARTUP_RUN__, __STARTUP_SIZE__
        .import         __CODE_LOAD__, __CODE_RUN__, __CODE_SIZE__
        .import         __RODATA_LOAD__, __RODATA_RUN__, __RODATA_SIZE__
        .ifdef GR_NES_RAMCODE
        .import         __RAMCODE_LOAD__, __RAMCODE_RUN__, __RAMCODE_SIZE__
        .endif

        ; Keep cc65's forced font import satisfied without spending CHR.
        .forceimport    NESfont

        .include        "zeropage.inc"
        .include        "nes.inc"

; Mapper configuration defaults (the build driver overrides all three).
        .ifdef GR_NES_MAPPER
GR_MAPPER = GR_NES_MAPPER
        .else
GR_MAPPER = 0
        .endif

        .ifdef GR_NES_PRG_BANKS
GR_PRG_BANKS = GR_NES_PRG_BANKS
        .else
GR_PRG_BANKS = 2
        .endif
        .ifdef GR_NES_CHR_BANKS
GR_CHR_BANKS = GR_NES_CHR_BANKS
        .else
GR_CHR_BANKS = 1
        .endif

; Export mapper configuration as real ROM bytes. Absolute symbols would be
; treated by C as addresses, not values, so the bytes must live in a PRG
; segment.
        .segment "RODATA"
        .export _gr_nes_mapper_id
_gr_nes_mapper_id:
        .byte GR_MAPPER
        .export _gr_nes_prg_banks
_gr_nes_prg_banks:
        .byte GR_PRG_BANKS
        .segment "STARTUP"

; Gramma-owned scroll bytes. $7EE0/$7EE1 are outside cc65's parameter stack
; ($0500-$07FF) and outside the OAM DMA page at $7F00.
NES_SCROLL_X    = $7EE0
NES_SCROLL_Y    = $7EE1

; ------------------------------------------------------------------------
; iNES/NES 2.0 header: mapper and bank counts come from project.toml. Counts
; above 15 need NES 2.0 because the original iNES bank-count fields are only
; four bits.
; ------------------------------------------------------------------------

.segment        "HEADER"

; NES 2.0 identifier is bits 3..2 of byte 7. Bytes 8/9 hold the PRG/CHR count
; MSBs in their high nibbles.
.if (GR_PRG_BANKS > 15) .or (GR_CHR_BANKS > 15)
GR_FORMAT_VERSION = 2
; NES 2.0 byte 10: 64 << 7 = 8 KB of PRG RAM, which cc65 uses for RAM.
GR_PRG_RAM = $07
.else
GR_FORMAT_VERSION = 0
GR_PRG_RAM = 0
.endif
.if GR_PRG_BANKS > 15
GR_PRG_MSB = ((GR_PRG_BANKS >> 4) & $0f) << 4
GR_PRG_HEADER = GR_PRG_BANKS & $0f
.else
GR_PRG_MSB = 0
GR_PRG_HEADER = GR_PRG_BANKS
.endif
.if GR_CHR_BANKS > 15
GR_CHR_MSB = ((GR_CHR_BANKS >> 4) & $0f) << 4
GR_CHR_HEADER = GR_CHR_BANKS & $0f
.else
GR_CHR_MSB = 0
GR_CHR_HEADER = GR_CHR_BANKS
.endif

        .byte   $4e,$45,$53,$1a
        .byte   GR_PRG_HEADER
        .byte   GR_CHR_HEADER
        .byte   ((GR_MAPPER & $0f) << 4) | $03 ; low mapper + vertical mirror
        .byte   (GR_FORMAT_VERSION << 2) | ((GR_MAPPER >> 4) & $0f)
        .byte   GR_PRG_MSB              ; byte 8: PRG size MSB (NES 2.0)
        .byte   GR_CHR_MSB              ; byte 9: CHR size MSB (NES 2.0)
        .byte   GR_PRG_RAM              ; byte 10: PRG RAM size
        .byte   0,0,0,0,0

; ------------------------------------------------------------------------
; Startup
; ------------------------------------------------------------------------

.segment        "STARTUP"

start:
        sei
        cld
        ldx     #$00
        stx     VBLANK_FLAG
        stx     ringread
        stx     ringwrite
        stx     ringcount
        stx     NES_SCROLL_X
        stx     NES_SCROLL_Y
        txs

        jsr     mapper_init     ; program MMC1/MMC3 before any banked code runs

        lda     #$20
@l:     sta     ringbuff,x
        sta     ringbuff+$0100,x
        sta     ringbuff+$0200,x
        inx
        bne     @l

        jsr     zerobss
        jsr     copydata

        .ifdef GR_NES_RAMCODE
        ; Copy the banked-PRG reader into RAM before main() can call it.
        lda     #<__RAMCODE_LOAD__
        sta     ptr1
        lda     #>__RAMCODE_LOAD__
        sta     ptr1+1
        lda     #<__RAMCODE_RUN__
        sta     ptr2
        lda     #>__RAMCODE_RUN__
        sta     ptr2+1
        ldx     #$04
@ramcode_page:
        ldy     #$00
@ramcode_byte:
        lda     (ptr1),y
        sta     (ptr2),y
        iny
        bne     @ramcode_byte
        inc     ptr1+1
        inc     ptr2+1
        dex
        bne     @ramcode_page
        .endif

        lda     #<(__SRAM_START__ + __SRAM_SIZE__)
        ldx     #>(__SRAM_START__ + __SRAM_SIZE__)
        sta     sp
        stx     sp+1

        jsr     initlib
        jsr     callmain

_exit:  jsr     donelib
        jmp     start

; ------------------------------------------------------------------------
; Mapper programming. Code is linked into the final two 16 KB PRG banks;
; earlier banks are data-only. The startup registers select the code banks so
; cc65's $8000-$FFFF layout stays intact.
;
; MMC1: control $1E (vertical, 16 KB upper-fixed PRG, 4 KB CHR), PRG bank N-2.
; MMC3: PRG mode 0 with R6/R7 = 2*(N-2), 2*(N-2)+1; 4 KB CHR mode.
; ------------------------------------------------------------------------

; Emit the five MMC1 serial bits for one register. The fifth write commits
; `value`; bit 7 on the first write resets the shift register.
.macro MMC1_SERIAL reg, value
        lda     #$80
        sta     reg
        .repeat 5, bit_index
        lda     #((value >> bit_index) & $01)
        sta     reg
        .endrepeat
.endmacro

GR_PRG_CODE_BANK = 2 * (GR_PRG_BANKS - 2)
GR_PRG_CODE_BANK2 = GR_PRG_CODE_BANK + 1

mapper_init:
        .if GR_MAPPER = 1
        ; Control $1E: vertical mirroring, 16 KB upper-fixed PRG, 4 KB CHR.
        MMC1_SERIAL $8000, $1e
        ; The switchable lower window must show the code bank (N-2).
        MMC1_SERIAL $a000, (GR_PRG_BANKS - 2)
        ; CHR banks 0 for both pattern tables.
        MMC1_SERIAL $c000, $00
        MMC1_SERIAL $e000, $00
        .elseif GR_MAPPER = 4
        ; $E000 is the IRQ disable register, not mode control. PRG/CHR mode
        ; lives in bits 6/7 of every $8000 bank-select write: bit7=1 selects
        ; 4 KB CHR banks, bit6=0 selects PRG mode 0. All eight registers are
        ; programmed so both pattern tables map to the full 8 KB CHR ROM:
        ;   R0/R1 (2 KB) -> PPU $1000-$1FFF (background) = CHR $0000-$0FFF
        ;   R2-R5 (1 KB) -> PPU $0000-$0FFF (sprites)     = CHR $0000-$0FFF
        ;   R6/R7 -> the two 8 KB halves of PRG bank N-2 at $8000-$BFFF
        ;   $C000-$FFFF fixed to the final two 8 KB banks
        lda     #$00            ; vertical mirroring
        sta     $A000
        lda     #$00            ; IRQ disable
        sta     $E000
        lda     #$80            ; R0 = 0
        sta     $8000
        lda     #$00
        sta     $8001
        lda     #$81            ; R1 = 1
        sta     $8000
        lda     #$01
        sta     $8001
        lda     #$82            ; R2 = 0
        sta     $8000
        lda     #$00
        sta     $8001
        lda     #$83            ; R3 = 1
        sta     $8000
        lda     #$01
        sta     $8001
        lda     #$84            ; R4 = 2
        sta     $8000
        lda     #$02
        sta     $8001
        lda     #$85            ; R5 = 3
        sta     $8000
        lda     #$03
        sta     $8001
        lda     #$86            ; R6 = first switchable code 8 KB bank
        sta     $8000
        lda     #<GR_PRG_CODE_BANK
        sta     $8001
        lda     #$87            ; R7 = second switchable code 8 KB bank
        sta     $8000
        lda     #<GR_PRG_CODE_BANK2
        sta     $8001
        .endif
        rts

; ------------------------------------------------------------------------
; NMI: flush buffered PPU writes, then apply Gramma's scroll.
; ------------------------------------------------------------------------

nmi:    pha
        tya
        pha
        txa
        pha

        lda     #1
        sta     VBLANK_FLAG

        inc     tickcount
        bne     @s
        inc     tickcount+1

@s:     jsr     ppubuf_flush

        lda     #$20
        sta     PPU_VRAM_ADDR2
        lda     #$00
        sta     PPU_VRAM_ADDR2

        lda     NES_SCROLL_X
        sta     PPU_VRAM_ADDR1
        lda     NES_SCROLL_Y
        sta     PPU_VRAM_ADDR1

        pla
        tax
        pla
        tay
        pla
        rti

irq:    rti

; ------------------------------------------------------------------------
; Hardware vectors
; ------------------------------------------------------------------------

.segment "VECTORS"

        .word   nmi         ; $FFFA
        .word   start       ; $FFFC
        .word   irq         ; $FFFE
