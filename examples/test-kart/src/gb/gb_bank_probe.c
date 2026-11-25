/* Sentinel placed in GB ROM bank 2. The shipped example calls it through
 * GBDK's BANKED trampoline so the MBC switch is exercised without patching a
 * temporary ROM or leaving game code mapped into the switchable window. */
#pragma bank 2

#include "gb_bank_probe.h"

uint8_t gb_bank_probe_read(void) BANKED
{
    return 0x5au;
}
