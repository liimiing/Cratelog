"""Run on macOS after build_macos.sh. Exercises real Cocoa/GL, never falls back."""
import argparse
import json
import math
from pathlib import Path
import sys
import time
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--seconds',type=float,default=10)
    args=parser.parse_args()
    if sys.platform!='darwin':raise SystemExit('This check requires macOS and the compiled native bridge.')
    import tkinter as tk
    from PIL import Image,ImageDraw
    from cratelog_turntable_native import NativeTurntable
    from cratelog_turntable import camera_eye
    root=tk.Tk();root.title('Cratelog GPU direct presentation check');root.geometry('960x640')
    canvas=tk.Canvas(root,highlightthickness=0);canvas.pack(fill='both',expand=True);root.update()
    renderer=NativeTurntable(canvas)
    hud=Image.new('RGBA',(960,640));ImageDraw.Draw(hud).text((16,16),'GPU direct / no per-frame pixel readback',fill='white')
    renderer.hud(hud.resize((1920,1280)),[(16,50,'33.33 RPM   +0.0%   ×1.000','#ffffff'),(16,80,'‹   ⌃   ↺   ›   ⌄   曲目','#ffffff')])
    start=time.monotonic();cpu=time.process_time();frames=0;failure=[]
    def draw():
        nonlocal frames
        elapsed=time.monotonic()-start
        if elapsed>=args.seconds:root.quit();return
        state=dict(width=960,height=640,eye=camera_eye(),rotation=elapsed*math.tau*100/180,
            lamp=1.,pitch=0.,velocity=100/3,speed_mix=0.,power=True,room_light=elapsed<args.seconds/2,
            keys=(0.,0.,0.),strobe=(.1,.2,0.,.3),clip=0.,progress=.5,arm=1.,lift=0.,cover='')
        try:frames+=int(renderer.render(state))
        except Exception as error:failure.append(error);root.quit();return
        root.after(33,draw)
    root.protocol('WM_DELETE_WINDOW',root.quit)
    try:
        draw();root.mainloop()
        elapsed=time.monotonic()-start
        if failure:raise failure[0]
        if not frames:raise RuntimeError('No native frames presented')
        print(json.dumps(dict(backend='native-cocoa-opengl',frames=frames,seconds=round(elapsed,2),fps=round(frames/max(elapsed,.001),2),process_cpu_percent=round(100*(time.process_time()-cpu)/max(elapsed,.001),2)),indent=2))
    finally:renderer.close();root.destroy()

if __name__=='__main__':main()
