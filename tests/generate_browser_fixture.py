"""Offline browser security fixture: literal HTML in a parsed HTTP header."""
import pathlib
import struct
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'data'))
from gen_pcap import session, START

out = ROOT / 'tmp/browser-xss.pcap'
out.parent.mkdir(exist_ok=True)
with out.open('wb') as stream:
    stream.write(struct.pack('<IHHIIII', 0xa1b2c3d4, 2, 4, 0, 0, 65535, 1))
    for i, data in enumerate(session(0, '/search?q=UNION%20SELECT', user_agent='<img src=x onerror=alert(1)>')):
        stream.write(struct.pack('<IIII', START, i * 1000, len(data), len(data)))
        stream.write(data)
print(out)
