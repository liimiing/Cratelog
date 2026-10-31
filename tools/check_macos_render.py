"""Real macOS acceptance probe: Tk/Cocoa/libmpv, not a mocked renderer."""
import math
import queue
import struct
import sys
import tempfile
import time
import wave
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from cratelog_platform import executable,load_tk


def main():
    if sys.platform!='darwin':
        raise SystemExit('此检查必须在 macOS 实机运行。')
    from cratelog_player import MPV,mpv_control_error
    from cratelog_widgets import SpectrumTimeline
    tk=load_tk();root=tk.Tk();root.title('Cratelog 原生频谱自检（静音）');root.geometry('850x180')
    host=SpectrumTimeline(root,lambda _:None);host.pack(fill='both',expand=True)
    engine=None;events=queue.Queue();progress=[0.0];pause=[None]
    def pump(seconds):
        deadline=time.monotonic()+seconds
        while time.monotonic()<deadline:
            root.update()
            while not events.empty():
                kind,event=events.get_nowait()
                if kind=='error':raise RuntimeError(event)
                error=mpv_control_error(event)
                if error:raise RuntimeError(error)
                if event.get('event')=='property-change':
                    if event.get('name')=='time-pos':progress[0]=event.get('data') or 0
                    if event.get('name')=='pause':pause[0]=event.get('data')
            time.sleep(.01)
    try:
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'spectrum.wav'
            sample=b''.join(struct.pack('<h',int(8000*math.sin(2*math.pi*1000*i/44100))) for i in range(44100))
            with wave.open(str(path),'wb') as audio:
                audio.setparams((1,2,44100,0,'NONE','not compressed'));audio.writeframes(sample*20)
            root.update()
            engine=MPV(executable('mpv'),events,host)
            engine.command('set_property','volume',0)
            engine.command('loadfile',str(path),'replace')
            pump(4)
            cpu_start=time.process_time();wall_start=time.monotonic()
            start=engine.process.frame_count();pump(2)
            count=engine.process.frame_count()-start
            print("频谱进程 CPU（含 libmpv）：%.1f%%" % (100*(time.process_time()-cpu_start)/(time.monotonic()-wall_start)))
            print("渲染统计：",engine.process.render_stats())
            assert count>=20,f'原生频谱输出过慢：2 秒只有 {count} 帧'
            assert progress[0]>1,'播放时钟未推进'
            engine.command('set_property','pause',True);pump(.6)
            before=progress[0];pump(.5)
            assert pause[0] is True and abs(progress[0]-before)<.15,'暂停失败'
            engine.command('seek',10,'absolute+exact');pump(.6)
            assert abs(progress[0]-10)<.5,'暂停时跳转失败'
            root.geometry('1100x240');pump(.3)
            root.iconify();pump(.5)
            frames_hidden=engine.process.frame_count();pump(.5)
            assert engine.process.frame_count()==frames_hidden,'最小化后仍在进行 GPU 呈现'
            root.deiconify();pump(.3)
            engine.command('set_property','pause',False);pump(1.5)
            assert progress[0]>10.5,'恢复播放失败'
            engine.close();engine=None
            # Exercise callback cancellation and a new native view in the same Tk root.
            engine=MPV(executable('mpv'),events,host)
            engine.close();engine=None
            print(f'PASS: 原生 Render API，{count/2:.1f} fps；播放、暂停、跳转、缩放、最小化、销毁重建')
    finally:
        if engine:engine.close()
        root.destroy()


if __name__=='__main__':main()
