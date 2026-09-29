#!/usr/bin/env python3
"""Real native PSK HTTPS reactor checks; Python/OpenSSL are independent peers only."""
import ast
import contextlib
import hashlib
import hmac
import os
from pathlib import Path
import re
import socket
import subprocess
import threading
import time
from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey, X25519PublicKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
ROOT = Path(__file__).resolve().parents[1]
CRYPTO = Path(os.environ.get('ZEN_CRYPTO', ROOT.parent/'zen-crypto')).resolve()
OPENSSL = Path(os.environ.get('OPENSSL', ROOT/'build/openssl/bin/openssl')).resolve()
PSK = bytes(range(32))
BINARY = Path(os.environ.get('NATIVE_SERVER', ROOT/'build/zen-native-server')).resolve()
helper = ast.parse((CRYPTO/'scripts/check-tls13-server.py').read_text())
names = {'extract','label','finished','hs','plain','encrypted','receive_exact','receive_record','decrypt','extension','hello'}
exec(compile(ast.Module(body=[n for n in helper.body if isinstance(n,ast.FunctionDef) and n.name in names],type_ignores=[]),'<independent TLS oracle>','exec'))

def request(body=b'', extra=b'', path=b'/echo'):
    return b'POST '+path+b' HTTP/1.1\r\nHost: localhost\r\nContent-Length: '+str(len(body)).encode()+b'\r\n'+extra+b'\r\n'+body

class Peer:
    def __init__(self, port, first=b'', fragmented=False):
        self.sock = socket.create_connection(('127.0.0.1',port),3)
        self.sock.settimeout(4)
        self.buffer=b''; self.sent=0; self.received=0
        private=X25519PrivateKey.generate(); ch,early,sid=hello(private,'valid')
        wire=plain(22,ch[:7])+plain(22,ch[7:])
        if fragmented:
            for byte in wire:self.sock.sendall(bytes([byte]))
        else:self.sock.sendall(wire)
        header,sh=receive_record(self.sock)
        assert header[0]==22 and sh[0]==2 and int.from_bytes(sh[1:4],'big')==len(sh)-4
        n=sh[38]; assert sh[39:39+n]==sid
        at=39+n; assert sh[at:at+3]==b'\x13\x03\0'; at+=3
        length=int.from_bytes(sh[at:at+2],'big'); at+=2; assert at+length==len(sh)
        exts={}
        while at<len(sh):
            kind=int.from_bytes(sh[at:at+2],'big'); n=int.from_bytes(sh[at+2:at+4],'big');at+=4
            assert kind not in exts;exts[kind]=sh[at:at+n];at+=n
        assert exts[43]==b'\3\4' and exts[41]==b'\0\0' and exts[51][:4]==b'\0\x1d\0\x20'
        shared=private.exchange(X25519PublicKey.from_public_bytes(exts[51][4:])); transcript=ch+sh
        secret=extract(label(early,'derived',hashlib.sha256(b'').digest()),shared)
        digest=hashlib.sha256(transcript).digest(); client=label(secret,'c hs traffic',digest); server=label(secret,'s hs traffic',digest)
        flight=decrypt(server,0,receive_record(self.sock)); assert flight[-1]==22;flight=flight[:-1]
        assert len(flight)==42 and flight[:6]==hs(8,b'\0\0')
        assert hmac.compare_digest(flight[10:],finished(server,transcript+flight[:6]))
        transcript+=flight
        cf=hs(20,finished(client,transcript))
        master=extract(label(secret,'derived',hashlib.sha256(b'').digest()),bytes(32));digest=hashlib.sha256(transcript).digest()
        self.client=label(master,'c ap traffic',digest);self.server=label(master,'s ap traffic',digest)
        # Coalesce the client Finished and application bytes in the same TCP write.
        wire=encrypted(client,0,cf[:8])+encrypted(client,1,cf[8:])
        wire+=self.encode(first) if first else b''
        self.sock.sendall(wire)
    def encode(self, data):
        result=b''
        for at in range(0,len(data),16384):
            result+=encrypted(self.client,self.sent,data[at:at+16384],23);self.sent+=1
        return result
    def send(self,data):self.sock.sendall(self.encode(data))
    def empty_records(self,count):
        records=[]
        for _ in range(count):
            records.append(encrypted(self.client,self.sent,b'',23));self.sent+=1
        self.sock.sendall(b''.join(records))
    def part(self):
        part=decrypt(self.server,self.received,receive_record(self.sock));self.received+=1
        assert part[-1] in (21,23)
        return part[:-1],part[-1]
    def response(self, expected, status=200):
        while b'\r\n\r\n' not in self.buffer:
            part,kind=self.part(); assert kind==23;self.buffer+=part
        headers,body=self.buffer.split(b'\r\n\r\n',1)
        assert headers.startswith(f'HTTP/1.1 {status} '.encode()),headers
        fields=dict(line.split(b': ',1) for line in headers.split(b'\r\n')[1:])
        size=int(fields[b'Content-Length'])
        while len(body)<size:
            part,kind=self.part();assert kind==23;body+=part
        assert body[:size]==expected,(size,len(expected));self.buffer=body[size:]
    def closed(self):
        assert not self.buffer
        part,kind=self.part();assert kind==21 and part==b'\x01\0',(part,kind)
        assert self.sock.recv(1)==b''
    def close(self):self.sock.close()

