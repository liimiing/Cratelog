"""Canvas-only image viewer: alpha-composited controls and one input surface."""
import math
import sys
from PIL import Image, ImageDraw, ImageTk
from cratelog_platform import load_tk

tk=load_tk()

def visible_screens(window):
    """Tk-coordinate work areas; Cocoa excludes the menu bar and Dock."""
    if sys.platform=='darwin':
        import json,subprocess
        script="""ObjC.import('AppKit');
var screens=$.NSScreen.screens, top=screens.objectAtIndex(0).frame;
var ymax=top.origin.y+top.size.height, out=[];
for(var i=0;i<screens.count;i++) {var r=screens.objectAtIndex(i).visibleFrame;
out.push([r.origin.x,ymax-r.origin.y-r.size.height,r.size.width,r.size.height]);}
JSON.stringify(out);"""
        try:
            result=subprocess.run(['/usr/bin/osascript','-l','JavaScript','-e',script],capture_output=True,text=True,timeout=3,check=True)
            areas=json.loads(result.stdout)
            if areas and all(len(a)==4 and a[2]>0 and a[3]>0 for a in areas):return areas
        except (OSError,ValueError,subprocess.SubprocessError):pass
    # Conservative fallback for environments without a work-area API.
    return [(window.winfo_vrootx(),window.winfo_vrooty()+32,window.winfo_screenwidth(),max(1,window.winfo_screenheight()-112))]


def bounded_geometry(width,height,cx,cy,areas,decoration=40):
    area=next((a for a in areas if a[0]<=cx<a[0]+a[2] and a[1]<=cy<a[1]+a[3]),None)
    if area is None:area=min(areas,key=lambda a:(cx-a[0]-a[2]/2)**2+(cy-a[1]-a[3]/2)**2)
    sx,sy,sw,sh=area
    width=max(1,min(round(width),int(sw)-16))
    height=max(1,min(round(height),int(sh)-decoration-16))
    x=round(max(sx+8,min(cx-width/2,sx+sw-width-8)))
    y=round(max(sy+8,min(cy-height/2,sy+sh-height-decoration-8)))
    return width,height,x,y


