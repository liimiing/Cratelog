"""Native Cratelog playback widgets (no external GUI dependencies)."""
from cratelog_platform import ui_font
import tkinter as tk
import math
from PIL import Image, ImageDraw, ImageTk

SPECTRUM_HEIGHT = round((145 + 21) * .7)
SPECTRUM_PLOT_HEIGHT = SPECTRUM_HEIGHT - 21


class HalfStarPicker(tk.Canvas):
    """Five stars; each left/right half selects a half/full star."""
    def __init__(self, parent, variable):
        super().__init__(parent,width=220,height=44,bg='#202428',highlightthickness=0,cursor='hand2',takefocus=True)
        self.variable=variable
        self.bind('<Button-1>',self.select)
        self.bind('<Left>',lambda e:self.step(-.5))
        self.bind('<Right>',lambda e:self.step(.5))
        self.bind('<Home>',lambda e:self.variable.set(0))
        self.bind('<End>',lambda e:self.variable.set(5))
        self.trace=variable.trace_add('write',lambda *args:self.draw())
        self.draw()

    def select(self,event):
        self.focus_set()
        self.variable.set(max(.5,min(5,math.ceil(event.x/22)/2)))

    def step(self,amount):
        self.variable.set(max(0,min(5,self.variable.get()+amount)))
        return 'break'

    def draw(self):
        image=Image.new('RGBA',(880,176),'#202428')
        draw=ImageDraw.Draw(image)
        for i in range(5):
            cx,cy=(i*44+22)*4,88
            points=[(cx+math.cos(-math.pi/2+j*math.pi/5)*(72 if j%2==0 else 32),
                     cy+math.sin(-math.pi/2+j*math.pi/5)*(72 if j%2==0 else 32)) for j in range(10)]
            draw.polygon(points,fill='#465057')
            fraction=max(0,min(1,self.variable.get()-i))
            if fraction:
                layer=Image.new('RGBA',image.size)
                ImageDraw.Draw(layer).polygon(points,fill='#efb861')
                box=(i*176,0,round((i+fraction)*176),176)
                crop=layer.crop(box); image.paste(crop,box[:2],crop)
        self.image=ImageTk.PhotoImage(image.resize((220,44),Image.Resampling.LANCZOS))
        self.delete('all'); self.create_image(0,0,image=self.image,anchor='nw')

    def destroy(self):
        self.variable.trace_remove('write',self.trace)
        super().destroy()


def fraction_at(x, width):
    return max(0.0, min(1.0, float(x) / max(1, width - 1)))


class Thermometer(tk.Canvas):
    """A filled timeline; mouse coordinates map directly to time, not scale steps."""
    def __init__(self, master, command, height=22, **kwargs):
        super().__init__(master, height=height, bg='#15191c', highlightthickness=0,
                         cursor='hand2', takefocus=True, **kwargs)
        self.command = command
        self.duration = 0.0
        self.position = 0.0
        self.dragging = False
        self.last_requested = None
        self.bind('<Configure>', lambda e: self.draw())
        self.bind('<ButtonPress-1>', self.press)
        self.bind('<B1-Motion>', self.motion)
        self.bind('<ButtonRelease-1>', self.release)
        self.bind('<Left>', lambda e: self.nudge(-5))
        self.bind('<Right>', lambda e: self.nudge(5))

    def set(self, position, duration):
        self.duration = max(0.0, float(duration))
        if not self.dragging:
            self.position = max(0.0, min(self.duration, float(position)))
            self.draw()

    def choose(self, x):
        self.position = fraction_at(x, self.winfo_width()) * self.duration
        self.draw()

    def press(self, event):
        if not self.duration: return 'break'
        self.focus_set()
        self.dragging = True
        self.choose(event.x)
        self.last_requested = self.position
        self.command(self.position)
        return 'break'

    def motion(self, event):
        if self.dragging: self.choose(event.x)
        return 'break'

    def release(self, event):
        if self.dragging:
            self.choose(event.x)
            self.dragging = False
            if self.position != self.last_requested:
                self.last_requested = self.position
                self.command(self.position)
        return 'break'

    def nudge(self, seconds):
        if self.duration:
            self.position = min(self.duration, max(0, self.position + seconds))
            self.command(self.position)
            self.draw()
        return 'break'

    def draw(self):
        self.delete('all')
        width, height = self.winfo_width(), self.winfo_height()
        self.create_rectangle(0, 0, width, height, fill='#30383d', outline='')
        filled = round(width * min(1, self.position / self.duration)) if self.duration else 0
        # Temperature-like amber → orange fill with a bright current-position edge.
        for x in range(0, filled, 4):
            t = x / max(1, width)
            color = f'#{int(237 + 18*t):02x}{int(182 - 85*t):02x}{int(76 - 30*t):02x}'
            self.create_rectangle(x, 2, min(x+4, filled), height-2, fill=color, outline='')
        if filled:
            self.create_line(min(filled, width-1), 1, min(filled, width-1), height-1, fill='#ffe2aa', width=2)


