#ifndef ZEN_HTTP_TRANSPORT_H
#define ZEN_HTTP_TRANSPORT_H
/* POSIX includes, narrow platform ABI access, errno and HTTP date/time.
 * Socket/session setup, allocation, cleanup and I/O policy live in Zen. */
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

/* Native family width varies by OS; nested native-record addresses are not
 * yet lowered by Zen. These helpers expose ABI fields without socket policy. */
static void zen_http_ipv4_family(void *p, int family) { ((struct sockaddr_in *)p)->sin_family = family; }
static void *zen_http_ipv4_address(void *p) { return &((struct sockaddr_in *)p)->sin_addr; }
/* errno is a platform macro; policy is implemented by the Zen caller. */
static int zen_http_errno(void) { return errno; }
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
