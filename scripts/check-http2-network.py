"""Independent hyper-h2 peer for the experimental Zen h2c listener on 18082."""
import argparse
import contextlib
import os
from pathlib import Path
import socket
import ssl
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'build/python-deps'))
try:
    import h2.config
    import h2.connection
    import h2.events
    import h2.settings
    import hpack
except ImportError:
    raise SystemExit('Install tests/http2-requirements.txt into build/python-deps with pip --target first')

PORT = 18082
SECURE = False

@contextlib.contextmanager
def server(binary):
    with socket.socket() as probe:
        probe.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)
        probe.bind(('127.0.0.1', PORT))
    with (ROOT / 'build/h2-network-test.log').open('w') as log:
        child = subprocess.Popen([str(ROOT / binary)] + (["--tls"] if SECURE else []), cwd=ROOT, stdout=log, stderr=log)
        try:
            deadline = time.monotonic() + 35
            while True:
                if child.poll() is not None:
                    raise AssertionError('server exited: ' + (ROOT / 'build/h2-network-test.log').read_text())
                try:
                    with socket.create_connection(('127.0.0.1', PORT), timeout=.1): pass
                    break
                except OSError:
                    if time.monotonic() >= deadline: raise
                    time.sleep(.03)
            yield child
            assert child.poll() is None, 'server died during protocol checks'
        finally:
            child.terminate()
            try: child.wait(timeout=5)
            except subprocess.TimeoutExpired:
                child.kill(); child.wait()

def descriptor_count(child):
    proc = Path('/proc') / str(child.pid) / 'fd'
    if proc.is_dir():
        return len(list(proc.iterdir()))
    result = subprocess.run(['/usr/sbin/lsof', '-a', '-p', str(child.pid), '-Ff'], capture_output=True, text=True, check=True)
    return sum(line.startswith('f') and line[1:].isdigit() for line in result.stdout.splitlines())

def readiness_cleanup(child):
    # Exercise owner cleanup before and after Wire is moved into Session.
    with Peer(): pass
    time.sleep(.1)
    baseline = descriptor_count(child)
    for _ in range(24):
        raw = socket.create_connection(('127.0.0.1', PORT), timeout=4)
        if SECURE:
            context = ssl.create_default_context(cafile=str(ROOT/'build/cert.pem'))
            context.set_alpn_protocols(['h2'])
            raw = context.wrap_socket(raw, server_hostname='localhost')
        with raw:
            raw.sendall(b'x' * 24)
            assert raw.recv(1) == b'', 'invalid preface accepted'
        with Peer(): pass
    time.sleep(.1)
    assert descriptor_count(child) == baseline, 'connection readiness descriptor leaked'
    print('H2 readiness cleanup: 24 preface failures + 24 established disconnects PASS', flush=True)

def wire(kind, flags, sid, data=b''):
    return len(data).to_bytes(3, 'big') + bytes((kind, flags)) + sid.to_bytes(4, 'big') + data

