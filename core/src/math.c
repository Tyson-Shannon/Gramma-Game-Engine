#include <gramma/target.h>

/* Fixed-point helpers.  Shared by every backend; no floats, no libm. */

gr_fixed gr_itof(int value)
{
    return (gr_fixed)((long)value << GR_FIXED_SHIFT);
}

int gr_ftoi(gr_fixed value)
{
    if (value >= 0) {
        return (int)(value >> GR_FIXED_SHIFT);
    }
    /* Arithmetic shift rounds toward -infinity; make it round toward zero. */
    return -((int)((-value) >> GR_FIXED_SHIFT));
}

gr_fixed gr_fmul(gr_fixed a, gr_fixed b)
{
    return (gr_fixed)(((long)a * (long)b) >> GR_FIXED_SHIFT);
}

gr_fixed gr_fdiv(gr_fixed a, gr_fixed b)
{
    if (b == 0) {
        return 0;
    }
    return (gr_fixed)(((long)a << GR_FIXED_SHIFT) / (long)b);
}

gr_fixed gr_fclamp(gr_fixed value, gr_fixed lo, gr_fixed hi)
{
    if (value < lo) {
        return lo;
    }
    if (value > hi) {
        return hi;
    }
    return value;
}
