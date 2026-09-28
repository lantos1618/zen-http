Throughput and p99 values are medians across trials. Brackets show trial minima–maxima, not confidence intervals. Ratios are medians of paired Zen/uWS throughput ratios.

Run status: complete. Planned paired trials per cell: 3.

| Protocol | Connections | Body bytes | Valid pairs / planned | Zen req/s [min–max] | uWS req/s [min–max] | Paired Zen/uWS [min–max] | Zen p99 µs | uWS p99 µs | Status |
|---|---:|---:|---:|---|---|---|---:|---:|---|
| HTTP | 1 | 64 | 3/3 | 29,692 [29,202–29,825] | 27,967 [27,720–28,849] | 1.062 [1.012–1.076] | 48.6 | 49.0 | complete |
| HTTP | 1 | 16,384 | 3/3 | 17,983 [17,656–19,753] | 17,030 [17,009–21,208] | 1.056 [0.833–1.161] | 80.8 | 84.8 | complete |
| HTTP | 32 | 64 | 3/3 | 99,549 [94,848–100,557] | 99,785 [97,734–100,388] | 0.992 [0.970–1.008] | 626.7 | 629.8 | complete |
| HTTP | 32 | 16,384 | 3/3 | 70,234 [65,309–70,332] | 64,700 [64,686–66,776] | 1.052 [1.010–1.087] | 899.3 | 975.2 | complete |
| TLS 1.3 | 1 | 64 | 3/3 | 26,589 [26,394–28,389] | 26,718 [26,634–26,871] | 0.990 [0.988–1.066] | 51.5 | 51.5 | complete |
| TLS 1.3 | 1 | 16,384 | 3/3 | 12,201 [12,159–12,280] | 12,502 [12,353–12,676] | 0.982 [0.959–0.988] | 100.8 | 106.7 | complete |
| TLS 1.3 | 32 | 64 | 3/3 | 81,622 [79,205–81,976] | 81,814 [80,736–82,951] | 0.988 [0.981–0.998] | 757.1 | 747.6 | complete |
| TLS 1.3 | 32 | 16,384 | 3/3 | 25,521 [25,498–25,652] | 32,360 [32,258–32,773] | 0.789 [0.778–0.795] | 2446.2 | 1917.7 | complete |

Linux server resources below are trial medians over process lifetime through client completion, including startup and warmup. They are not timed-phase-only CPU or instantaneous RSS.

| Protocol | Connections | Body bytes | Server | CPU seconds | Peak RSS KiB |
|---|---:|---:|---|---:|---:|
| HTTP | 1 | 64 | zen | 2.120 | 5,112 |
| HTTP | 1 | 64 | uws | 1.900 | 5,404 |
| HTTP | 1 | 16384 | zen | 2.060 | 5,140 |
| HTTP | 1 | 16384 | uws | 1.990 | 5,372 |
| HTTP | 32 | 64 | zen | 3.990 | 5,116 |
| HTTP | 32 | 64 | uws | 3.990 | 5,420 |
| HTTP | 32 | 16384 | zen | 4.000 | 6,120 |
| HTTP | 32 | 16384 | uws | 3.990 | 5,364 |
| TLS 1.3 | 1 | 64 | zen | 2.200 | 9,620 |
| TLS 1.3 | 1 | 64 | uws | 2.020 | 9,848 |
| TLS 1.3 | 1 | 16384 | zen | 2.460 | 9,608 |
| TLS 1.3 | 1 | 16384 | uws | 2.260 | 9,948 |
| TLS 1.3 | 32 | 64 | zen | 4.000 | 11,084 |
| TLS 1.3 | 32 | 64 | uws | 4.000 | 11,328 |
| TLS 1.3 | 32 | 16384 | zen | 4.010 | 12,448 |
| TLS 1.3 | 32 | 16384 | uws | 4.010 | 11,648 |

These closed-loop measurements include client overhead and use one outstanding request per connection. They do not measure open-loop tail latency or handshake throughput. Server resource metrics, when available, include startup and warmup.
