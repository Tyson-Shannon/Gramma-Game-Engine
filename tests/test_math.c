#include <gramma/gramma.h>
#include <assert.h>

int main(void)
{
    assert(gr_itof(3) == 3 * GR_FIXED_ONE);
    assert(gr_ftoi(gr_itof(7)) == 7);
    assert(gr_ftoi(-gr_itof(7)) == -7);
    assert(gr_fmul(gr_itof(3), gr_itof(4)) == gr_itof(12));
    assert(gr_fdiv(gr_itof(12), gr_itof(4)) == gr_itof(3));
    assert(gr_fdiv(gr_itof(1), 0) == 0);
    assert(gr_fclamp(gr_itof(20), 0, gr_itof(10)) == gr_itof(10));
    assert(gr_fclamp(-gr_itof(2), 0, gr_itof(10)) == 0);
    return 0;
}