class SpectrumTimeline(tk.Frame):
    """Timeline model and Tk fallback input around the native mpv child surface.

    Actual video-area mouse input and painting are handled by cratelog_spectrum.lua.
    The Tk handlers cover input before mpv creates its child, plus keyboard use.
    """
    press = Thermometer.press
    motion = Thermometer.motion
    release = Thermometer.release
    nudge = Thermometer.nudge
    choose = Thermometer.choose
    set = Thermometer.set

    def __init__(self, master, command):
        super().__init__(master, bg='#000000', height=SPECTRUM_PLOT_HEIGHT, width=740,
                         cursor='hand2', takefocus=True)
        self.command = command
        self.duration = self.position = 0.0
        self.dragging = False
        self.last_requested = None
        # macOS attaches a Cocoa OpenGL subview here. No RGB canvas refresh loop.
        self.bind('<ButtonPress-1>', self.press)
        self.bind('<B1-Motion>', self.motion)
        self.bind('<ButtonRelease-1>', self.release)
        self.bind('<Left>', lambda e: self.nudge(-5))
        self.bind('<Right>', lambda e: self.nudge(5))

    def draw(self):
        # mpv renders the spectrum and progress overlay on its native surface.
        pass


class VolumeMeter(Thermometer):
    def __init__(self, master, variable, command, height=34):
        self.variable = variable
        self.change = command
        super().__init__(master, command=self.apply, width=200, height=height)
        self.duration = 100
        self.position = variable.get()
        self.variable_trace = variable.trace_add('write', self.changed)
        self.bind('<MouseWheel>', lambda e: self.nudge(2 if e.delta > 0 else -2))

    def apply(self, value):
        self.variable.set(max(0, min(100, value)))
        self.change(self.variable.get())

    def changed(self, *args):
        self.position = self.variable.get()
        self.draw()

    def motion(self, event):
        if self.dragging:
            self.choose(event.x)
            self.last_requested = self.position
            self.apply(self.position)
        return 'break'

    def draw(self):
        self.delete('all')
        width, height = self.winfo_width(), self.winfo_height()
        filled = round(width * self.position / 100)
        self.create_rectangle(0,0,width,height,fill='#30363c',outline='')
        self.create_rectangle(0,0,filled,height,fill='#687a7b',outline='')
        self.create_text(width/2,height/2,text=f'{self.position:.0f}%',fill='#edf0ef',font=(ui_font(),9))

    def destroy(self):
        self.variable.trace_remove('write', self.variable_trace)
        super().destroy()


def transport_icon(kind, width=88):
    """Antialiased familiar transport shapes, independent of system glyph fonts."""
    scale, height = 4, 20
    image = Image.new('RGBA', (width*scale,height*scale))
    draw = ImageDraw.Draw(image)
    offset = (width-20)/2
    def poly(points):
        draw.polygon([((x+offset)*scale,y*scale) for x,y in points], fill='#e7e7e7')
    if kind == 'play': poly([(6,3),(17,10),(6,17)])
    elif kind == 'pause':
        poly([(5,3),(9,3),(9,17),(5,17)]); poly([(12,3),(16,3),(16,17),(12,17)])
    elif kind == 'stop': poly([(4,4),(16,4),(16,16),(4,16)])
    elif kind == 'previous':
        poly([(4,3),(6,3),(6,17),(4,17)]); poly([(16,3),(6,10),(16,17)])
    elif kind == 'next':
        poly([(14,3),(16,3),(16,17),(14,17)]); poly([(4,3),(14,10),(4,17)])
    elif kind == 'menu':
        for y in (4,9,14):poly([(2,y),(18,y),(18,y+2),(2,y+2)])
    elif kind == 'list':
        for y in (4,9,14):
            poly([(2,y),(4,y),(4,y+2),(2,y+2)])
            poly([(7,y),(18,y),(18,y+2),(7,y+2)])
    elif kind == 'turntable':
        draw.rounded_rectangle(((offset+1)*scale,3*scale,(offset+19)*scale,17*scale),radius=scale,outline='#e7e7e7',width=scale)
        draw.ellipse(((offset+3)*scale,5*scale,(offset+13)*scale,15*scale),outline='#e7e7e7',width=scale)
        draw.ellipse(((offset+7)*scale,9*scale,(offset+9)*scale,11*scale),fill='#f59a38')
        poly([(16,5),(17,5),(17,11),(14,14),(13,13),(16,10)])
    elif kind == 'copy':
        # Two offset sheets, with an open rear outline.
        poly([(3,13),(1,13),(1,1),(13,1),(13,3),(3,3)])
        draw.rounded_rectangle(((6+offset)*scale,6*scale,(18+offset)*scale,19*scale),
                               radius=scale,outline='#e7e7e7',width=2*scale)
    elif kind == 'search':
        draw.ellipse(((2+offset)*scale,2*scale,(14+offset)*scale,14*scale),
                     outline='#e7e7e7',width=2*scale)
        poly([(12,14),(14,12),(19,17),(17,19)])
    elif kind == 'remote':
        draw.rounded_rectangle(((1+offset)*scale,3*scale,(16+offset)*scale,18*scale),radius=scale,outline='#e7e7e7',width=2*scale)
        poly([(10,1),(20,1),(20,11),(18,11),(18,5),(10,13),(8,11),(16,3),(10,3)])
    elif kind == 'selected':
        poly([(2,10),(5,7),(8,11),(16,3),(19,6),(8,17)])
    elif kind == 'highlighted':
        poly([(10+9*math.cos(-math.pi/2+j*math.pi/5),10+9*math.sin(-math.pi/2+j*math.pi/5)) if j%2==0 else
              (10+4*math.cos(-math.pi/2+j*math.pi/5),10+4*math.sin(-math.pi/2+j*math.pi/5)) for j in range(10)])
    elif kind == 'sequential':
        for y in (4,9,14):poly([(2,y),(11,y),(11,y+2),(2,y+2)])
        poly([(14,5),(19,10),(14,15)])
    elif kind in ('repeat','repeat_one'):
        poly([(3,4),(14,4),(14,1),(19,5),(14,9),(14,6),(5,6),(5,10),(3,10)])
        poly([(17,16),(6,16),(6,19),(1,15),(6,11),(6,14),(15,14),(15,10),(17,10)])
        if kind=='repeat_one':poly([(9,8),(11,7),(11,13),(9,13),(9,9),(8,10),(8,8)])
    return ImageTk.PhotoImage(image.resize((width,height),Image.Resampling.LANCZOS))


