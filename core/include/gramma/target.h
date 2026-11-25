#ifndef GRAMMA_TARGET_H
#define GRAMMA_TARGET_H

#include <stdint.h>

/*
 * Compile-time target configuration.
 *
 * There is deliberately no runtime target detection. Every backend defines
 * exactly one GRAMMA_TARGET_* macro in its build flags. Keeping these numbers
 * in one header means the public API has the same shape on an SM83 and on a
 * desktop host, while still letting each backend set honest limits.
 */

#if defined(GRAMMA_TARGET_GB) || defined(GRAMMA_TARGET_NES) || \
    defined(GRAMMA_TARGET_SMS)
#  define GR_FIXED_BITS      16
/* 6 fractional bits keep a 240px world inside int16_t (max 511 px). */
#  define GR_FIXED_SHIFT     6
#  define GR_MAX_ACTORS      32
#  define GR_MAX_PALETTES    8
#  define GR_AUDIO_CHANNELS  4
#  if defined(GRAMMA_TARGET_SMS)
#    define GR_PALETTE_COLORS  16
#    define GR_SUPPORT_BPP_1   1
#    define GR_SUPPORT_BPP_2   1
#    define GR_SUPPORT_BPP_4   1
#    define GR_SUPPORT_BPP_8   0
#  else
#    define GR_PALETTE_COLORS  4
#    define GR_SUPPORT_BPP_1   1
#    define GR_SUPPORT_BPP_2   1
#    define GR_SUPPORT_BPP_4   0
#    define GR_SUPPORT_BPP_8   0
#  endif
#elif defined(GRAMMA_TARGET_PC)
#  define GR_FIXED_BITS      32
#  define GR_FIXED_SHIFT     16
#  define GR_MAX_ACTORS      64
#  define GR_MAX_PALETTES    16
#  define GR_PALETTE_COLORS  16
#  define GR_AUDIO_CHANNELS  4
#  define GR_SUPPORT_BPP_1   1
#  define GR_SUPPORT_BPP_2   1
#  define GR_SUPPORT_BPP_4   1
#  define GR_SUPPORT_BPP_8   1
#else
/* Generic definition so headers can be inspected/linted without a backend. */
#  define GR_FIXED_BITS      32
#  define GR_FIXED_SHIFT     16
#  define GR_MAX_ACTORS      64
#  define GR_MAX_PALETTES    16
#  define GR_PALETTE_COLORS  16
#  define GR_AUDIO_CHANNELS  4
#  define GR_SUPPORT_BPP_1   1
#  define GR_SUPPORT_BPP_2   1
#  define GR_SUPPORT_BPP_4   1
#  define GR_SUPPORT_BPP_8   1
#endif

#if GR_FIXED_BITS == 16
typedef int16_t gr_fixed;
#else
typedef int32_t gr_fixed;
#endif

#define GR_FIXED_ONE       ((gr_fixed)(1L << GR_FIXED_SHIFT))
#define GR_BUTTON_BIT(b)   ((uint16_t)1u << (uint16_t)(b))

/* Native logical resolution of each target; games use these instead of
   hard-coding pixel counts so one source file builds everywhere. */
#if defined(GRAMMA_TARGET_GB)
#  define GR_SCREEN_W 160
#  define GR_SCREEN_H 144
#elif defined(GRAMMA_TARGET_NES)
#  define GR_SCREEN_W 256
#  define GR_SCREEN_H 240
#elif defined(GRAMMA_TARGET_SMS)
#  define GR_SCREEN_W 256
#  define GR_SCREEN_H 192
#else
#  define GR_SCREEN_W 256
#  define GR_SCREEN_H 224
#endif

/* Number of controllers the target can address without extra hardware. */
#if defined(GRAMMA_TARGET_GB)
#  define GR_PAD_PLAYERS 1
#else
#  define GR_PAD_PLAYERS 2
#endif

/* Fixed-point helpers live in the core so they can be shared by backends. */
gr_fixed gr_itof(int value);
int      gr_ftoi(gr_fixed value);
gr_fixed gr_fmul(gr_fixed a, gr_fixed b);
gr_fixed gr_fdiv(gr_fixed a, gr_fixed b);
gr_fixed gr_fclamp(gr_fixed value, gr_fixed lo, gr_fixed hi);

#endif /* GRAMMA_TARGET_H */
