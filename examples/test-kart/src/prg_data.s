; Optional data-only PRG bank for bank-aware linker verification. The build
; driver defines GR_NES_RAMCODE only when prg_banks > 2.
        .ifdef GR_NES_RAMCODE
        .export _prg_probe_data
        .segment "PRG0"
_prg_probe_data:
        .byte $A5
        .endif
