"""Isolated OpenGL turntable renderer. Tk owns UI; a child owns its GL context."""
import json
import math
import os
from pathlib import Path
import queue
import struct
import subprocess
import sys
import threading
import time
from cratelog_i18n import tr


def album_progress(album,identity,position,duration=0):
    tracks=album.get('tracks',[])
    lengths=[album.get('_durations',{}).get(t['filename'],{}).get('seconds') or 0 for t in tracks]
    known=[n for n in lengths if n>0]
    fallback=sum(known)/len(known) if known else max(duration,180)
    lengths=[n if n>0 else fallback for n in lengths]
    index=next((i for i,t in enumerate(tracks) if t['filename']==identity),None)
    if index is None:return 0.,False
    return min(1.,max(0.,(sum(lengths[:index])+min(position,lengths[index]))/max(1,sum(lengths)))),True


# Published stationary-speed references; dot counts approximate the visible pattern,
# not an undocumented factory machining specification.
STROBE_REFERENCES=(.064,.033,0.,-.033)
STROBE_COUNTS=(169,174,180,186)


def strobe_rates(rpm,nominal):
    return tuple((rpm-nominal*(1+reference))*count/60
                 for reference,count in zip(STROBE_REFERENCES,STROBE_COUNTS))


SPINDLE=(-.57,-.12)
PIVOT=(1.30,SPINDLE[1]-math.sqrt(2.15**2-1.87**2))


def tonearm_geometry(progress,arm=1.):
    """230 mm effective length, 215 mm pivot spacing, fixed 22 degree offset."""
    r=1.46+( .60-1.46)*max(0.,min(1.,progress));length=2.30;distance=2.15
    a=(r*r-length*length+distance*distance)/(2*distance)
    h=math.sqrt(max(0.,r*r-a*a));u=tuple((PIVOT[i]-SPINDLE[i])/distance for i in (0,1))
    t=(SPINDLE[0]+a*u[0]-h*u[1],SPINDLE[1]+a*u[1]+h*u[0])
    angle=-.22*(1-arm)+math.atan2(t[0]-PIVOT[0],t[1]-PIVOT[1])*arm
    direction=(math.sin(angle),math.cos(angle));tip=tuple(PIVOT[i]+length*direction[i] for i in (0,1))
    c=math.cos(math.radians(22));s=math.sin(math.radians(22))
    cartridge=(c*direction[0]-s*direction[1],s*direction[0]+c*direction[1])
    return tip,direction,cartridge


def camera_eye(yaw=.666,elevation=.596,distance=12.9):
    return (distance*math.cos(elevation)*math.sin(yaw),
            .15+distance*math.sin(elevation),distance*math.cos(elevation)*math.cos(yaw))


def deck_point(x,y,width,height,eye=None,plane=.32):
    # Same perspective camera as the shader. Intersect the top plate for picking.
    def norm(v):
        length=math.sqrt(sum(a*a for a in v));return tuple(a/length for a in v)
    def cross(a,b):return (a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0])
    eye=eye or (6.6,7.4,8.4);fw=norm((-eye[0],.15-eye[1],-eye[2]));rt=norm(cross(fw,(0,1,0)));up=cross(rt,fw)
    unit=max(1,min(height,width/1.5))
    u=(x-width/2)/unit;v=(height/2-y)/unit
    ray=norm(tuple(fw[i]*2.5+rt[i]*u+up[i]*v for i in range(3)))
    if ray[1]>=0:return None
    t=(plane-eye[1])/ray[1]
    return eye[0]+ray[0]*t,eye[2]+ray[2]*t


def read_exact(stream,size):
    result=bytearray()
    while len(result)<size:
        part=stream.read(size-len(result))
        if not part:raise EOFError(tr('唱机渲染进程已退出'))
        result.extend(part)
    return bytes(result)


