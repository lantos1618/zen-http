#ifndef ZEN_HTTP_REACTOR_H
#define ZEN_HTTP_REACTOR_H
/* Readiness only. Slot identities and all HTTP state are owned by Zen. */
#include "transport.h"
#ifdef __APPLE__
#include <sys/event.h>
struct zen_http_reactor { int fd; struct kevent events[257]; };
#else
#include <sys/epoll.h>
struct zen_http_reactor { int fd; struct epoll_event events[257]; };
#endif
static int zen_http_watch_fd(struct zen_http_reactor *r, int fd, uintptr_t slot, short want, int fresh) {
#ifdef __APPLE__
    (void)fresh;
    struct kevent changes[2];
    EV_SET(&changes[0], fd, EVFILT_READ, EV_ADD | (want == POLLIN ? EV_ENABLE : EV_DISABLE), 0, 0, (void *)slot);
    EV_SET(&changes[1], fd, EVFILT_WRITE, EV_ADD | (want == POLLOUT ? EV_ENABLE : EV_DISABLE), 0, 0, (void *)slot);
    return kevent(r->fd, changes, 2, NULL, 0, NULL);
#else
    struct epoll_event event = {0};
    event.events = want == POLLIN ? EPOLLIN : EPOLLOUT;
    event.data.u64 = slot;
    return epoll_ctl(r->fd, fresh ? EPOLL_CTL_ADD : EPOLL_CTL_MOD, fd, &event);
#endif
}
static void *zen_http_reactor_new(void *listener) {
    struct zen_http_reactor *r = calloc(1, sizeof(*r));
    if (!r) return NULL;
#ifdef __APPLE__
    r->fd = kqueue();
#else
    r->fd = epoll_create1(EPOLL_CLOEXEC);
#endif
    if (r->fd < 0) { free(r); return NULL; }
    if (fcntl(r->fd, F_SETFD, FD_CLOEXEC) || zen_http_watch_fd(r, zen_http_listener_fd(listener), 256, POLLIN, 1)) {
        close(r->fd); free(r); return NULL;
    }
    return r;
}
static int zen_http_watch(void *reactor, void *transport, size_t slot) {
    struct transport *t = transport;
    if (t->want == t->armed) return 0;
    if (zen_http_watch_fd(reactor, t->fd, slot, t->want, !t->armed)) return -1;
    t->armed = t->want;
    return 0;
}
static int zen_http_wait_timeout(void *reactor, int timeout_ms) {
    struct zen_http_reactor *r = reactor;
#ifdef __APPLE__
    struct timespec timeout = {timeout_ms / 1000, (timeout_ms % 1000) * 1000000L};
    int n = kevent(r->fd, NULL, 0, r->events, 257, &timeout);
#else
    int n = epoll_wait(r->fd, r->events, 257, timeout_ms);
#endif
    return n < 0 && errno == EINTR ? 0 : n;
}
static int zen_http_wait(void *reactor) { return zen_http_wait_timeout(reactor, 1000); }
static size_t zen_http_ready_slot(void *reactor, size_t i) {
    struct zen_http_reactor *r = reactor;
#ifdef __APPLE__
    return (uintptr_t)r->events[i].udata;
#else
    return (size_t)r->events[i].data.u64;
#endif
}
static void zen_http_reactor_free(void *reactor) {
    struct zen_http_reactor *r = reactor; close(r->fd); free(r);
}
#endif
