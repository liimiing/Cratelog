"""Installation checks on the target machine; --playback checks real mpv IPC."""
import importlib
import platform
import queue
import subprocess
import sys
import tempfile
import time
import wave
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from cratelog_platform import executable,state_dir,ROOT
failures=[]
print(platform.platform(),platform.machine(),sys.executable)
if sys.version_info<(3,10):failures.append('需要 Python 3.10 或更新版本')
for module in ('tkinter','_tkinter','requests','PIL','openpyxl','mutagen','pyglet'):
    try:
        if module=='mutagen' and importlib.util.find_spec('mutagen') is None:sys.path.insert(0,str(ROOT/'vendor'))
        importlib.import_module(module);print('OK:',module)
    except ImportError as e:failures.append(module+': '+str(e))
if not any('tkinter' in e for e in failures):
    try:
        import tkinter as tk
        root=tk.Tk();root.withdraw();print('Tk:',root.tk.call('info','patchlevel'));root.destroy()
    except Exception as e:failures.append('Tk 窗口初始化失败：'+str(e))
for name in ('mpv','ffmpeg'):
    path=executable(name)
    if not path:
        if name=='mpv' or sys.platform=='darwin':failures.append('缺少 '+name)
        continue
    try:
        result=subprocess.run([path,'--version' if name=='mpv' else '-version'],capture_output=True,timeout=15)
        if result.returncode:raise RuntimeError('无法执行，请检查架构和安装')
        print('OK:',path)
    except Exception as e:failures.append(name+': '+str(e))
for name in ('web/cratelog-brand.json','web/assets/cratelog.png','cratelog_spectrum.lua','cratelog_macos.py','cratelog_turntable.py','cratelog_turntable.frag'):
    if not (ROOT/name).is_file():failures.append('缺少项目文件：'+name)
if sys.platform=='darwin' and not (ROOT/'runtime/macos/libcratelog.dylib').is_file():
    failures.append('缺少原生频谱库：请执行 bash tools/build_macos.sh')
try:
    with tempfile.TemporaryFile(dir=state_dir()):pass
    print('设置目录：',state_dir())
except OSError as e:failures.append('配置目录不可写：'+str(e))
if '--playback' in sys.argv and not failures:
    from cratelog_player import MPV,mpv_control_error
    engine=None
    try:
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'test.wav'
            with wave.open(str(path),'wb') as audio:
                audio.setparams((1,2,44100,0,'NONE','not compressed'));audio.writeframes(b'\0\0'*44100*3)
            events=queue.Queue();engine=MPV(executable('mpv'),events)
            engine.command('set_property','volume',0);engine.command('loadfile',str(path),'replace')
            deadline=time.monotonic()+15;seen=False
            while time.monotonic()<deadline:
                try:kind,event=events.get(timeout=1)
                except queue.Empty:continue
                if kind=='error':raise RuntimeError(event)
                if kind=='mpv' and mpv_control_error(event):raise RuntimeError(mpv_control_error(event))
                if event.get('event')=='property-change' and event.get('name')=='time-pos' and (event.get('data') or 0)>.1:seen=True;break
            if not seen:raise RuntimeError('没有收到播放进度，检查 mpv IPC')
            print('OK: mpv 解码、IPC 通信、播放进度')
            engine.close();engine=None
    except Exception as e:failures.append('播放检查失败：'+str(e))
    finally:
        if engine:engine.close()
if failures:
    print('\n检查未通过：\n'+'\n'.join(failures));sys.exit(1)
print('安装检查通过。')
