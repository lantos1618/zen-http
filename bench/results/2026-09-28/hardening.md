Throughput and p99 values are medians across trials. Brackets show trial minima–maxima, not confidence intervals. Ratios are medians of paired Zen/uWS throughput ratios.

Run status: complete. Planned paired trials per cell: 3.

| Protocol | Connections | Body bytes | Valid pairs / planned | Zen req/s [min–max] | uWS req/s [min–max] | Paired Zen/uWS [min–max] | Zen p99 µs | uWS p99 µs | Status |
|---|---:|---:|---:|---|---|---|---:|---:|---|
| HTTP | 1 | 64 | 3/3 | 45,427 [44,796–51,523] | 46,047 [45,331–48,717] | 0.973 [0.932–1.137] | 60.3 | 63.4 | complete |
| HTTP | 1 | 16,384 | 3/3 | 35,735 [35,610–35,980] | 36,519 [36,126–38,347] | 0.979 [0.929–0.996] | 60.2 | 68.2 | complete |
| HTTP | 32 | 64 | 3/3 | 142,326 [140,687–143,999] | 140,897 [136,744–142,505] | 1.010 [0.987–1.053] | 447.8 | 471.6 | complete |
| HTTP | 32 | 16,384 | 3/3 | 94,060 [74,731–98,532] | 75,888 [72,627–80,755] | 1.220 [1.029–1.239] | 773.6 | 1149.4 | complete |
| TLS 1.3 | 1 | 64 | 3/3 | 42,323 [39,706–43,359] | 40,218 [38,636–40,303] | 1.050 [0.987–1.122] | 64.2 | 63.4 | complete |
| TLS 1.3 | 1 | 16,384 | 3/3 | 20,337 [20,017–20,463] | 20,300 [20,285–20,603] | 0.993 [0.987–1.002] | 93.5 | 95.6 | complete |
| TLS 1.3 | 32 | 64 | 3/3 | 118,536 [117,104–120,330] | 120,000 [118,392–120,736] | 0.989 [0.982–1.003] | 536.6 | 544.8 | complete |
| TLS 1.3 | 32 | 16,384 | 3/3 | 47,482 [39,421–50,573] | 46,925 [42,950–48,259] | 1.012 [0.918–1.048] | 1435.6 | 1380.1 | complete |

These closed-loop measurements include client overhead and use one outstanding request per connection. They do not measure open-loop tail latency, server CPU/RSS, or handshake throughput.
