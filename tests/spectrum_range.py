"""Verify the rendered spectrum separates two signals 30 dB apart."""
from pathlib import Path
import subprocess
import sys
from PIL import Image
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from cratelog_widgets import SPECTRUM_FILTER

base=Path(__file__).resolve().parents[1]
output=base/'.qa/spectrum-range.png'
output.parent.mkdir(exist_ok=True)
graph=SPECTRUM_FILTER.split(';',1)[1].replace('[analysis]','[0:a]',1)
subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-f','lavfi','-i',
    'aevalsrc=0.25*sin(2*PI*440*t)+0.0079057*sin(2*PI*4400*t):s=44100:d=1',
    '-filter_complex',graph,'-map','[vo]','-ss','0.5','-frames:v','1','-y',str(output)],
    check=True,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
with Image.open(output) as source:
    im=source.convert('RGB')
    def height(hz):
        fft_bin=hz*4096/44100
        x=round(1200-1200**((2048-fft_bin-1)/2047))
        return max(sum(im.getpixel((column,y))[0]>100 for y in range(im.height))
                   for column in range(max(0,x-8),min(im.width,x+9)))
    strong,quiet=height(440),height(4400)
    assert 75 <= strong-quiet <= 105, (strong,quiet)
    assert quiet < im.height*.35, (strong,quiet)
    print(f'PASS: 30 dB separation renders {strong-quiet} pixels; strong={strong}, quiet={quiet}/180')
