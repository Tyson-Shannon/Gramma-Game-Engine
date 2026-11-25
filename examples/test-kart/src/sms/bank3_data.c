#include <stdint.h>

/* Compiled into 16 KB ROM bank 3 with `--constseg BANK3`. */
const uint8_t sms_bank3_probe_data[4] = { 0x3cu, 0xc3u, 0x03u, 0x04u };