class Peer:
    def __init__(self, initial_window=None):
        self.sock = socket.create_connection(('127.0.0.1', PORT), timeout=4)
        if SECURE:
            context=ssl.create_default_context(cafile=str(ROOT/'build/cert.pem'))
            context.set_alpn_protocols(['h2'])
            self.sock=context.wrap_socket(self.sock,server_hostname='localhost')
            assert self.sock.selected_alpn_protocol() == 'h2'
        self.sock.settimeout(4)
        self.h2 = h2.connection.H2Connection(config=h2.config.H2Configuration(client_side=True, header_encoding='utf-8'))
        self.h2.initiate_connection()
        if initial_window is not None:
            self.h2.update_settings({h2.settings.SettingCodes.INITIAL_WINDOW_SIZE: initial_window})
        self.body = {}; self.headers = {}; self.ended = set(); self.resets = set(); self.pings = []
        self.settings = 0; self.acks = 0
        self.allow_goaway = False; self.goaways = []
        self.flush()
        self.until(lambda: self.settings > 0 and self.acks >= (2 if initial_window is not None else 1))
    def __enter__(self): return self
    def __exit__(self, *_): self.sock.close()
    def flush(self):
        data = self.h2.data_to_send()
        if data: self.sock.sendall(data)
    def pump(self, acknowledge=True):
        data = self.sock.recv(65536)
        assert data, 'unexpected EOF'
        for event in self.h2.receive_data(data):
            if isinstance(event, h2.events.RemoteSettingsChanged): self.settings += 1
            elif isinstance(event, h2.events.SettingsAcknowledged): self.acks += 1
            elif isinstance(event, h2.events.ResponseReceived): self.headers[event.stream_id] = dict(event.headers)
            elif isinstance(event, h2.events.DataReceived):
                self.body.setdefault(event.stream_id, bytearray()).extend(event.data)
                if acknowledge: self.h2.acknowledge_received_data(event.flow_controlled_length, event.stream_id)
            elif isinstance(event, h2.events.StreamEnded): self.ended.add(event.stream_id)
            elif isinstance(event, h2.events.StreamReset): self.resets.add(event.stream_id)
            elif isinstance(event, h2.events.PingAckReceived): self.pings.append(event.ping_data)
            elif isinstance(event, h2.events.ConnectionTerminated):
                self.goaways.append(event)
                assert self.allow_goaway, f'GOAWAY {event.error_code}'
        self.flush()
    def until(self, condition):
        deadline = time.monotonic() + 8
        while not condition():
            assert time.monotonic() < deadline, 'protocol made no progress'
            self.pump()
    def start(self, sid, length, *, path='/echo', fragmented=False, empty=False):
        headers = [(':method','POST'),(':scheme','https' if SECURE else 'http'),(':authority','localhost'),(':path',path),('content-length',str(length)),('x-shared','reused-huffman-header-value')]
        self.h2.send_headers(sid, headers, end_stream=empty)
        if fragmented:
            data = self.h2.data_to_send()
            n = int.from_bytes(data[:3], 'big')
            assert data[3] == 1 and n > 1
            payload = data[9:9+n]; middle = len(payload)//2
            parts = wire(1, data[4] & ~4, sid, payload[:middle]) + wire(9,4,sid,payload[middle:]) + data[9+n:]
            for byte in parts: self.sock.sendall(bytes([byte]))
        else: self.flush()
    def send_body(self, sid, data):
        position = 0
        if not data:
            self.h2.send_data(sid, b'', end_stream=True); self.flush(); return
        while position < len(data):
            window = self.h2.local_flow_control_window(sid)
            if not window:
                self.pump(); continue
            amount = min(window, self.h2.max_outbound_frame_size, len(data)-position)
            self.h2.send_data(sid, data[position:position+amount], end_stream=position+amount == len(data))
            position += amount; self.flush()
    def check(self, sid, expected, status='200'):
        self.until(lambda: sid in self.ended)
        assert self.headers[sid][':status'] == status
        assert bytes(self.body.get(sid,b'')) == expected
        if 'content-length' in self.headers[sid]:
            assert self.headers[sid]['content-length'] == str(len(expected))

def malformed(frame):
    with socket.create_connection(('127.0.0.1',PORT),timeout=4) as raw:
        if SECURE:
            context=ssl.create_default_context(cafile=str(ROOT/'build/cert.pem'));context.set_alpn_protocols(['h2'])
            sock=context.wrap_socket(raw,server_hostname='localhost')
        else: sock=raw
        sock.sendall(b'PRI * HTTP/2.0\r\n\r\nSM\r\n\r\n' + wire(4,0,0) + frame)
        sock.settimeout(4)
        buf=b''
        while True:
            try: chunk=sock.recv(65536)
            except ConnectionResetError: return
            if not chunk: return
            buf += chunk
            while len(buf)>=9:
                size=int.from_bytes(buf[:3],'big')
                if len(buf)<9+size: break
                if buf[3]==7:
                    assert size>=8 and int.from_bytes(buf[13:17],'big') != 0, 'malformed input accepted with clean GOAWAY'
                    return
                assert buf[3] != 1, 'malformed input produced response HEADERS'
                buf=buf[9+size:]

