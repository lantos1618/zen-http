#ifndef ZEN_HTTP_REACTOR_H
#define ZEN_HTTP_REACTOR_H
/* Transitional H2 handle adapter. Generic OS readiness lives in std.net.readiness. */
#include "transport.h"
/* Transitional H2 opaque-handle adapter. HTTP/1 uses the Zen Readiness owner.
 * This preserves the existing H2 borrowed-handle lifetime until its NetworkIo
 * ownership is migrated. Platform event handling is shared with std. */
#include "zen_readiness.h"
struct zen_http_h2_reactor { int fd; uintptr_t *events; };
static void *zen_http_reactor_new(void *listener) {
    struct zen_http_h2_reactor *r = calloc(1, sizeof(*r));
    if (!r) return NULL;
    r->fd = -1;
    r->events = calloc(zen_ready_words(257), sizeof(uintptr_t));
    if (!r->events) { free(r); return NULL; }
    r->fd = zen_ready_open();
    if (r->fd < 0 || zen_ready_change(r->fd, zen_http_listener_fd(listener), 256, 0, 1) < 0) {
        if (r->fd >= 0) close(r->fd);
        free(r->events); free(r); return NULL;
    }
    return r;
}
static int zen_http_watch(void *reactor, void *transport, size_t slot) {
    struct zen_http_h2_reactor *r = reactor;
    struct transport *t = transport;
    if (t->want == t->armed) return 0;
    if (zen_ready_change(r->fd, t->fd, slot, t->want == POLLOUT, !t->armed) < 0) return -1;
    t->armed = t->want;
    return 0;
}
static int zen_http_wait_timeout(void *reactor, int timeout_ms) {
    struct zen_http_h2_reactor *r = reactor;
    int count = zen_ready_wait(r->fd, r->events, 257, timeout_ms);
    return count < 0 && zen_ready_interrupted(errno) ? 0 : count;
}
static void zen_http_reactor_free(void *reactor) {
    struct zen_http_h2_reactor *r = reactor;
    close(r->fd); free(r->events); free(r);
}
#endif
