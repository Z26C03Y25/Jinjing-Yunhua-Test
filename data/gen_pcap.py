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


def session(index, uri):
    a, b, port = '10.0.0.66', '10.0.0.5', 40000 + index
    request = f'GET {uri} HTTP/1.1\r\nHost: lab.example\r\nConnection: close\r\n\r\n'.encode('ascii')
    response = b'HTTP/1.1 200 OK\r\nContent-Length: 2\r\nConnection: close\r\n\r\nOK'
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


if __name__ == '__main__':
    for path in generate():
        print(path.name, path.stat().st_size)
