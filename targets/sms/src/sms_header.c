/*
 * SEGA ROM header for SMS/GG builds.
 *
 * makesms computes the checksum but never updates the ROM-size nibble in the
 * region/size byte at $7fff. We therefore emit a full 16-byte header here and
 * derive the size code from the configured bank count.
 */
#include <stdint.h>

#ifndef GR_SMS_ROM_BANKS
#  define GR_SMS_ROM_BANKS 2u
#endif

#if defined(TARGET_GG)
#  define GR_SMS_REGION 7u          /* Game Gear International */
#else
#  define GR_SMS_REGION 4u          /* Master System Export */
#endif

#if GR_SMS_ROM_BANKS == 2u
#  define GR_SMS_SIZE_CODE 0xCu     /* 32 KB */
#elif GR_SMS_ROM_BANKS == 4u
#  define GR_SMS_SIZE_CODE 0xEu     /* 64 KB */
#elif GR_SMS_ROM_BANKS == 8u
#  define GR_SMS_SIZE_CODE 0xFu     /* 128 KB */
#elif GR_SMS_ROM_BANKS == 16u
#  define GR_SMS_SIZE_CODE 0x0u     /* 256 KB */
#elif GR_SMS_ROM_BANKS == 32u
#  define GR_SMS_SIZE_CODE 0x1u     /* 512 KB */
#elif GR_SMS_ROM_BANKS == 64u
#  define GR_SMS_SIZE_CODE 0x2u     /* 1 MB */
#else
#  error "unsupported GR_SMS_ROM_BANKS value"
#endif

#define GR_SMS_REGION_CODE ((uint8_t)((GR_SMS_REGION << 4) | GR_SMS_SIZE_CODE))

/* "TMR SEGA", reserved, checksum (filled by makesms), product code, version,
 * region/size. */
const __at (0x7ff0) unsigned char gr_sms_rom_header[16] = {
    'T', 'M', 'R', ' ', 'S', 'E', 'G', 'A',
    0xffu, 0xffu, 0x00u, 0x00u,
    0x00u, 0x00u, 0x00u, GR_SMS_REGION_CODE
};
