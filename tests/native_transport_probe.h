/* Test-only syscall fault injection. Never included by the native server build. */
#ifndef NATIVE_TRANSPORT_PROBE_H
#define NATIVE_TRANSPORT_PROBE_H
#include "transport.h"
#include <sys/random.h>
static int interrupt_next, entropy_at, entropy_failure;
static void interrupt_read(void) { interrupt_next = 1; }
static void fail_entropy(int call) { entropy_at = 0; entropy_failure = call; }
static int entropy_calls(void) { return entropy_at; }
static ssize_t probe_recv(int fd, void *data, size_t len, int flags) {
    if (interrupt_next) { interrupt_next = 0; errno = EINTR; return -1; }
    return recv(fd, data, len, flags);
}
static int probe_getentropy(void *data, size_t len) {
    ++entropy_at;
    if (entropy_at == entropy_failure) { errno = EIO; return -1; }
    return getentropy(data, len);
}
#define recv probe_recv
#define getentropy probe_getentropy
#endif
