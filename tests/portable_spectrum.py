"""CPU spectrum frames use the real audio; pause and seek remain clock-driven."""
import queue
import subprocess
import sys
import tempfile
import time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from cratelog_platform import executable
from cratelog_portable_spectrum import PortableSpectrum,WIDTH,HEIGHT

with tempfile.TemporaryDirectory() as tmp:
    file=Path(tmp)/'tone.flac'
    ffmpeg=executable('ffmpeg')
    assert ffmpeg,'Install ffmpeg first'
    subprocess.run([ffmpeg,'-v','error','-f','lavfi','-i','sine=frequency=1000:duration=8','-y',str(file)],check=True,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    events=queue.Queue();worker=PortableSpectrum(ffmpeg,events)
    try:
        worker.update(file,0)
        kind,_=events.get(timeout=8);generation,data=worker.take_frame()
        assert kind=='spectrum' and len(data)==WIDTH*HEIGHT*3 and max(data)>0
        for _ in range(500):worker.publish(worker.generation,data)
        assert events.qsize()==1
        events.get_nowait();assert worker.take_frame()[1]==data
        worker.update(file,4)
        deadline=time.monotonic()+8
        while time.monotonic()<deadline:
            kind,result=events.get(timeout=8)
            if kind=='status':raise AssertionError(result)
            if kind=='spectrum':worker.take_frame();break
        worker.update(file,4,True);time.sleep(.2)
        while not events.empty():
            events.get_nowait();worker.take_frame()
        time.sleep(.3);assert events.empty(),'Paused analysis continues producing frames'
        worker.stop();worker.update(file,1)
        kind,_=events.get(timeout=8);generation,data=worker.take_frame();assert generation==worker.generation
    finally:worker.close()
    assert not worker.thread.is_alive()
print('PASS: real FFmpeg spectrum frame, pause, seek, stop/restart and cleanup')
