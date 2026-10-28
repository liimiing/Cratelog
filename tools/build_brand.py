"""Approved Groove C mark: SVG, PNG and multi-resolution Windows icon."""
import math
from pathlib import Path
from PIL import Image,ImageDraw
out=Path(__file__).resolve().parents[1]/'web'/'assets'
out.mkdir(exist_ok=True)
s=8;im=Image.new('RGBA',(64*s,64*s));d=ImageDraw.Draw(im)
orange='#f59a38';dark='#202428'
d.rounded_rectangle((0,0,64*s-1,64*s-1),radius=14*s,fill=dark)
paths=[]
for radius in (21,11):
    outer=radius+2
    d.arc(((32-outer)*s,(32-outer)*s,(32+outer)*s,(32+outer)*s),42,318,fill=orange,width=4*s)
    x=32+radius*math.cos(math.radians(42));dy=radius*math.sin(math.radians(42))
    paths.append(f'<path d="M{x:.5f} {32+dy:.5f} A{radius} {radius} 0 1 1 {x:.5f} {32-dy:.5f}"/>')
d.ellipse((30*s,30*s,34*s,34*s),fill=orange)
svg='<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64"><title>Cratelog — Groove C</title><rect width="64" height="64" rx="14" fill="'+dark+'"/><g fill="none" stroke="'+orange+'" stroke-width="4">'+''.join(paths)+'</g><circle cx="32" cy="32" r="2" fill="'+orange+'"/></svg>'
(out/'cratelog.svg').write_text(svg,encoding='utf-8')
im.resize((256,256),Image.Resampling.LANCZOS).save(out/'cratelog.png')
im.save(out/'cratelog.ico',sizes=[(16,16),(24,24),(32,32),(48,48),(64,64),(128,128),(256,256)])
