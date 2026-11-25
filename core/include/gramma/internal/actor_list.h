#ifndef GRAMMA_INTERNAL_ACTOR_LIST_H
#define GRAMMA_INTERNAL_ACTOR_LIST_H

#include <gramma/types.h>

/* Collects visible actors from the static pool for the backend renderer. */
uint8_t gr_actor_list(gr_actor **out, uint8_t capacity);
void gr_actor_set_limit(uint8_t limit);

#endif /* GRAMMA_INTERNAL_ACTOR_LIST_H */
