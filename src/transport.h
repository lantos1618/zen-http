#ifndef ZEN_HTTP_TRANSPORT_H
#define ZEN_HTTP_TRANSPORT_H
/* Native socket/session setup and platform ABI helpers. I/O policy is Zen. */
#include <arpa/inet.h>
#include <errno.h>
#include <fcntl.h>
#include <netinet/tcp.h>
#include <poll.h>
#include <signal.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <sys/socket.h>
#include <time.h>
#include <unistd.h>
#include "zen_tls.h"

struct transport { int fd; SSL *ssl; int want, armed; };
struct listener { int fd; SSL_CTX *context; };
static int zen_http_flags(int fd) {
    int one = 1;
    if (fcntl(fd, F_SETFL, O_NONBLOCK) || fcntl(fd, F_SETFD, FD_CLOEXEC)) return -1;
    #ifdef SO_NOSIGPIPE
    if (setsockopt(fd, SOL_SOCKET, SO_NOSIGPIPE, &one, sizeof(one))) return -1;
#endif
    return setsockopt(fd, IPPROTO_TCP, TCP_NODELAY, &one, sizeof(one));
}
static void zen_http_listener_close(void *p) {
    struct listener *l = p;
    if (l->fd >= 0) close(l->fd);
    free(l); /* context is borrowed from the Zen owner */
}
static int zen_http_listener_fd(void *p) { return ((struct listener *)p)->fd; }
static void *zen_http_listen(unsigned char *host, uint16_t port, void *context) {
    struct listener *l = calloc(1, sizeof(*l));
    if (!l) return NULL;
    l->fd = -1;
    l->context = context;
    l->fd = socket(AF_INET, SOCK_STREAM, 0);
    if (l->fd < 0) goto fail;
    int one = 1;
    struct sockaddr_in addr = {0};
    addr.sin_family = AF_INET; addr.sin_port = htons(port);
    if (inet_pton(AF_INET, (char *)host, &addr.sin_addr) != 1
        || setsockopt(l->fd, SOL_SOCKET, SO_REUSEADDR, &one, sizeof(one)) || zen_http_flags(l->fd)
        || bind(l->fd, (struct sockaddr *)&addr, sizeof(addr)) || listen(l->fd, 256)) goto fail;
    return l;
fail:
    zen_http_listener_close(l); return NULL;
}
static void *zen_http_accept(void *p) {
    struct listener *l = p;
    int fd = accept(l->fd, NULL, NULL);
    if (fd < 0) return NULL;
    if (zen_http_flags(fd)) { close(fd); return NULL; }
    struct transport *t = calloc(1, sizeof(*t));
    if (!t) { close(fd); return NULL; }
    t->fd = fd; t->want = POLLIN;
    if (l->context) {
        t->ssl = zen_tls_accept(l->context, fd);
        if (!t->ssl) { close(fd); free(t); return NULL; }
    }
    return t;
}
static int zen_http_fd(void *p) { return ((struct transport *)p)->fd; }
static short zen_http_want(void *p) { return ((struct transport *)p)->want; }
/* errno is a platform macro; policy is implemented by the Zen caller. */
static int zen_http_errno(void) { return errno; }
static void zen_http_close(void *p) {
    struct transport *t = p;
    zen_tls_free(t->ssl); close(t->fd); free(t);
}
static uint64_t zen_http_seconds(void) {
    struct timespec ts; clock_gettime(CLOCK_MONOTONIC, &ts); return (uint64_t)ts.tv_sec;
}
static unsigned char *zen_http_date(void) {
    static _Thread_local char date[30]; static _Thread_local time_t previous;
    time_t now = time(NULL);
    if (now != previous) {
        struct tm utc; gmtime_r(&now, &utc);
        strftime(date, sizeof(date), "%a, %d %b %Y %H:%M:%S GMT", &utc);
        previous = now;
    }
    return (unsigned char *)date;
}
#endif