class RenderClient:
    def __init__(self):
        self.requests=queue.Queue(maxsize=1);self.results=queue.Queue(maxsize=1)
        self.closed=False;self.process=None
        self.thread=threading.Thread(target=self.run,daemon=True);self.thread.start()
    def run(self):
        try:
            executable=Path(sys.executable)
            if executable.name.lower()=='pythonw.exe':executable=executable.with_name('python.exe')
            command=[str(executable),str(Path(__file__).resolve()),'--worker']
            if getattr(sys,'frozen',False):
                helper=Path(__file__).resolve().parent/'worker'/('CratelogRender.exe' if os.name=='nt' else 'CratelogRender')
                command=[str(helper)]
            self.process=subprocess.Popen(command,
                stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,
                creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            while not self.closed:
                state=self.requests.get()
                if state is None:break
                self.process.stdin.write((json.dumps(state)+'\n').encode());self.process.stdin.flush()
                size=struct.unpack('!I',read_exact(self.process.stdout,4))[0]
                if size>8_000_000:raise ValueError('Invalid renderer frame')
                data=read_exact(self.process.stdout,size)
                if size!=state['width']*state['height']*3:raise RuntimeError(data.decode('utf-8',errors='replace'))
                self.results.put((state['width'],state['height'],data))
        except Exception as error:
            if not self.closed:
                try:self.results.put_nowait((0,0,str(error).encode()))
                except queue.Full:pass
        finally:
            if self.process:
                if self.process.poll() is None:self.process.kill()
                self.process.wait()
                for pipe in (self.process.stdin,self.process.stdout):pipe.close()
    def close(self):
        self.closed=True
        if self.process and self.process.poll() is None:self.process.kill()
        try:self.requests.put_nowait(None)
        except queue.Full:pass


def create_view(master,player,on_error):
    import tkinter as tk
    from PIL import Image,ImageTk,ImageDraw
    class View(tk.Canvas):
        def __init__(self):
            super().__init__(master,bg='#12151a',highlightthickness=0)
            self.player=player;self.client=None;self.pending=False;self.job=None
            self.strobe=[0.,0.,0.,0.];self.angle=0.;self.arm=0.;self.velocity=0.;self.groove=0.;self.identity='';self.continuous_target=None;self.transition=0.;self.lamp=1.;self.lamp_target=1.;self.lift=0.;self.pitch=0.;self.rpm=100/3
            self.yaw=.666;self.elevation=.596;self.distance=12.9;self.menu_open=False;self.menu_offset=0;self.frame=None;self.hits=[];self.orbit_drag=None
            from cratelog_widgets import transport_icon
            self.menu_icon=transport_icon('list',width=20)
            self.pad_visible=False;self.head_drag=None;self.cue_index=None;self.speed_mix=0.;self.power=True;self.room_light=True
            self.requested_at=0.;self.last=time.monotonic();self.active=False;self.drag_pitch=False;self.photo=None
            self.bind('<Button-1>',self.click);self.bind('<B1-Motion>',self.drag)
            self.bind('<ButtonRelease-1>',self.release)
            self.bind('<Motion>',self.hover);self.bind('<Leave>',self.leave)
            self.bind('<MouseWheel>',self.wheel)
            self.bind('<Button-4>',lambda e:self.wheel(e,1));self.bind('<Button-5>',lambda e:self.wheel(e,-1))
            try:
                callback=self.register(self.touchpad)
                self.tk.call('bind',self._w,'<TouchpadScroll>',callback+' %D %x %y; break')
            except tk.TclError:self.deletecommand(callback)
            self.bind('<Destroy>',lambda e:self.close() if e.widget is self else None)
        def show(self):
            self.active=True;self.last=time.monotonic();self.requested_at=time.monotonic()
            if not self.client:self.client=RenderClient()
            if self.job is None:self.tick()
        def hide(self):
            self.active=False
            if self.job:self.after_cancel(self.job);self.job=None
        def close(self):
            self.hide()
            if self.client:self.client.close();self.client=None
        def state(self):
            p=self.player;album=p.album or {};identity=''
            if p.folder and p.current_track_id:
                try:identity=p.current_track_id.relative_to(p.folder).as_posix()
                except ValueError:pass
            progress,matched=album_progress(album,identity,p.position.get(),p.duration)
            if not self.power and p.playback_state!='stopped':p.stop()
            running=self.power and matched and p.playback_state=='playing'
            if self.head_drag is not None:
                tracks=album.get('tracks',[])
                if tracks:progress,_=album_progress(album,tracks[self.cue_index]['filename'],0,p.duration)
                target_arm=1.
            else:target_arm=None
            target=target_arm if target_arm is not None else (1. if matched and p.playback_state!='stopped' else 0.)
            dt=min(.15,time.monotonic()-self.last);self.last=time.monotonic()
            if identity!=self.identity:
                self.identity=identity
                self.transition=0. if self.continuous_target==p.current_track_id else time.monotonic()
                self.continuous_target=None
            travelling=max(0.,1.-(time.monotonic()-self.transition)/.8)
            self.speed_mix+=((1. if self.rpm==45. else 0.)-self.speed_mix)*min(1,dt*18.)
            self.lamp+=(self.lamp_target-self.lamp)*min(1,dt*12.)
            self.arm+=(target-self.arm)*min(1,dt*3.5)
            self.groove+=(progress-self.groove)*min(1,dt*8.)
            self.velocity+=((self.rpm*(1+self.pitch*.08) if running else 0.)-self.velocity)*min(1,dt*5.)
            self.angle=(self.angle+dt*self.velocity*math.tau/60)%math.tau
            self.strobe=[(phase+dt*rate)%1 for phase,rate in zip(self.strobe,strobe_rates(self.velocity,self.rpm))]
            w=max(1,self.winfo_width());h=max(1,self.winfo_height());scale=min(1,1200/w,800/h)
            images=album.get('images',[])
            cover=str(p.folder/images[0]['filename']) if p.folder and images else ''
            return dict(eye=camera_eye(self.yaw,self.elevation,self.distance),width=max(2,int(w*scale)),height=max(2,int(h*scale)),rotation=self.angle,strobe=self.strobe,velocity=self.velocity,
                        room_light=self.room_light,power=self.power,speed_mix=self.speed_mix,progress=self.groove,arm=self.arm,lift=max(self.lift,math.sin(travelling*math.pi)),lamp=self.lamp,pitch=self.pitch,cover=cover)
        def tick(self):
            self.job=None
            if not self.active:return
            if not self.winfo_viewable():
                self.last=time.monotonic();self.job=self.after(200,self.tick);return
            try:
                if self.pending:
                    if time.monotonic()-self.requested_at>20:raise RuntimeError(tr('OpenGL 唱机渲染超时，请检查显卡驱动。'))
                    try:w,h,data=self.client.results.get_nowait()
                    except queue.Empty:pass
                    else:
                        self.pending=False
                        if w==0:raise RuntimeError(data.decode('utf-8',errors='replace'))
                        image=Image.frombytes('RGB',(w,h),data).transpose(Image.Transpose.FLIP_TOP_BOTTOM)
                        if image.size!=(self.winfo_width(),self.winfo_height()):image=image.resize((max(1,self.winfo_width()),max(1,self.winfo_height())),Image.Resampling.BILINEAR)
                        self.frame=image;self.paint_overlay()
                if not self.pending:
                    self.client.requests.put_nowait(self.state());self.pending=True;self.requested_at=time.monotonic()
            except Exception as error:
                self.close();on_error(str(error));return
            self.job=self.after(33,self.tick)
        def paint_overlay(self):
            if self.frame is None:return
            image=self.frame.convert('RGBA');w,h=image.size
            overlay=Image.new('RGBA',image.size);draw=ImageDraw.Draw(overlay)
            self.delete('hud');self.hits=[]
            texts=[(16,h-22,f'{self.rpm:.2f} RPM   {self.pitch*8:+.1f}%   ×{self.rpm/(100/3)*(1+self.pitch*.08):.3f}','#b7c3d1')]
            if self.menu_open:
                tracks=(self.player.album or {}).get('tracks',[])
                count=max(1,min(12,(h-134)//28));self.menu_count=count
                self.menu_offset=max(0,min(self.menu_offset,max(0,len(tracks)-count)))
                width=min(370,w-24);height=42+min(count,len(tracks))*28
                left=10;right=left+width
                self.menu_bounds=(left,44,right,height+44)
                draw.rounded_rectangle(self.menu_bounds,12,fill=(12,17,24,210),outline=(255,255,255,40))
                texts.append((left+14,62,tr('曲目  ·  滚轮翻页'),'#b7c3d1'))
                for row,track in enumerate(tracks[self.menu_offset:self.menu_offset+count]):
                    index=self.menu_offset+row;y=89+row*28
                    source=self.player.album.get('_track_sources',{}).get(track['filename'],{})
                    info=self.player.album.get('_durations',{}).get(track['filename'],{})
                    title=source.get('title') or info.get('title') or track['filename']
                    text=f"{index+1:02}  {title}"
                    import tkinter.font as tkfont
                    font=tkfont.Font(self,font=('TkDefaultFont',11))
                    if font.measure(text)>width-35:
                        while text and font.measure(text+'…')>width-35:text=text[:-1]
                        text+='…'
                    active=index==self.cue_index if self.head_drag is not None else self.player.current_track_id==self.player.folder/track['filename']
                    if active:draw.rounded_rectangle((left+4,y-12,right-4,y+12),5,fill=(255,166,77,40))
                    texts.append((left+14,y,text,'#ffb66b' if active else '#edf0f5'))
                    self.hits.append(((left,y-13,right,y+13),('track',index)))
            if self.pad_visible:
                x=max(4,w-176);y=max(4,h-106)
                draw.rounded_rectangle((x,y,x+166,h-10),12,fill=(12,17,24,165),outline=(255,255,255,35))
                for dx,dy,label,action in [(25,48,'‹','left'),(75,22,'⌃','up'),(75,48,'↺','home'),(125,48,'›','right'),(75,76,'⌄','down')]:
                    texts.append((x+dx,y+dy,label,'#e9eef5'))
                    self.hits.append(((x+dx-18,y+dy-13,x+dx+18,y+dy+13),('camera',action)))
            bulb='#f6d58b' if self.room_light else '#8593a5'
            draw.ellipse((52,14,64,26),outline=bulb,width=2)
            draw.line((55,25,55,30,61,30,61,25),fill=bulb,width=2)
            draw.line((56,33,60,33),fill=bulb,width=2)
            if self.room_light:
                for line in [(58,8,58,10),(47,13,49,15),(67,13,69,11),(45,21,48,21),(68,21,71,21)]:draw.line(line,fill=bulb,width=1)
            else:draw.line((48,34,68,12),fill=bulb,width=2)
            self.hits.append(((44,6,76,40),('lighting','toggle')))
            self.photo=ImageTk.PhotoImage(Image.alpha_composite(image,overlay))
            if not self.find_withtag('scene'):self.create_image(0,0,anchor='nw',image=self.photo,tags='scene')
            else:self.itemconfigure('scene',image=self.photo)
            for x,y,text,color in texts:self.create_text(x,y,text=text,fill=color,anchor='w',font=('TkDefaultFont',11),tags='hud')
            self.create_image(16,14,anchor='nw',image=self.menu_icon,tags='hud')
            self.tag_raise('hud')
        def in_menu(self,event):
            x1,y1,x2,y2=getattr(self,'menu_bounds',(0,0,0,0))
            return self.menu_open and x1<=event.x<=x2 and y1<=event.y<=y2
        def hover(self,event):
            opened=self.head_drag is not None or self.in_menu(event) or (event.x<42 and event.y<48)
            pad=event.x>self.winfo_width()-186 and event.y>self.winfo_height()-116
            if opened!=self.menu_open or pad!=self.pad_visible:
                self.menu_open=opened;self.pad_visible=pad;self.paint_overlay()
        def leave(self,event):
            self.pad_visible=False
            if self.head_drag is None:self.menu_open=False
            self.paint_overlay()
        def wheel(self,event,step=None):
            if step is None:
                delta=float(event.delta);step=delta if sys.platform=='darwin' else delta/120
            step=max(-3,min(3,step))
            if self.in_menu(event):
                self.menu_offset=max(0,self.menu_offset+(-1 if step>0 else 1));self.paint_overlay()
            else:self.distance=max(4.2,min(22.,self.distance*math.exp(-step*.09)))
            return 'break'
        def touchpad(self,raw,x,y):
            from types import SimpleNamespace
            low=int(raw)&0xffff;dy=low if low<0x8000 else low-0x10000
            if dy:self.wheel(SimpleNamespace(x=int(x),y=int(y)),dy/30)
            return 'break'
        def release(self,event):
            self.drag_pitch=False;self.orbit_drag=None
            if self.head_drag is not None:
                self.head_drag=None;self.lift=0.
                self.play_track(self.cue_index);self.paint_overlay()
        def play_track(self,index):
            if not self.power:return
            self.player.tracks.selection_set(str(index));self.player.tracks.focus(str(index))
            self.player.tracks.see(str(index));self.player.play_selected();self.pitch_control()
        def show_cue(self):
            count=getattr(self,'menu_count',12)
            if self.cue_index<self.menu_offset:self.menu_offset=self.cue_index
            elif self.cue_index>=self.menu_offset+count:self.menu_offset=self.cue_index-count+1
            self.paint_overlay()
        def toggle_power(self):
            self.power=not self.power
            if not self.power:
                self.head_drag=None;self.drag_pitch=False;self.lift=0.
                self.player.stop()
        def pitch_control(self):
            # Disable time-stretch compensation: playback rate now changes pitch too.
            self.player.control('set_property','audio-pitch-correction',False)
            self.player.control('set_property','speed',self.rpm/(100/3)*(1+self.pitch*.08))

        def click(self,event):
            for (x1,y1,x2,y2),(kind,value) in self.hits:
                if x1<=event.x<=x2 and y1<=event.y<=y2:
                    if kind=='lighting':
                        self.room_light=not self.room_light;self.paint_overlay()
                    elif kind=='track':
                        self.play_track(value)
                    elif value=='home':self.yaw=.666;self.elevation=.596;self.distance=12.9
                    elif value=='left':self.yaw-=.15
                    elif value=='right':self.yaw+=.15
                    elif value=='up':self.elevation=min(1.35,self.elevation+.10)
                    elif value=='down':self.elevation=max(.18,self.elevation-.10)
                    return 'break'
            if self.in_menu(event):return 'break'
            point=deck_point(event.x,event.y,self.winfo_width(),self.winfo_height(),camera_eye(self.yaw,self.elevation,self.distance))
            p=self.player
            tip,_,_=tonearm_geometry(self.groove,self.arm)
            head=deck_point(event.x,event.y,self.winfo_width(),self.winfo_height(),camera_eye(self.yaw,self.elevation,self.distance),.55+self.lift*.27)
            tracks=(p.album or {}).get('tracks',[])
            if self.power and head and math.dist(head,tip)<.28 and tracks:
                self.cue_index=next((i for i,t in enumerate(tracks) if p.folder/t['filename']==p.current_track_id),0)
                self.head_drag=(event.x,self.cue_index);self.lift=1.;self.menu_open=True
                if p.playback_state=='playing':p.toggle_pause()
                self.show_cue();return 'break'
            if point is None:
                self.orbit_drag=(event.x,event.y,self.yaw,self.elevation);return 'break'
            x,z=point
            if abs(x+2.03)<.2 and abs(z-.94)<.2:self.toggle_power()
            elif not self.power:
                self.orbit_drag=(event.x,event.y,self.yaw,self.elevation)
            elif abs(x+1.91)<.3 and abs(z-1.39)<.23:p.toggle_pause()
            elif abs(x+1.295)<.26 and abs(z-1.61)<.10:
                self.rpm=100/3 if x<-1.295 else 45.;self.pitch_control()
            elif abs(x-.54)<.20 and abs(z-1.54)<.16:self.lamp_target=1.-self.lamp_target
            elif abs(x-1.93)<.22 and -.15<z<1.15:self.drag_pitch=True;self.drag(event)
            elif abs(x-1.93)<.2 and abs(z-1.29)<.12:
                self.pitch=0.;self.pitch_control()
            elif abs(x-1.70)<.2 and abs(z+.73)<.18:
                self.lift=1.-self.lift
                if self.lift and p.playback_state=='playing':p.toggle_pause()
                elif not self.lift and p.playback_state=='paused':p.toggle_pause()
            else:self.orbit_drag=(event.x,event.y,self.yaw,self.elevation)
            return 'break'
        def drag(self,event):
            if self.head_drag is not None:
                x,index=self.head_drag;tracks=(self.player.album or {}).get('tracks',[])
                self.cue_index=max(0,min(len(tracks)-1,index-round((event.x-x)/36)))
                self.show_cue();return 'break'
            if self.orbit_drag:
                x,y,yaw,elevation=self.orbit_drag
                self.yaw=yaw-(event.x-x)*.008;self.elevation=max(.18,min(1.35,elevation+(event.y-y)*.006))
            if self.drag_pitch:
                point=deck_point(event.x,event.y,self.winfo_width(),self.winfo_height(),camera_eye(self.yaw,self.elevation,self.distance))
                if point:
                    self.pitch=max(-1,min(1,(point[1]-.52)/.55))
                    self.pitch_control()
            return 'break'
    return View()


def worker():
    from PIL import Image,ImageDraw,ImageFont,ImageOps
    import pyglet
    pyglet.options['shadow_window']=False
    from pyglet import gl
    from pyglet.graphics.shader import Shader,ShaderProgram
    window=pyglet.window.Window(width=900,height=600,visible=False,vsync=False,
                               config=gl.Config(major_version=3,minor_version=3,double_buffer=False))
    window.switch_to()
    vertex=Shader('#version 330 core\nin vec2 position;void main(){gl_Position=vec4(position,0,1);}', 'vertex')
    fragment=Shader(Path(__file__).with_suffix('.frag').read_text(encoding='utf-8'),'fragment')
    program=ShaderProgram(vertex,fragment)
    quad=program.vertex_list(6,gl.GL_TRIANGLES,position=('f',(-1,-1,1,-1,1,1,-1,-1,1,1,-1,1)))
    def texture(image):
        data=pyglet.image.ImageData(image.width,image.height,'RGBA',image.tobytes(),pitch=-image.width*4)
        return data.get_texture()
    panel=Image.new('RGBA',(1359,1059));draw=ImageDraw.Draw(panel)
    try:font=ImageFont.truetype('DejaVuSans.ttf',20)
    except OSError:font=ImageFont.load_default(size=20)
    def label(x,z,text,size=font):draw.text(((x+2.265)*300,(z+1.765)*300),text,font=size,fill=(26,30,34,255))
    label(.75,1.42,'CRATELOG');label(.75,1.52,'DIRECT DRIVE');label(-2.10,1.40,'START / STOP')
    label(-1.50,1.51,'33');label(-1.23,1.51,'45');label(1.70,-.24,'PITCH');label(1.73,1.42,'RESET');label(1.64,-.06,'-8');label(1.64,1.02,'+8')
    for i in range(-4,5):
        z=.52+i*.135
        draw.line([(1190,(z+1.765)*300),(1205,(z+1.765)*300)],fill=(20,20,20,255),width=2)
    panel_tex=texture(panel);cover_tex=texture(Image.new('RGBA',(256,256),'#bd692d'));last_cover=None
    # A dedicated FBO avoids hidden-window/Retina framebuffer sizing differences.
    fbo=gl.GLuint();gl.glGenFramebuffers(1,fbo);gl.glBindFramebuffer(gl.GL_FRAMEBUFFER,fbo)
    output=gl.GLuint();gl.glGenTextures(1,output);last_size=None
    for line in sys.stdin.buffer:
        state=json.loads(line);ow,oh=state['width'],state['height'];w,h=ow*2,oh*2
        if (w,h)!=last_size:
            gl.glBindTexture(gl.GL_TEXTURE_2D,output)
            gl.glTexImage2D(gl.GL_TEXTURE_2D,0,gl.GL_RGB8,w,h,0,gl.GL_RGB,gl.GL_UNSIGNED_BYTE,None)
            gl.glTexParameteri(gl.GL_TEXTURE_2D,gl.GL_TEXTURE_MIN_FILTER,gl.GL_LINEAR)
            gl.glTexParameteri(gl.GL_TEXTURE_2D,gl.GL_TEXTURE_MAG_FILTER,gl.GL_LINEAR)
            gl.glFramebufferTexture2D(gl.GL_FRAMEBUFFER,gl.GL_COLOR_ATTACHMENT0,gl.GL_TEXTURE_2D,output,0)
            if gl.glCheckFramebufferStatus(gl.GL_FRAMEBUFFER)!=gl.GL_FRAMEBUFFER_COMPLETE:raise RuntimeError('OpenGL framebuffer unavailable')
            last_size=(w,h)
        if state['cover']!=last_cover:
            cover_tex.delete()
            try:
                with Image.open(state['cover']) as image:cover_image=ImageOps.fit(ImageOps.exif_transpose(image).convert('RGBA'),(512,512))
            except (OSError,ValueError):cover_image=Image.new('RGBA',(512,512),'#bd692d')
            cover_tex=texture(cover_image);last_cover=state['cover']
        gl.glViewport(0,0,w,h);program.use()
        program['resolution']=(w,h)
        program['eye']=tuple(state.get('eye',(6.6,7.4,8.4)))
        for key in ('rotation','lamp','pitch'):program[key]=float(state[key])
        program['strobe_phase']=tuple(state.get('strobe',(0.,0.,0.,0.)))
        program['room_light']=float(state.get('room_light',True))
        program['power']=float(state.get('power',True))
        program['speed_mix']=float(state.get('speed_mix',0.))
        program['velocity']=float(state.get('velocity',0.))
        program['arm_direction']=tonearm_geometry(state['progress'],state['arm'])[1]
        program['elevation']=state['lift']*.12+(1.-state['arm'])*.04
        gl.glActiveTexture(gl.GL_TEXTURE0);gl.glBindTexture(cover_tex.target,cover_tex.id);program['cover']=0
        gl.glActiveTexture(gl.GL_TEXTURE1);gl.glBindTexture(panel_tex.target,panel_tex.id);program['panel']=1
        quad.draw(gl.GL_TRIANGLES)
        gl.glPixelStorei(gl.GL_PACK_ALIGNMENT,1)
        data=(gl.GLubyte*(w*h*3))();gl.glReadPixels(0,0,w,h,gl.GL_RGB,gl.GL_UNSIGNED_BYTE,data)
        packet=Image.frombytes('RGB',(w,h),bytes(data)).resize((ow,oh),Image.Resampling.LANCZOS).tobytes();sys.stdout.buffer.write(struct.pack('!I',len(packet))+packet);sys.stdout.buffer.flush()
    window.close()


if __name__=='__main__':
    try:worker()
    except Exception as error:
        message=(str(error)+'\n请在当前虚拟环境执行 python -m pip install -r requirements.txt，并确认显卡支持 OpenGL 3.3。').encode('utf-8')
        # Zero-size frames are represented by a JSON-independent error packet.
        sys.stdout.buffer.write(struct.pack('!I',len(message))+message);sys.stdout.buffer.flush()
