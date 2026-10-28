"""FFmpeg spectrum frames for Tk on macOS (no Cocoa cross-process embedding).

Only visualization is decoded here; mpv owns audio and the playback clock.
The worker follows that clock, freezes on pause and restarts after seeking.
"""
import subprocess
import threading
import time

WIDTH,HEIGHT,RATE=600,90,20
FILTER=(f'aresample=44100,showfreqs=s={WIDTH}x{HEIGHT*2}:rate={RATE}:mode=bar:'
        'ascale=log:fscale=log:win_size=4096:win_func=hann:averaging=2:'
        f'colors=0xff9c38|0xff6128,crop={WIDTH}:{HEIGHT}:0:0,format=rgb24')


class PortableSpectrum:
    def __init__(self,executable,events):
        self.executable=executable;self.events=events;self.condition=threading.Condition()
        self.closed=False;self.target=None;self.process=None;self.generation=0
        self.latest_frame=None;self.frame_pending=False;self.updated_at=0
        self.thread=threading.Thread(target=self.run,daemon=True,name='spectrum');self.thread.start()
    def update(self,file,position,paused=False):
        with self.condition:
            if self.target is None or self.target[0]!=str(file):self.generation+=1
            self.target=(str(file),max(0,position),paused);self.updated_at=time.monotonic();self.condition.notify()
    def take_frame(self):
        with self.condition:
            frame=self.latest_frame;self.latest_frame=None;self.frame_pending=False
            return frame
    def publish(self,generation,data):
        # Keep only the newest frame when the UI is slow.
        with self.condition:
            if generation!=self.generation or self.closed:return
            self.latest_frame=(generation,data)
            if not self.frame_pending:
                self.frame_pending=True;self.events.put(('spectrum',None))
    def stop(self):
        with self.condition:self.target=None;self.generation+=1;self.condition.notify()
        self.terminate()
    def terminate(self):
        process=self.process
        if process and process.poll() is None:
            try:process.terminate()
            except OSError:pass
    def close(self):
        self.closed=True;self.stop();self.thread.join(timeout=3)
    def run(self):
        process=None;file=None;cursor=0;generation=-1;frame_size=WIDTH*HEIGHT*3
        try:
            while not self.closed:
                with self.condition:
                    target=self.target;new_generation=self.generation
                    updated_at=self.updated_at
                    if target is None or target[2]:self.condition.wait(.1);continue
                wanted,position,_=target
                # Smooth sparse clock observations without running far ahead.
                position+=min(.2,max(0,time.monotonic()-updated_at))
                if wanted!=file or generation!=new_generation or position<cursor-.25 or position>cursor+1.5:
                    if process:
                        if process.poll() is None:process.terminate()
                        try:process.wait(timeout=2)
                        except subprocess.TimeoutExpired:process.kill();process.wait()
                        process.stdout.close()
                    cursor=position;file=wanted;generation=new_generation
                    process=subprocess.Popen([self.executable,'-nostdin','-v','error','-ss',str(position),'-i',file,
                        '-an','-filter_complex','[0:a]'+FILTER+'[v]','-map','[v]',
                        '-threads','1','-f','rawvideo','-pix_fmt','rgb24','pipe:1'],
                        stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
                    self.process=process
                if cursor>position+.05:
                    with self.condition:self.condition.wait(.03)
                    continue
                data=process.stdout.read(frame_size)
                if len(data)!=frame_size:
                    # EOF stays idle until a seek/new file arrives.
                    cursor=position+1
                    with self.condition:self.condition.wait(.1)
                    continue
                if cursor>=position-.1:self.publish(generation,data)
                cursor+=1/RATE
        except (OSError,ValueError) as e:
            if not self.closed:self.events.put(('status','频谱读取失败：'+str(e)))
        finally:
            if process:
                if process.poll() is None:
                    process.terminate()
                    try:process.wait(timeout=2)
                    except subprocess.TimeoutExpired:process.kill();process.wait()
                process.stdout.close()
