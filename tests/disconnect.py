"""Abrupt peers must not terminate the server (including Linux SIGPIPE)."""
import argparse
import socket
import struct
import time
from check import server, connect, request, response


def check(name):
    for tls in (False, True):
        with server(name,tls) as process:
            for i in range(100):
                conn=connect(tls)
                conn.setsockopt(socket.SOL_SOCKET,socket.SO_LINGER,struct.pack('ii',1,0))
                try:
                    conn.sendall(request(bytes([i])*65536))
                finally:
                    conn.close()
                time.sleep(.001)
                assert process.poll() is None, f'{name} died after reset {i}: {process.returncode}'
            with connect(tls) as conn, conn.makefile('rb') as stream:
                conn.sendall(request(b'still alive'));response(stream,b'still alive')
        print(f'{name} {"TLS" if tls else "HTTP"} abrupt disconnect survival PASS',flush=True)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--server',default='zen');args=parser.parse_args();check(args.server)
