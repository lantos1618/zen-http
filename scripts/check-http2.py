"""Compile package tests and compare corpus output; exercise a separate wire peer."""
import os, pathlib, subprocess, socket, ssl, threading, struct
ROOT = pathlib.Path(__file__).resolve().parents[1]
os.chdir(ROOT)
ENV = dict(os.environ, ZEN_STD=str(ROOT.parent / 'zen-actor-runtime/src'))
COMPILER = str(ROOT.parent / 'zen-actor-runtime/zen')
source = ROOT / 'build/source'
def compile_test(path):
    entry = source / ('h2_' + path.name)
    if entry.is_symlink(): entry.unlink()
    entry.symlink_to(path.resolve())
    output = ROOT / 'build' / ('h2_' + path.stem)
    subprocess.run([COMPILER, 'build', str(source), '--entry', entry.name, '--emit-c', '-o', str(output)+'.c'], env=ENV, check=True)
    subprocess.run(['clang', '-O2', '-I../zen-crypto/src', '-Ibuild/openssl/include', str(output)+'.c', 'build/openssl/lib/libssl.a', 'build/openssl/lib/libcrypto.a', '-o', str(output)], check=True)
    return output
for path in sorted((ROOT / 'tests/http2').glob('*.zen')):
    executable = compile_test(path)
    expected = path.with_suffix('.expected')
    if expected.exists():
        result = subprocess.run([str(executable)], capture_output=True, text=True, check=True)
        assert result.stdout == expected.read_text(), (path, result.stdout)
        print(path.stem, 'PASS', flush=True)

def exact(conn, n):
    data = b''
    while len(data) < n:
        chunk = conn.recv(n-len(data))
        if not chunk: raise EOFError()
        data += chunk
    return data

def frame(kind, flags, sid, body=b''):
    return len(body).to_bytes(3,'big') + bytes([kind,flags]) + sid.to_bytes(4,'big') + body

def peer(listener, secure, errors, alpn="h2"):
    try:
        conn, _ = listener.accept()
        conn.settimeout(10)
        if secure:
            context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            context.load_cert_chain('build/cert.pem','build/key.pem')
            context.set_alpn_protocols([alpn])
            conn = context.wrap_socket(conn, server_side=True)
            if alpn != 'h2':
                conn.close()
                return
            assert conn.selected_alpn_protocol() == 'h2'
        with conn:
            assert exact(conn,24) == b'PRI * HTTP/2.0\r\n\r\nSM\r\n\r\n'
            conn.sendall(frame(4,0,0))
            bodies = {}
            count = 0
            while count < 3:
                head = exact(conn,9)
                n = int.from_bytes(head[:3],'big'); kind, flags = head[3:5]; sid = int.from_bytes(head[5:],'big')
                data = exact(conn,n)
                if kind == 4 and not flags & 1: conn.sendall(frame(4,1,0))
                if kind == 1: bodies[sid] = b''
                if kind == 0: bodies[sid] += data
                if kind in (0,1) and flags & 1:
                    assert sid == 1 + count*2
                    # Indexed :status 200. Split every wire byte to exercise reads.
                    reply = frame(1,4,sid,b'\x88') + frame(0,1,sid,bodies[sid])
                    for byte in reply: conn.sendall(bytes([byte]))
                    count += 1
    except BaseException as error: errors.append(error)
for secure in (False, True):
    errors=[]
    with socket.socket() as listener:
        listener.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)
        listener.bind(('127.0.0.1',18081)); listener.listen(); listener.settimeout(35)
        worker=threading.Thread(target=peer,args=(listener,secure,errors)); worker.start()
        result=subprocess.run(['build/h2_client']+(['--tls'] if secure else []), env=dict(ENV, SSL_CERT_FILE=str(ROOT/'build/cert.pem')), capture_output=True,text=True,timeout=35)
        worker.join(35)
        assert not worker.is_alive()
        assert not errors, errors
        assert result.returncode == 0, f"client exit {result.returncode}: " + result.stderr + result.stdout
    print('HTTP/2 '+('TLS ALPN' if secure else 'prior knowledge')+' PASS',flush=True)

# Trusted certificate but no h2 ALPN must never be accepted as HTTP/2.
errors = []
with socket.socket() as listener:
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listener.bind(('127.0.0.1', 18081)); listener.listen(); listener.settimeout(35)
    worker = threading.Thread(target=peer, args=(listener, True, errors, 'http/1.1'))
    worker.start()
    result = subprocess.run(['build/h2_client', '--tls', '--reject'], env=dict(ENV, SSL_CERT_FILE=str(ROOT/'build/cert.pem')), capture_output=True, text=True, timeout=35)
    worker.join(35)
    assert not worker.is_alive() and not errors, errors
    assert result.returncode == 0, result.stdout + result.stderr
print('HTTP/2 missing ALPN rejection PASS', flush=True)
