#ifndef TEST_KART_SMS_BANK_PROBE_H
#define TEST_KART_SMS_BANK_PROBE_H

#include <stdint.h>

/* Reads the sentinel from switchable ROM bank 2 and restores the startup bank.
 * Used by the shipped example to prove slot-2 banking works at runtime. */
uint8_t sms_bank_probe_read(void);

#endif /* TEST_KART_SMS_BANK_PROBE_H */