def checks():
    with Peer() as p:
        # Interleave live streams; repeated fields exercise the peer's HPACK table.
        first = b'A'*8192; second = bytes(range(256))*16
        p.start(1,len(first),fragmented=True); p.start(3,len(second))
        p.h2.send_data(1,first[:4096]); p.flush()
        p.send_body(3,second); p.send_body(1,first[4096:])
        p.check(1,first); p.check(3,second)
        p.start(5,0,empty=True); p.check(5,b'')
        body=bytes(i%251 for i in range(65536))
        p.start(7,len(body)); p.send_body(7,body); p.check(7,body)
        p.start(9,3); p.h2.send_data(9,b'pad',end_stream=True,pad_length=5);p.flush();p.check(9,b'pad')
        p.start(11,0,path='/missing',empty=True);p.check(11,b'not found','404')
        p.h2.ping(b'zen-ping');p.flush();p.until(lambda: b'zen-ping' in p.pings)
        p.start(13,100);p.h2.reset_stream(13);p.flush()
        p.start(15,2);p.send_body(15,b'ok');p.check(15,b'ok')
    print('h2c independent peer: concurrent streams, HPACK, CONTINUATION, padding, 64KiB, reset and ping PASS',flush=True)
    with Peer(initial_window=0) as p:
        p.start(1,2048);p.send_body(1,b'x'*2048)
        p.start(3,2);p.send_body(3,b'ok')
        p.until(lambda: 1 in p.headers and 3 in p.headers)
        assert not p.body, 'DATA exceeded zero stream window'
        p.h2.increment_flow_control_window(2,stream_id=3);p.flush();p.check(3,b'ok')
        assert not p.body.get(1), 'blocked stream sent DATA'
        p.h2.increment_flow_control_window(2048,stream_id=1);p.flush();p.check(1,b'x'*2048)
    print('h2c zero-window stream isolation and resumption PASS',flush=True)
    for frame in [wire(6,0,0,b'short'),wire(0,1,0,b'x'),wire(8,0,0,b'\0'*4),wire(4,0,1),wire(9,4,1,b'\x82'),wire(0,0,1,b'x'*16385)]: malformed(frame)
    print('h2c malformed frame rejection PASS',flush=True)
    base=[(':method','POST'),(':scheme','https' if SECURE else 'http'),(':authority','localhost'),(':path','/echo')]
    for bad in [base+[('connection','close')],base+[('X-Upper','bad')],base+[('content-length','1')],base+[(':path','/duplicate')]]:
        malformed(wire(1,5,1,hpack.Encoder().encode(bad)))
    print('HTTP/2 malformed request header rejection PASS',flush=True)
    with Peer() as p:
        p.allow_goaway=True
        for index in range(128):
            sid=2*index+1
            p.start(sid,0,empty=True);p.check(sid,b'')
        p.until(lambda: bool(p.goaways))
        assert p.goaways[-1].error_code==0 and p.goaways[-1].last_stream_id==255
    print('HTTP/2 128-request GOAWAY resource limit PASS',flush=True)
    if SECURE:
        context=ssl.create_default_context(cafile=str(ROOT/'build/cert.pem'))
        context.set_alpn_protocols(['http/1.1'])
        with socket.create_connection(('127.0.0.1',PORT),timeout=4) as raw:
            try: context.wrap_socket(raw,server_hostname='localhost')
            except ssl.SSLError: pass
            else: raise AssertionError('accepted incompatible ALPN')
        context=ssl.create_default_context(cafile=str(ROOT/'build/cert.pem'))
        with socket.create_connection(('127.0.0.1',PORT),timeout=4) as raw:
            with context.wrap_socket(raw,server_hostname='localhost') as peer:
                peer.sendall(b'PRI * HTTP/2.0\r\n\r\nSM\r\n\r\n')
                try: assert peer.recv(1)==b'', 'accepted missing ALPN'
                except (ConnectionResetError,ssl.SSLError): pass
        context=ssl.create_default_context();context.set_alpn_protocols(['h2'])
        with socket.create_connection(('127.0.0.1',PORT),timeout=4) as raw:
            try: context.wrap_socket(raw,server_hostname='localhost')
            except ssl.SSLCertVerificationError: pass
            else: raise AssertionError('accepted untrusted test certificate')
        print('HTTP/2 TLS incompatible/missing ALPN and untrusted certificate rejection PASS',flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--binary',default='build/zen-h2-server');args=parser.parse_args()
    for SECURE in (False,True):
        with server(args.binary) as child:
            checks()
            readiness_cleanup(child)
        print(('TLS h2 ALPN' if SECURE else 'plaintext h2c') + ' suite PASS',flush=True)
