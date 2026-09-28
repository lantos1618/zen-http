package main

import (
	"bufio"
	"strings"
	"testing"
)

func TestResponseContract(t *testing.T) {
	tests := []struct {
		name, wire string
		valid      bool
	}{
		{"valid", "HTTP/1.1 200 OK\r\nContent-Length: 3\r\n\r\nabc", true},
		{"case and whitespace", "HTTP/1.1 200 OK\r\ncOnTeNt-LeNgTh:\t3 \r\n\r\nabc", true},
		{"wrong body", "HTTP/1.1 200 OK\r\nContent-Length: 3\r\n\r\nxyz", false},
		{"duplicate length", "HTTP/1.1 200 OK\r\nContent-Length: 3\r\nContent-Length: 3\r\n\r\nabc", false},
		{"transfer encoding", "HTTP/1.1 200 OK\r\nContent-Length: 3\r\nTransfer-Encoding: chunked\r\n\r\nabc", false},
		{"signed length", "HTTP/1.1 200 OK\r\nContent-Length: +3\r\n\r\nabc", false},
		{"missing length", "HTTP/1.1 200 OK\r\n\r\nabc", false},
		{"truncated body", "HTTP/1.1 200 OK\r\nContent-Length: 3\r\n\r\nab", false},
		{"bad header name", "HTTP/1.1 200 OK\r\nContent-Length : 3\r\n\r\nabc", false},
		{"status", "HTTP/1.1 500 Error\r\nContent-Length: 3\r\n\r\nabc", false},
		{"header flood", "HTTP/1.1 200 OK\r\n" + strings.Repeat("X: a\r\n", 100) + "Content-Length: 3\r\n\r\nabc", false},
		{"large header", "HTTP/1.1 200 OK\r\nX: " + strings.Repeat("a", 9000) + "\r\nContent-Length: 3\r\n\r\nabc", false},
	}
	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			err := readResponse(bufio.NewReaderSize(strings.NewReader(test.wire), 16384), []byte("abc"), make([]byte, 3))
			if (err == nil) != test.valid {
				t.Fatalf("valid=%v error=%v", test.valid, err)
			}
		})
	}
}
