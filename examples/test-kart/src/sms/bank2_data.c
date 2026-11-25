#include <stdint.h>

/* Compiled into 16 KB ROM bank 2 with `--constseg BANK2`. */
const uint8_t sms_bank2_probe_data[4] = { 0x5au, 0xa5u, 0x01u, 0x02u };
