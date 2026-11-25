#include "sms_bank_probe.h"

#include <SMSlib.h>

#ifndef GR_SMS_ROM_BANKS
#  define GR_SMS_ROM_BANKS 2u
#endif

#if GR_SMS_ROM_BANKS > 2u
extern const uint8_t sms_bank2_probe_data[];
#endif

uint8_t sms_bank_probe_read(void)
{
#if GR_SMS_ROM_BANKS > 2u
    uint8_t value;

    SMS_saveROMBank();
    SMS_mapROMBank(2u);
    value = sms_bank2_probe_data[0];
    SMS_restoreROMBank();
    return value;
#else
    return 0u;
#endif
}
