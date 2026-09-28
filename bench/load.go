package main

import (
	"bufio"
	"bytes"
	"crypto/tls"
	"crypto/x509"
	"encoding/json"
	"flag"
	"fmt"
	"io"
	"math"
	"net"
	"os"
	"sort"
	"strconv"
	"strings"
	"sync"
	"syscall"
	"time"
)

type result struct {
	Count    int
	Samples  []int64
	Err      error
	Finished time.Time
}

func main() {
	size := flag.Int("body", 64, "request and response body bytes")
	concurrency := flag.Int("connections", 1, "persistent connections")
	seconds := flag.Float64("seconds", 2, "measurement duration")
	encrypted := flag.Bool("tls", false, "TLS 1.3 with verified local certificate")
	flag.Parse()
	if *size < 0 || *size > 65536 || *concurrency < 1 || *concurrency > 200 || math.IsNaN(*seconds) || math.IsInf(*seconds, 0) || *seconds <= 0 || *seconds > 3600 {
		panic("invalid parameters")
	}
	config := &tls.Config{ServerName: "localhost", MinVersion: tls.VersionTLS13, MaxVersion: tls.VersionTLS13}
	if *encrypted {
		cert, err := os.ReadFile("build/cert.pem")
		if err != nil {
			panic(err)
		}
		roots := x509.NewCertPool()
		if !roots.AppendCertsFromPEM(cert) {
			panic("invalid CA")
		}
		config.RootCAs = roots
	}
	start := make(chan time.Time, *concurrency)
	output := make(chan result, *concurrency)
	var ready sync.WaitGroup
	ready.Add(*concurrency)
	for worker := 0; worker < *concurrency; worker++ {
		go func(worker int) {
			r := result{Samples: make([]int64, 0, 65536)}
			announced := false
			defer func() {
				if !announced {
					ready.Done()
				}
				r.Finished = time.Now()
				output <- r
			}()
			conn, e := net.DialTimeout("tcp", "127.0.0.1:18080", 3*time.Second)
			if e != nil {
				r.Err = e
				return
			}
			defer conn.Close()
			conn.SetDeadline(time.Now().Add(10 * time.Second))
			if *encrypted {
				secure := tls.Client(conn, config)
				if e = secure.Handshake(); e != nil {
					r.Err = e
					return
				}
				if secure.ConnectionState().CipherSuite != tls.TLS_AES_128_GCM_SHA256 {
					r.Err = fmt.Errorf("unexpected cipher")
					return
				}
				conn = secure
			}
			payload := make([]byte, *size)
			for i := range payload {
				payload[i] = byte((i*31 + worker) % 251)
			}
			header := fmt.Sprintf("POST /echo HTTP/1.1\r\nHost: localhost\r\nContent-Length: %d\r\n\r\n", len(payload))
			request := append([]byte(header), payload...)
			response := make([]byte, *size)
			reader := bufio.NewReaderSize(conn, 131072)
			exchange := func() error {
				left := request
				for len(left) > 0 {
					n, e := conn.Write(left)
					if e != nil {
						return e
					}
					if n == 0 {
						return io.ErrShortWrite
					}
					left = left[n:]
				}
				return readResponse(reader, payload, response)
			}
			warmEnd := time.Now().Add(time.Second)
			for time.Now().Before(warmEnd) {
				if e := exchange(); e != nil {
					r.Err = e
					return
				}
			}
			announced = true
			ready.Done()
			begin := <-start
			time.Sleep(time.Until(begin))
			end := begin.Add(time.Duration(*seconds * float64(time.Second)))
			conn.SetDeadline(end.Add(3 * time.Second))
			for time.Now().Before(end) {
				t := time.Now()
				if e := exchange(); e != nil {
					r.Err = e
					return
				}
				r.Samples = append(r.Samples, time.Since(t).Nanoseconds())
				r.Count++
			}
		}(worker)
	}
	ready.Wait()
	begin := time.Now().Add(20 * time.Millisecond)
	for i := 0; i < *concurrency; i++ {
		start <- begin
	}
	samples := []int64{}
	count := 0
	finished := begin
	for i := 0; i < *concurrency; i++ {
		r := <-output
		if r.Err != nil {
			fmt.Fprintln(os.Stderr, r.Err)
			os.Exit(1)
		}
		if r.Finished.After(finished) {
			finished = r.Finished
		}
		count += r.Count
		samples = append(samples, r.Samples...)
	}
	elapsed := finished.Sub(begin).Seconds()
	if count == 0 {
		panic("no responses")
	}
	sort.Slice(samples, func(i, j int) bool { return samples[i] < samples[j] })
	quantile := func(p float64) float64 { return float64(samples[int(float64(len(samples)-1)*p)]) / 1000 }
	var usage syscall.Rusage
	if err := syscall.Getrusage(syscall.RUSAGE_SELF, &usage); err != nil {
		panic(err)
	}
	json.NewEncoder(os.Stdout).Encode(map[string]interface{}{
		"requests": count, "elapsed_s": elapsed, "rps": float64(count) / elapsed,
		"p50_us": quantile(.50), "p95_us": quantile(.95), "p99_us": quantile(.99),
		"body": *size, "connections": *concurrency, "tls": *encrypted,
		"client_cpu_s_including_warmup": float64(usage.Utime.Sec+usage.Stime.Sec) + float64(usage.Utime.Usec+usage.Stime.Usec)/1e6,
	})
}

// This benchmark deliberately accepts only the declared fixed-length echo contract.
func readResponse(reader *bufio.Reader, payload, response []byte) error {
	status, err := reader.ReadSlice('\n')
	if err != nil {
		return err
	}
	if !bytes.Equal(status, []byte("HTTP/1.1 200 OK\r\n")) {
		return fmt.Errorf("unexpected status %q", status)
	}
	length := -1
	total := len(status)
	for headers := 0; ; headers++ {
		line, err := reader.ReadSlice('\n')
		if err != nil {
			return err
		}
		total += len(line)
		if total > 8192 || headers > 64 {
			return fmt.Errorf("response headers exceed benchmark limit")
		}
		if bytes.Equal(line, []byte("\r\n")) {
			break
		}
		if !bytes.HasSuffix(line, []byte("\r\n")) {
			return fmt.Errorf("invalid header terminator")
		}
		key, value, found := strings.Cut(string(line[:len(line)-2]), ":")
		if !found || key == "" {
			return fmt.Errorf("malformed header")
		}
		for _, ch := range key {
			if !(ch >= 'a' && ch <= 'z' || ch >= 'A' && ch <= 'Z' || ch >= '0' && ch <= '9' || strings.ContainsRune("!#$%&'*+-.^_`|~", ch)) {
				return fmt.Errorf("invalid header name")
			}
		}
		value = strings.Trim(value, " \t")
		switch strings.ToLower(key) {
		case "transfer-encoding":
			return fmt.Errorf("unexpected transfer encoding")
		case "content-length":
			if length != -1 || value == "" {
				return fmt.Errorf("duplicate or empty content length")
			}
			for _, ch := range value {
				if ch < '0' || ch > '9' {
					return fmt.Errorf("invalid content length")
				}
			}
			length, err = strconv.Atoi(value)
			if err != nil {
				return err
			}
		}
	}
	if length != len(payload) {
		return fmt.Errorf("length %d != %d", length, len(payload))
	}
	if _, err := io.ReadFull(reader, response); err != nil {
		return err
	}
	if !bytes.Equal(response, payload) {
		return fmt.Errorf("wrong response body")
	}
	return nil
}