class PictureCanvas(tk.Canvas):
    def __init__(self,master,image,on_step,on_zoom=None,on_error=None,**kwargs):
        super().__init__(master,bg='#151719',highlightthickness=0,takefocus=True,**kwargs)
        self.on_step=on_step;self.on_zoom=on_zoom;self.base_fit=None;self.source=image;self.picture=image
        self.zoom=1.;self.offset=[0.,0.];self.rotation=0;self.fit_locked=False
        self.gestures=None;self.gesture_job=None;self.on_error=on_error
        self.pointer=None;self.drag=None;self.job=None;self.photo=None;self.controls=[]
        self.bind('<Configure>',lambda e:self.redraw())
        self.bind('<Motion>',self.motion);self.bind('<Leave>',self.leave)
        self.bind('<ButtonPress-1>',self.press);self.bind('<B1-Motion>',self.motion);self.bind('<ButtonRelease-1>',self.release)
        self.bind('<MouseWheel>',self.wheel)
        # Tk 9 precise devices emit TouchpadScroll, not MouseWheel. Register raw
        # substitutions because older Python tkinter does not expose its delta.
        try:
            callback=self.register(self.touchpad)
            self.tk.call('bind',self._w,'<TouchpadScroll>',callback+' %D %x %y; break')
        except tk.TclError:
            self.deletecommand(callback)  # Tk 8.6 continues using MouseWheel.

        self.bind('<Button-4>',lambda e:self.scale(1.12,e.x,e.y))
        self.bind('<Button-5>',lambda e:self.scale(1/1.12,e.x,e.y))
        self.bind('<Destroy>',self.destroyed)
        if sys.platform=='darwin':self.bind('<Map>',self.gesture_mapped,add='+')
    def gesture_mapped(self,event):
        if event.widget is self and self.gestures is None and self.gesture_job is None:
            # A timer runs after Map processing; update_idletasks cannot fire it
            # prematurely while the toplevel is still being constructed.
            self.gesture_job=self.after(30,self.attach_gestures)
    def attach_gestures(self):
        self.gesture_job=None
        if not self.winfo_viewable() or self.gestures is not None:return
        try:
            from cratelog_gestures import PictureGestures
            self.gestures=PictureGestures(self)
        except (OSError,RuntimeError,AttributeError) as error:
            if self.on_error:self.on_error(str(error))
    def pan(self,dx,dy):
        self.offset[0]+=dx;self.offset[1]+=dy;self.redraw()
    def set_image(self,image):
        self.source=image;self.picture=image;self.base_fit=None;self.fit_locked=False;self.rotation=0;self.zoom=1.;self.offset[:]=[0.,0.];self.drag=None
        self.redraw()
    def dimensions(self):
        w,h=max(1,self.winfo_width()),max(1,self.winfo_height())
        fit=min(1,max(1,w-24)/self.picture.width,max(1,h-24)/self.picture.height)
        # Geometry changes arrive asynchronously, sometimes after the first paint.
        # Follow the viewport until an explicit zoom freezes its reference scale.
        if self.base_fit is None or not self.fit_locked:self.base_fit=fit
        return w,h,self.base_fit*self.zoom
    def redraw(self):
        if self.job is None:self.job=self.after(16,self.paint)
    def destroyed(self,event):
        if event.widget is self:
            if self.gesture_job is not None:self.after_cancel(self.gesture_job);self.gesture_job=None
            if self.gestures:self.gestures.close();self.gestures=None
        if event.widget is self and self.job is not None:
            self.after_cancel(self.job);self.job=None
    def paint(self):
        self.job=None
        w,h,scale=self.dimensions()
        # Render only the viewport, so zoom does not allocate a giant bitmap.
        left=(w-self.picture.width*scale)/2+self.offset[0]
        top=(h-self.picture.height*scale)/2+self.offset[1]
        frame=self.picture.transform((w,h),Image.Transform.AFFINE,(1/scale,0,-left/scale,0,1/scale,-top/scale),Image.Resampling.BILINEAR,fillcolor='#151719').convert('RGBA')
        overlay=Image.new('RGBA',(w,h));pen=ImageDraw.Draw(overlay);self.controls=[]
        if self.pointer is not None:
            px,py=self.pointer
            if py<64:
                for i in range(3):
                    cx=w/2+(i-1)*42;cy=27;r=16
                    box=(cx-r,cy-r,cx+r,cy+r);self.controls.append(box)
                    hot=abs(px-cx)<=r and abs(py-cy)<=r
                    pen.ellipse(box,fill=(30,33,36,185 if hot else 125))
                    color=(255,255,255,230)
                    if i==0:
                        pen.arc((cx-8,cy-8,cx+8,cy+8),35,315,fill=color,width=2)
                        pen.polygon([(cx+8,cy-7),(cx+2,cy-7),(cx+8,cy-1)],fill=color)
                    else:
                        pen.line((cx-7,cy,cx+7,cy),fill=color,width=2)
                        if i==1:pen.line((cx,cy-7,cx,cy+7),fill=color,width=2)
            if self.on_step is not None:
                right=px>=w/2;cx=w-26 if right else 26;cy=h-27;direction=1 if right else -1
                pen.line((cx-direction*5,cy-9,cx+direction*4,cy,cx-direction*5,cy+9),fill=(255,255,255,100),width=2)
        frame=Image.alpha_composite(frame,overlay)
        self.photo=ImageTk.PhotoImage(frame)
        if not self.find_withtag('viewport'):self.create_image(0,0,anchor='nw',tags='viewport',image=self.photo)
        else:self.itemconfigure('viewport',image=self.photo)
    def motion(self,event):
        old=self.pointer;self.pointer=(event.x,event.y)
        if self.drag is not None:
            x,y,ox,oy,moved=self.drag;dx,dy=event.x-x,event.y-y
            if abs(dx)+abs(dy)>4:self.drag[4]=True
            if self.drag[4]:self.offset[:]=[ox+dx,oy+dy];self.redraw()
        elif old is None or (old[1]<64)!=(event.y<64) or (old[0]<self.winfo_width()/2)!=(event.x<self.winfo_width()/2) or event.y<64:self.redraw()
        return 'break'
    def leave(self,event):
        self.pointer=None;self.redraw()
    def press(self,event):
        self.focus_set();self.drag=None
        if self.pointer is not None and event.y<64:
            for i,(x1,y1,x2,y2) in enumerate(self.controls):
                if x1<=event.x<=x2 and y1<=event.y<=y2:
                    if i==0:
                        self.rotation=(self.rotation+90)%360;self.picture=self.source.rotate(-self.rotation,expand=True);self.base_fit=None;self.offset[:]=[0.,0.];self.redraw()
                    else:self.scale(1.2 if i==1 else 1/1.2)
                    return 'break'
        self.drag=[event.x,event.y,*self.offset,False]
        return 'break'
    def release(self,event):
        drag=self.drag;self.drag=None
        if drag is not None and not drag[4] and self.on_step is not None:self.on_step(-1 if event.x<self.winfo_width()/2 else 1)
        return 'break'
    def scale(self,factor,x=None,y=None):
        w,h,_=self.dimensions()
        self.fit_locked=True
        old=self.zoom;self.zoom=max(.25,min(8,self.zoom*factor));ratio=self.zoom/old
        x=w/2 if x is None else x;y=h/2 if y is None else y
        self.offset[:]=[(x-w/2)*(1-ratio)+self.offset[0]*ratio,(y-h/2)*(1-ratio)+self.offset[1]*ratio]
        if self.on_zoom and self.zoom>old:
            self.on_zoom(self.picture.width*self.base_fit*self.zoom,self.picture.height*self.base_fit*self.zoom)
        self.redraw();return 'break'
    def touchpad(self,raw,x,y):
        # Same signed low-word decoding as tk::PreciseScrollDeltas.
        low=int(raw)&0xffff
        dy=low if low<0x8000 else low-0x10000
        dx=int(raw)>>16
        self.pan(dx,dy)
        return 'break'
    def wheel(self,event):
        delta=float(event.delta)
        if sys.platform!='darwin':delta/=120
        return self.scale(math.exp(max(-3,min(3,delta))*.14),event.x,event.y)