@contextlib.contextmanager
def server():
    with socket.socket() as s:s.bind(('127.0.0.1',0));port=s.getsockname()[1]
    with (ROOT/'build/native-reactor-server.log').open('w') as log:
        proc=subprocess.Popen([str(BINARY),PSK.hex(),str(port)],stdout=log,stderr=log,cwd=ROOT)
        try:
            for _ in range(400):
                assert proc.poll() is None,('server exited',proc.returncode)
                try:
                    with socket.create_connection(('127.0.0.1',port),.1):break
                except OSError:time.sleep(.025)
            else:raise AssertionError('listener never ready')
            yield proc,port
        finally:
            if proc.poll() is None:proc.terminate()
            proc.wait(timeout=5)
    log=(ROOT/'build/native-reactor-server.log').read_text()
    assert 'runtime error:' not in log and 'AddressSanitizer' not in log and 'trap:' not in log,log

with server() as (proc,port):
    fd_path=Path(f'/proc/{proc.pid}/fd')
    time.sleep(.1)
    baseline_fds=len(list(fd_path.iterdir())) if fd_path.exists() else None
    stalled=socket.create_connection(('127.0.0.1',port),3);stalled.sendall(b'\x16\x03')
    start=time.monotonic()
    peer=Peer(port,request(b'coalesced',b'Connection: close\r\n'),fragmented=True)
    peer.response(b'coalesced');peer.closed();peer.close()
    assert time.monotonic()-start<4,'stalled handshake delayed another connection'
    print('PASS fragmented handshake, Finished/application coalescing, graceful shutdown, stalled-handshake isolation',flush=True)
    peer=Peer(port)
    peer.empty_records(96)
    peer.send(request(b'one')+request(b'two')+request(b'three'))
    for body in (b'one',b'two',b'three'):peer.response(body)
    chunked=b'POST /echo HTTP/1.1\r\nHost: localhost\r\nTransfer-Encoding: chunked\r\n\r\n2\r\nhe\r\n3\r\nllo\r\n0\r\n\r\n'
    peer.send(chunked);peer.response(b'hello')
    data=bytes(i%251 for i in range(50000));peer.send(request(data,b'Connection: close\r\n'));peer.response(data);peer.closed();peer.close()
    print('PASS runnable empty-record progress, HTTP pipelining, chunked framing and 50KB multi-record echo',flush=True)
    slow=Peer(port);slow.sock.setsockopt(socket.SOL_SOCKET,socket.SO_RCVBUF,4096)
    slow.sock.settimeout(3);errors=[]
    def flood():
        try:slow.send(request(b'x'*65536)*20)
        except (OSError,TimeoutError):pass
        except Exception as e:errors.append(e)
    thread=threading.Thread(target=flood);thread.start();time.sleep(.15)
    fast=Peer(port,request(b'independent',b'Connection: close\r\n'));fast.response(b'independent');fast.closed();fast.close()
    slow.close();thread.join(5);assert not thread.is_alive() and not errors,errors
    print('PASS slow-reader isolation and cancellation',flush=True)
    peer=Peer(port,request(b'peer close'));peer.response(b'peer close')
    peer.sock.sendall(encrypted(peer.client,peer.sent,b'\x01\0',21));peer.sent+=1
    peer.closed();peer.close()
    print('PASS peer-initiated authenticated shutdown',flush=True)
    for mode in ('wrong-psk','bad-binder','wrong-identity'):
        with socket.create_connection(('127.0.0.1',port),3) as bad:
            bad.settimeout(4);ch,_,_=hello(X25519PrivateKey.generate(),mode);bad.sendall(plain(22,ch))
            try:wire=bad.recv(1)
            except ConnectionResetError:wire=b''
            assert wire==b'','rejected identity/binder emitted server flight'
    print('PASS invalid PSK/identity/binder rejected before server flight',flush=True)
    stalled.settimeout(13)
    assert stalled.recv(1)==b'','incomplete handshake failed to expire'
    stalled.close()
    for _ in range(24):
        peer=Peer(port,request(b'cleanup',b'Connection: close\r\n'));peer.response(b'cleanup');peer.closed();peer.close()
    result=subprocess.run([str(OPENSSL),'s_client','-connect',f'127.0.0.1:{port}','-psk',PSK.hex(),'-psk_identity','ZenTest','-groups','X25519','-ciphersuites','TLS_CHACHA20_POLY1305_SHA256','-tls1_3','-quiet','-ign_eof'],input=request(b'openssl',b'Connection: close\r\n'),capture_output=True,timeout=10)
    assert result.returncode==0 and result.stdout.endswith(b'\r\n\r\nopenssl'),(result.returncode,result.stdout,result.stderr)
    assert proc.poll() is None
    if baseline_fds is not None:
        for _ in range(100):
            if len(list(fd_path.iterdir()))<=baseline_fds:break
            time.sleep(.02)
        assert len(list(fd_path.iterdir()))<=baseline_fds,'connection descriptors leaked'
        print('PASS Linux connection descriptor count returns to baseline',flush=True)
    print('PASS handshake timeout, repeated connection cleanup and OpenSSL HTTPS interoperability',flush=True)