class Tooltip:
    def __init__(self, widget, text):
        self.widget, self.text, self.window, self.job = widget, text, None, None
        widget.bind('<Enter>', self.schedule, add='+')
        widget.bind('<Leave>', self.hide, add='+')
        widget.bind('<ButtonPress>', self.hide, add='+')
        widget.bind('<Destroy>', self.hide, add='+')

    def schedule(self, event=None):
        self.hide()
        self.job = self.widget.after(500,self.show)

    def show(self):
        self.job = None
        self.window = tk.Toplevel(self.widget)
        self.window.overrideredirect(True)
        self.window.configure(bg='#454e56')
        text = self.text() if callable(self.text) else self.text
        tk.Label(self.window,text=text,bg='#30363c',fg='#e7e7e7',padx=9,pady=4).pack(padx=1,pady=1)
        self.window.geometry(f'+{self.widget.winfo_rootx()}+{max(0,self.widget.winfo_rooty()-35)}')

    def hide(self, event=None):
        if self.job:
            self.widget.after_cancel(self.job); self.job = None
        if self.window:
            self.window.destroy(); self.window = None


# The split preserves the playback branch's native sample rate/channel layout.
# Only visualization is resampled. FFmpeg FFT runs inside the playback engine.
SPECTRUM_FILTER = (
    '[aid1]asplit[ao][analysis];'
    '[analysis]aresample=44100,'
    # showfreqs log scale is fixed at 0..-120 dB (minamp <= 1e-6).
    # Crop the upper half of a double-height plot for an honest 0..-60 dB
    # display, instead of lifting quiet frequencies with visual normalization.
    'showfreqs=s=1200x360:rate=30:mode=bar:ascale=log:fscale=log:'
    'win_size=4096:win_func=hann:averaging=2:colors=0xff9c38|0xff6128,'
    'crop=1200:180:0:0,'
    # Keep spectrum in packed RGB; discard transparent background without
    # CPU RGB->YUV conversion and
    # a second color conversion in the GPU renderer. Audio branch is untouched.
    'format=rgb0[vo]'
)


class SpectrumAxis(tk.Canvas):
    """Ticks aligned to showfreqs' frequency and amplitude transformations."""
    def __init__(self, parent, vertical=False):
        super().__init__(parent, bg='#202428', highlightthickness=0,
                         **({'width': 34, 'height': SPECTRUM_PLOT_HEIGHT} if vertical else {'height': 21}))
        self.vertical = vertical
        self.bind('<Configure>', lambda e: self.draw())

    def draw(self):
        self.delete('all')
        width, height = self.winfo_width(), self.winfo_height()
        if self.vertical:
            for db in (0, -20, -40, -60):
                self.create_text(width-3, max(7,min(height-7,height*(-db/60))), text=str(db), anchor='e',
                                 fill='#89939b', font=(ui_font(),8))
        else:
            for hz in (0, 250, 500, 1000, 2000, 4000, 8000, 22050):
                fft_bin = min(2047, hz * 4096 / 44100)
                fraction = (1200 - 1200 ** ((2048-fft_bin-1)/2047)) / 1200
                x = max(1, min(width-1, fraction*width))
                label = '22k Hz' if hz==22050 else f'{hz//1000}k' if hz>=1000 else str(hz)
                anchor = 'w' if hz==0 else 'e' if hz==22050 else 'center'
                self.create_text(x, 11, text=label, anchor=anchor, fill='#89939b', font=(ui_font(),8))
