Throughput and p99 values are medians across trials. Brackets show trial minima–maxima, not confidence intervals. Ratios are medians of paired Zen/uWS throughput ratios.

Run status: complete. Planned paired trials per cell: 3.

| Protocol | Connections | Body bytes | Valid pairs / planned | Zen req/s [min–max] | uWS req/s [min–max] | Paired Zen/uWS [min–max] | Zen p99 µs | uWS p99 µs | Status |
|---|---:|---:|---:|---|---|---|---:|---:|---|
| HTTP | 1 | 64 | 3/3 | 27,779 [27,399–28,100] | 27,630 [27,368–27,792] | 1.005 [0.986–1.027] | 50.4 | 49.9 | complete |
| HTTP | 1 | 16,384 | 3/3 | 18,569 [17,005–22,366] | 16,903 [16,788–17,089] | 1.099 [1.013–1.309] | 81.8 | 85.3 | complete |
| HTTP | 32 | 64 | 3/3 | 99,159 [97,067–100,342] | 95,705 [95,643–97,679] | 1.015 [1.015–1.048] | 626.6 | 644.7 | complete |
| HTTP | 32 | 16,384 | 3/3 | 70,669 [67,896–71,764] | 63,517 [63,326–64,027] | 1.113 [1.072–1.121] | 892.4 | 981.9 | complete |
| TLS 1.3 | 1 | 64 | 3/3 | 25,632 [25,536–25,991] | 27,388 [26,370–28,570] | 0.936 [0.894–0.986] | 54.2 | 51.6 | complete |
| TLS 1.3 | 1 | 16,384 | 3/3 | 12,348 [12,265–12,568] | 12,809 [12,586–13,537] | 0.974 [0.912–0.981] | 100.4 | 105.3 | complete |
| TLS 1.3 | 32 | 64 | 3/3 | 85,102 [84,459–86,610] | 86,109 [85,668–87,321] | 0.988 [0.986–0.992] | 731.6 | 721.2 | complete |
| TLS 1.3 | 32 | 16,384 | 3/3 | 25,222 [24,587–26,787] | 32,378 [31,992–32,463] | 0.777 [0.769–0.827] | 2482.7 | 1929.2 | complete |

Linux server resources below are trial medians over process lifetime through client completion, including startup and warmup. They are not timed-phase-only CPU or instantaneous RSS.

| Protocol | Connections | Body bytes | Server | CPU seconds | Peak RSS KiB |
|---|---:|---:|---|---:|---:|
| HTTP | 1 | 64 | zen | 2.070 | 5,104 |
| HTTP | 1 | 64 | uws | 1.920 | 5,396 |
| HTTP | 1 | 16384 | zen | 2.010 | 5,136 |
| HTTP | 1 | 16384 | uws | 1.930 | 5,456 |
| HTTP | 32 | 64 | zen | 3.990 | 5,112 |
| HTTP | 32 | 64 | uws | 3.990 | 5,400 |
| HTTP | 32 | 16384 | zen | 3.990 | 6,140 |
| HTTP | 32 | 16384 | uws | 3.990 | 5,396 |
| TLS 1.3 | 1 | 64 | zen | 2.220 | 9,632 |
| TLS 1.3 | 1 | 64 | uws | 2.010 | 9,800 |
| TLS 1.3 | 1 | 16384 | zen | 2.470 | 9,652 |
| TLS 1.3 | 1 | 16384 | uws | 2.240 | 9,888 |
| TLS 1.3 | 32 | 64 | zen | 4.010 | 11,328 |
| TLS 1.3 | 32 | 64 | uws | 4.010 | 11,392 |
| TLS 1.3 | 32 | 16384 | zen | 4.010 | 12,584 |
| TLS 1.3 | 32 | 16384 | uws | 4.010 | 11,900 |

These closed-loop measurements include client overhead and use one outstanding request per connection. They do not measure open-loop tail latency or handshake throughput. Server resource metrics, when available, include startup and warmup.