print('PASS native PSK HTTPS reactor; no certificate/ALPN or performance claim')

# A broken scheduler that parks locally runnable TLS work must fail the real
# listener test. Only staged source is changed, never the production module.
if not os.environ.get('NATIVE_NEGATIVE'):
    stage=ROOT/'build/native-server-source'
    core=stage/'http/server_core.zen'; original=core.read_text()
    needle='(n == -3).then(() { yielded = true; h.break(); });'
    assert original.count(needle)==2,'runnable-yield contract changed'
    try:
        core.write_text(original.replace(needle,'(n == -3).then(() { h.break(); });'))
        zen=Path(os.environ.get('ZEN_COMPILER',ROOT.parent/'zen-crypto-numeric/zen')).resolve()
        std=Path(os.environ.get('ZEN_STD',ROOT.parent/'zen-crypto-numeric/src')).resolve()
        binary=ROOT/'build/native-runnable-negative'
        with (ROOT/'build/native-runnable-negative.log').open('w') as log:
            subprocess.run([str(zen),'build',str(stage),'--std',str(std),'--emit-c','-o',str(binary)+'.c'],check=True,stdout=log,stderr=log)
            subprocess.run([os.environ.get('CC','clang'),'-O2','-Werror=parentheses-equality','-Isrc','-I'+str(std/'std/net'),str(binary)+'.c','-o',str(binary)],check=True,cwd=ROOT,stdout=log,stderr=log)
        result=subprocess.run([os.environ.get('PYTHON','python3'),str(Path(__file__).resolve())],env={**os.environ,'NATIVE_SERVER':str(binary),'NATIVE_NEGATIVE':'1'},capture_output=True,text=True,timeout=15)
        assert result.returncode!=0 and ('TimeoutError' in result.stderr or 'timed out' in result.stderr),(result.returncode,result.stdout,result.stderr)
        assert 'PASS fragmented handshake' not in result.stdout
        print('PASS negative control: parking locally runnable TLS work stalls the handshake as detected')
    finally:
        core.write_text(original)
