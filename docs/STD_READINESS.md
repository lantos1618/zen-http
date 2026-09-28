# Standard-library readiness migration

HTTP/1 now imports `std.net.readiness`. Generic kqueue/epoll creation,
registration, waiting and slot extraction are maintained in the compiler's
standard library instead of this package. Build with the std-readiness compiler
branch containing `b283fc2d` (or a later revision including it), setting
`ZEN_COMPILER` and `ZEN_STD` to that checkout. The build adds its `src/std/net`
header directory when compiling emitted C and records both readiness source
files in the environment manifest. Mainline std integration is pending.

Zen HTTP/1 owns the `Readiness` value with a 257-event caller-allocated buffer.
The listener still has slot 256; connection slots are 0..255. The existing
userspace runnable queue, duplicate-event coalescing, eight-response budgets,
16-accept budget, inactivity sweep, and 0/1000 ms wait decisions are unchanged.
Interrupted waits return to those HTTP scheduling decisions without restarting
the timeout. Wait failures become `ServerError.Poll`. Registration failures
close the affected transport, including a potentially partial kqueue update.

The standard primitive has no HTTP capacities, slots, policy or actor dependency.
Its C header only bridges native event layouts and syscall/macro ABI. Transport
interest/armed metadata in this package is accessed by Zen through `c.record`.
No direct epoll/kevent calls remain in `src/reactor.h`.

HTTP/2 still borrows an opaque reactor handle inside its experimental `NetworkIo`
owner. A transitional adapter in `src/reactor.h` delegates its platform work to
the same standard-library ABI, but retains allocation, armed-interest comparison,
and EINTR-to-empty compatibility logic in C. Therefore this migration does not
claim that all H2 readiness policy is already Zen. A future H2 ownership change
must replace the adapter without copying the standard library's Drop owner.

The current compiler actor backend uses one pthread worker per actor and
condition-variable mailbox wakeups. It does not provide a network event loop.
Readiness can underpin an actor-owned loop, but actor-per-socket threads and
mailbox-to-reactor wakeup integration are outside this change. We leave existing
standard-library HTTP protocol modules and `Env.http` behavior untouched.

Correctness checks cover HTTP/1, TLS, disconnects and experimental H2. Historical
throughput results predate this migration; no performance improvement is claimed.
