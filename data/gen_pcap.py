"""Generate deterministic Ethernet/IPv4/TCP PCAPs offline; no network access."""
import datetime as dt
import pathlib
import socket
import struct

ROOT = pathlib.Path(__file__).resolve().parent
START = int(dt.datetime(2026, 1, 1, 10, tzinfo=dt.timezone.utc).timestamp())


def checksum(data):
    if len(data) % 2:
        data += b'\0'
    value = sum(struct.unpack('!' + 'H' * (len(data) // 2), data))
    while value >> 16:
        value = (value & 65535) + (value >> 16)
    return (~value) & 65535


def packet(src, dst, sport, dport, seq, ack, flags, payload=b''):
    source, dest = socket.inet_aton(src), socket.inet_aton(dst)
    tcp = struct.pack('!HHIIBBHHH', sport, dport, seq, ack, 80, flags, 65535, 0, 0)
    pseudo = source + dest + struct.pack('!BBH', 0, 6, len(tcp) + len(payload))
    tcp = tcp[:16] + struct.pack('!H', checksum(pseudo + tcp + payload)) + tcp[18:]
    ip = struct.pack('!BBHHHBBH4s4s', 69, 0, 40 + len(payload), 1, 0, 64, 6, 0, source, dest)
    ip = ip[:10] + struct.pack('!H', checksum(ip)) + ip[12:]
    return bytes.fromhex('0200000000050200000000660800') + ip + tcp + payload


def session(index, uri, unauthorized=False):
    a, b, port = '10.0.0.66', '10.0.0.5', 40000 + index
    request = f'GET {uri} HTTP/1.1\r\nHost: lab.example\r\nConnection: close\r\n\r\n'.encode('ascii')
    response = b'HTTP/1.1 200 OK\r\nContent-Length: 2\r\nConnection: close\r\n\r\nOK'
    if unauthorized:
        response = b'HTTP/1.1 401 Unauthorized\r\nContent-Length: 0\r\nConnection: close\r\n\r\n'
    client = lambda s, ack, f, p=b'': packet(a, b, port, 80, s, ack, f, p)
    server = lambda s, ack, f, p=b'': packet(b, a, 80, port, s, ack, f, p)
    c, s = 1001 + len(request), 9001 + len(response)
    return [client(1000, 0, 2), server(9000, 1001, 18), client(1001, 9001, 16),
            client(1001, 9001, 24, request), server(9001, c, 16),
            server(9001, c, 24, response), client(c, s, 16),
            server(s, c, 17), client(c, s + 1, 17), server(s + 1, c + 1, 16)]


def generate():
    paths = []
    for name, attack in [('web_sqli', True), ('benign_http', False)]:
        path = ROOT / f'{name}.pcap'
        with path.open('wb') as stream:
            stream.write(struct.pack('<IHHIIII', 0xa1b2c3d4, 2, 4, 0, 0, 65535, 1))
            for i in range(150):
                uri = '/search?q=1%20UNION%20SELECT%20password' if attack and i == 0 else f'/catalog?page={i}'
                for j, data in enumerate(session(i, uri)):
                    stream.write(struct.pack('<IIII', START + i, j * 1000, len(data), len(data)))
                    stream.write(data)
        paths.append(path)
    return paths


def generate_extended():
    paths = []
    scenarios = {
        'scan_syn': [(START + i // 50, packet('10.0.0.66', '10.0.0.5', 45000, 1000+i, i+1, 0, 2)) for i in range(1200)],
        'scan_slow': [(START + i * 2, packet('10.0.0.66', '10.0.0.5', 45000, 1000+i, i+1, 0, 2)) for i in range(1200)],
    }
    dns = []
    for i in range(1200):
        name = '.'.join(['a'*50, 'b'*50, str(i), 'lab', 'example'])
        query = b''.join(bytes([len(label)]) + label.encode() for label in name.split('.')) + b'\0'
        payload = struct.pack('!HHHHHH', i, 256, 1, 0, 0, 0) + query + struct.pack('!HH', 1, 1)
        udp = struct.pack('!HHHH', 45000, 53, len(payload)+8, 0) + payload
        ip = struct.pack('!BBHHHBBH4s4s', 69, 0, 20+len(udp), i, 0, 64, 17, 0, socket.inet_aton('10.0.0.66'), socket.inet_aton('10.0.0.5'))
        ip = ip[:10] + struct.pack('!H', checksum(ip)) + ip[12:]
        dns.append((START+i//50, bytes.fromhex('0200000000050200000000660800') + ip + udp))
    scenarios['dns_long'] = dns
    scenarios['brute_http'] = [(START+(i//2 if i<15 else i), p) for i in range(150) for p in session(i, '/login' if i<15 else '/catalog', unauthorized=i<15)]
    for name, uri in [('web_xss', '/search?q=%3Cscript%3Ealert(1)%3C/script%3E'), ('web_sqli_case', '/search?q=1%20uNiOn%20sElEcT%20password')]:
        scenarios[name] = [(START+i, p) for i in range(150) for p in session(i, uri if i == 0 else '/catalog')]
    for name, packets in scenarios.items():
        path = ROOT / (name+'.pcap')
        with path.open('wb') as stream:
            stream.write(struct.pack('<IHHIIII', 0xa1b2c3d4, 2, 4, 0, 0, 65535, 1))
            for index, (seconds, data) in enumerate(packets):
                stream.write(struct.pack('<IIII', seconds, index % 1000, len(data), len(data)))
                stream.write(data)
        paths.append(path)
    return paths


if __name__ == '__main__':
    for path in generate() + generate_extended():
        print(path.name, path.stat().st_size)
