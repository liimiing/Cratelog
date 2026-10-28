"""Dedicated console entry: stdout is exclusively the binary frame protocol."""
import struct
import sys
from cratelog_turntable import worker
try:
    worker()
except Exception as error:
    message=str(error).encode('utf-8')
    sys.stdout.buffer.write(struct.pack('!I',len(message))+message)
    sys.stdout.buffer.flush()
    sys.exit(1)
