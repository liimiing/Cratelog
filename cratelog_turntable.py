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


SPINDLE=(-.53,0.)
PIVOT=(1.30,SPINDLE[1]-math.sqrt(2.15**2-1.83**2))


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


def advance_arm(arm, lift, target, dt):
    """Lift clear of the cradle before slewing; lower only at the destination."""
    moving=abs(target-arm)>0.0001
    lift_target=1. if moving else 0.
    lift=max(lift_target,lift-dt*2.5) if lift>lift_target else min(lift_target,lift+dt*4.)
    if moving and lift>=1.:
        step=dt*.85
        arm=min(target,arm+step) if target>arm else max(target,arm-step)
    return arm,lift


def needle_lift(manual, motion, remaining):
    # A loaded track starts raised: its transition must only descend.
    # A sine envelope starts at zero and would lift again mid-descent.
    return max(manual,motion,max(0.,min(1.,remaining)))


def camera_eye(yaw=.666,elevation=.596,distance=12.9):
    return (distance*math.cos(elevation)*math.sin(yaw),
            .15+distance*math.sin(elevation),distance*math.cos(elevation)*math.cos(yaw))


def exchange_pose(progress):
    def ease(a,b):
        t=max(0.,min(1.,(progress-a)/(b-a)));return t*t*(3.-2.*t)
    slide,lift,tilt,travel,land=(ease(a,b) for a,b in ((0.,.25),(.25,.40),(.40,.60),(.60,.82),(.82,1.)))
    center=(-.53+2.1*slide*(1.-travel),(.54+1.96*lift)*(1.-land)+.444*land,-2.625*(1.-travel))
    return center,tilt*math.pi/2,.98+.52*tilt


def exchange_view_distance(distance,progress):
    if progress<0:return distance
    def ease(value):
        t=max(0.,min(1.,value));return t*t*(3.-2.*t)
    weight=ease(progress/.25)*(1.-ease((progress-.82)/.18))
    return distance+(max(distance,20.)-distance)*weight


def track_menu_text(number,title,track,width,measure):
    suffix=(' ★' if track.get('highlighted') else '')+(' ✓' if track.get('selected') else '')
    text=f'{number:02}  {title}'
    if measure(text+suffix)>width:
        while text and measure(text+'…'+suffix)>width:text=text[:-1]
        text+='…'
    return text+suffix


def view_ray(x,y,width,height,eye=None):
    # Same perspective camera as the shader. Intersect the top plate for picking.
    def norm(v):
        length=math.sqrt(sum(a*a for a in v));return tuple(a/length for a in v)
    def cross(a,b):return (a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0])
    eye=eye or (6.6,7.4,8.4);fw=norm((-eye[0],.15-eye[1],-eye[2]));rt=norm(cross(fw,(0,1,0)));up=cross(rt,fw)
    unit=max(1,min(height,width/1.5))
    u=(x-width/2)/unit;v=(height/2-y)/unit
    ray=norm(tuple(fw[i]*2.5+rt[i]*u+up[i]*v for i in range(3)))
    return eye,ray


def deck_point(x,y,width,height,eye=None,plane=.32):
    eye,ray=view_ray(x,y,width,height,eye)
    if ray[1]>=0:return None
    t=(plane-eye[1])/ray[1]
    return eye[0]+ray[0]*t,eye[2]+ray[2]*t


def pending_disc_hit(x,y,width,height,eye):
    eye,ray=view_ray(x,y,width,height,eye)
    if abs(ray[2])<1e-6:return False
    distance=(-2.70-eye[2])/ray[2]
    if distance<=0:return False
    px,py=eye[0]+distance*ray[0],eye[1]+distance*ray[1]
    if abs(px+.53)>1.0 or abs(py-.54)>1.0:return False
    if ray[1]<0:
        for height_plane in (.46,.32):
            t=(height_plane-eye[1])/ray[1]
            if 0<t<distance:
                qx,qz=eye[0]+t*ray[0],eye[2]+t*ray[2]
                if height_plane==.46 and math.hypot(qx+.53,qz)<1.67:return False
                if height_plane==.32 and abs(qx)<2.27 and abs(qz)<1.77:return False
    return True


def power_hit(x,y,width,height,eye):
    # Match the raised cap; retain at least a 16 px target when zoomed out.
    center=deck_point(x,y,width,height,eye,.51)
    if center is None:return False
    nearby=[deck_point(x+dx,y+dy,width,height,eye,.51) for dx,dy in ((16,0),(0,16))]
    radius=max(.20,*(math.dist(center,p) for p in nearby if p is not None))
    return math.dist(center,(-2.03,.94))<=radius


def read_exact(stream,size):
    result=bytearray()
    while len(result)<size:
        part=stream.read(size-len(result))
        if not part:raise EOFError(tr('唱机渲染进程已退出'))
        result.extend(part)
    return bytes(result)


def completed_frame(results, requested_at, now):
    # A completed frame takes precedence over elapsed time (sleep/minimize).
    try:return results.get_nowait()
    except queue.Empty:
        if now-requested_at>20:raise TimeoutError('OpenGL renderer did not return a frame')
        return None


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
            super().__init__(master.winfo_toplevel(),bg='#12151a',highlightthickness=0)
            self.home_host=master;self.mounted_context=None;self.fullscreen_widgets=[];self.previous_fullscreen=False
            self.swap_disc=None;self.swap_started=None
            self.pending_disc=None;self.disc_generation=0;self.fullscreen=False;self.escape_binding=None
            self.native=None;self.native_failed=False;self.overlay_key=None;self.scratch=None;self.scratch_job=None
            self.gestures=None;self.gesture_job=None
            self.player=player;self.resume_pending=False;self.resume_generation=0;self.needle_ready=False;self.client=None;self.pending=False;self.job=None
            self.strobe=[0.,0.,0.,0.];self.angle=0.;self.arm=0.;self.velocity=0.;self.groove=0.;self.identity='';self.continuous_target=None;self.transition=0.;self.lamp=1.;self.lamp_target=1.;self.lift=0.;self.pitch=0.;self.rpm=100/3
            self.yaw=.666;self.elevation=.596;self.distance=12.9;self.menu_open=False;self.menu_offset=0;self.frame=None;self.hits=[];self.orbit_drag=None
            from cratelog_widgets import transport_icon
            self.menu_icon=transport_icon('list',width=20)
            self.pad_visible=False;self.head_drag=None;self.cue_index=None;self.speed_mix=0.;self.motion_lift=0.;self.key_until=0.;self.key_index=0;self.clip=0.;self.power=True;self.room_light=True
            self.render_retries=0;self.render_recovered_at=0.;self.last_tick=time.monotonic()
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
            if sys.platform=='darwin':self.bind('<Map>',self.gesture_mapped,add='+')
            self.escape_binding=self.winfo_toplevel().bind('<Escape>',self.exit_fullscreen,add='+')
            self.bind('<Destroy>',lambda e:self.close() if e.widget is self else None)
        def gesture_mapped(self,event):
            if event.widget is self and self.gestures is None and self.gesture_job is None:
                self.gesture_job=self.after(30,self.attach_gestures)
        def attach_gestures(self):
            self.gesture_job=None
            if not self.winfo_viewable() or self.gestures is not None:return
            try:
                from cratelog_gestures import PictureGestures
                self.gestures=PictureGestures(self,on_scale=self.pinch,on_scroll=self.native_scroll)
            except (OSError,RuntimeError,AttributeError) as error:
                from tkinter import messagebox
                messagebox.showwarning('Cratelog',str(error),parent=self.winfo_toplevel())
        def pinch(self,factor,x,y):
            if math.isfinite(factor) and factor>0:
                self.distance=max(4.2,min(22.,self.distance/factor))
        def native_scroll(self,dx,dy,x,y):
            from types import SimpleNamespace
            if dy:self.wheel(SimpleNamespace(x=x,y=y),dy/30.)
        def sync_playing_view(self):
            p=self.player
            if p.playback_state!='playing' or not p.folder or not p.current_track_id:return
            try:identity=p.current_track_id.relative_to(p.folder).as_posix()
            except ValueError:return
            progress,matched=album_progress(p.album or {},identity,p.position.get(),p.duration)
            if not matched:return
            self.power=True;self.identity=identity;self.groove=progress;self.arm=1.
            self.lift=0.;self.motion_lift=0.;self.transition=0.;self.clip=0.
            self.head_drag=None;self.continuous_target=None;self.needle_ready=True
            self.swap_disc=None;self.swap_started=None;self.cancel_audio()
            self.velocity=self.rpm*(1+self.pitch*.08)
            # Discard an old in-flight frame from before the view was hidden.
            if self.client and self.pending:
                self.client.close();self.client=None;self.pending=False
            self.frame=None;self.delete('scene');self.overlay_key=None
        def show(self):
            if not self.active:self.sync_playing_view()
            self.active=True;self.last=time.monotonic();self.requested_at=time.monotonic()
            if sys.platform=='darwin' and os.environ.get('CRATELOG_TURNTABLE_RENDERER')!='compat' and self.native is None and not self.native_failed:
                try:
                    from cratelog_turntable_native import NativeTurntable
                    self.native=NativeTurntable(self);self.overlay_key=None
                except (OSError,RuntimeError,AttributeError) as error:
                    self.native_failed=True
                    self.player.status.set('唱机使用兼容渲染：'+str(error))
            if not self.native and not self.client:self.client=RenderClient()
            if self.job is None:self.tick()
        def toggle_fullscreen(self):
            if self.fullscreen:self.exit_fullscreen();return
            root=self.winfo_toplevel()
            self.previous_fullscreen=bool(root.attributes('-fullscreen'))
            self.pack_forget()
            self.fullscreen_widgets=list(root.grid_slaves())
            for widget in self.fullscreen_widgets:widget.grid_remove()
            self.fullscreen=True
            self.place(x=0,y=0,relwidth=1,relheight=1)
            self.tk.call('raise',self._w)
            root.attributes('-fullscreen',True)
            self.overlay_key=None;self.paint_overlay()
        def exit_fullscreen(self,event=None):
            if self.fullscreen:
                self.fullscreen=False;self.place_forget()
                for widget in self.fullscreen_widgets:
                    if widget.winfo_exists():widget.grid()
                self.fullscreen_widgets=[]
                self.pack(in_=self.home_host,fill='both',expand=True)
                self.winfo_toplevel().attributes('-fullscreen',self.previous_fullscreen)
                self.overlay_key=None;self.paint_overlay()
                return 'break'
        def offer_folder(self,folder):
            from cratelog_library import load_album,read_json
            self.disc_generation+=1;generation=self.disc_generation;self.pending_disc=None
            if folder==self.player.folder:return
            self.player.status.set('正在准备待换唱片：'+folder.name)
            recursive=True if self.player.remote_catalog.lookup(folder,read_json(folder/'.cratelog.json',{})) else None
            def ready(album):
                if generation!=self.disc_generation or not self.winfo_exists():return
                if not album.get('tracks'):
                    self.player.status.set('此文件夹没有可播放曲目');return
                self.pending_disc=(folder,album);self.overlay_key=None
                self.player.status.set('点击唱机后方的唱片换盘：'+folder.name)
            self.player.submit(lambda:load_album(folder,recursive=recursive),ready)
        def accept_disc(self):
            if self.pending_disc is None or self.swap_disc is not None:return
            self.swap_disc=self.pending_disc;self.swap_started=None
            self.disc_generation+=1;self.pending_disc=None;self.overlay_key=None
            self.head_drag=None;self.lift=0.;self.player.stop()
        def update_exchange(self,now):
            if self.swap_disc is None:return -1.
            if self.swap_started is None:
                if self.arm!=0. or self.motion_lift!=0.:return 0.
                self.swap_started=now
            progress=min(1.,max(0.,(now-self.swap_started)/2.4))
            if progress>=1.:
                folder,album=self.swap_disc;self.swap_disc=None;self.swap_started=None;self.angle=0.
                self.player.load_folder(folder,autoplay=self.power,prepared=album)
                return -1.
            return progress
        def defer_audio(self):
            self.resume_generation+=1;self.resume_pending=True;self.needle_ready=False
        def cancel_audio(self):
            self.resume_generation+=1;self.resume_pending=False
        def hide(self):
            if self.active and self.player.album:self.mounted_context=(self.player.folder,self.player.album)
            self.exit_fullscreen()
            self.end_scratch()
            if self.gesture_job is not None:self.after_cancel(self.gesture_job);self.gesture_job=None
            if self.gestures:self.gestures.close();self.gestures=None
            self.active=False
            if self.native:self.native.geometry(False)
            if self.resume_pending:
                self.cancel_audio()
                if self.player.playback_state!='stopped':self.player.set_paused(False)
            if self.job:self.after_cancel(self.job);self.job=None
        def close(self):
            self.disc_generation+=1
            if self.escape_binding:
                self.winfo_toplevel().unbind('<Escape>',self.escape_binding);self.escape_binding=None
            self.hide()
            if self.native:self.native.close();self.native=None
            if self.client:self.client.close();self.client=None
        def state(self):
            swap_progress=self.update_exchange(time.monotonic())
            p=self.player;album=p.album or {};identity=''
            if p.folder and p.current_track_id:
                try:identity=p.current_track_id.relative_to(p.folder).as_posix()
                except ValueError:pass
            progress,matched=album_progress(album,identity,p.position.get(),p.duration)
            if not self.power and p.playback_state!='stopped':p.stop()
            running=self.power and matched and (p.playback_state=='playing' or self.resume_pending)
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
            if p.playback_state=='stopped':self.cancel_audio()
            travelling=max(0.,1.-(time.monotonic()-self.transition)/.8)
            self.speed_mix=1. if self.rpm==45. else 0.
            self.lamp+=(self.lamp_target-self.lamp)*min(1,dt*12.)
            if abs(target-self.arm)>0.0001:self.clip=0.
            self.arm,self.motion_lift=advance_arm(self.arm,self.motion_lift,target,dt)
            if target and self.motion_lift<1.:self.groove+=(progress-self.groove)*min(1,dt*8.)
            if self.scratch is not None:self.velocity=self.scratch["velocity"]
            else:self.velocity+=((self.rpm*(1+self.pitch*.08) if running else 0.)-self.velocity)*min(1,dt*5.)
            if self.scratch is None or not self.scratch["dragged"]:self.angle=(self.angle+dt*self.velocity*math.tau/60)%math.tau
            self.strobe=[(phase+dt*rate)%1 for phase,rate in zip(self.strobe,strobe_rates(self.velocity,self.rpm))]
            w=max(1,self.winfo_width());h=max(1,self.winfo_height());scale=min(1,1200/w,800/h)
            images=album.get('images',[])
            cover=str(p.folder/images[0]['filename']) if p.folder and images else ''
            self.needle_ready=target==1. and self.arm==1. and self.motion_lift==0. and self.lift==0. and travelling==0. and self.head_drag is None
            pending_cover='';pending_title='';pending_artist=''
            offered=self.swap_disc or self.pending_disc
            if offered:
                folder,album=offered;images=album.get('images',[])
                if images:pending_cover=str(folder/images[0]['filename'])
                metadata=album.get('metadata',{})
                pending_title=str(metadata.get('专辑名') or folder.name);pending_artist=str(metadata.get('音乐人') or '')
            exchange_center,exchange_angle,exchange_radius=exchange_pose(swap_progress)
            return dict(exchange_center=exchange_center,exchange_angle=exchange_angle,exchange_radius=exchange_radius,pending_title=pending_title,pending_artist=pending_artist,pending_record=bool(offered),swap_progress=swap_progress,pending_cover=pending_cover,eye=camera_eye(self.yaw,self.elevation,exchange_view_distance(self.distance,swap_progress)),width=max(2,int(w*scale)),height=max(2,int(h*scale)),rotation=self.angle,strobe=self.strobe,velocity=self.velocity,
                        room_light=self.room_light,power=self.power,speed_mix=self.speed_mix,progress=self.groove,arm=self.arm,lift=needle_lift(self.lift,self.motion_lift,travelling),clip=self.clip,keys=tuple(max(0.,(self.key_until-time.monotonic())/.12) if i==self.key_index else 0. for i in range(3)),lamp=self.lamp,pitch=self.pitch,cover=cover)
        def tick(self):
            self.job=None
            if not self.active:return
            now=time.monotonic()
            # Count only active polling time; OS sleep and UI suspension are not GPU stalls.
            if now-self.last_tick>2.:self.requested_at=now
            self.last_tick=now
            if not self.winfo_viewable():
                self.requested_at=now;self.last=now;self.job=self.after(200,self.tick);return
            try:
                if self.native:
                    state=self.state();self.paint_overlay()
                    displayed=self.native.render(state)
                    if displayed and self.resume_pending and self.needle_ready and self.power:
                        self.cancel_audio();self.player.set_paused(False)
                    self.job=self.after(33,self.tick);return
                if self.pending:
                    frame=completed_frame(self.client.results,self.requested_at,now)
                    if frame is not None:
                        w,h,data=frame
                        self.pending=False
                        if w==0:raise RuntimeError(data.decode('utf-8',errors='replace'))
                        image=Image.frombytes('RGB',(w,h),data).transpose(Image.Transpose.FLIP_TOP_BOTTOM)
                        if image.size!=(self.winfo_width(),self.winfo_height()):image=image.resize((max(1,self.winfo_width()),max(1,self.winfo_height())),Image.Resampling.BILINEAR)
                        self.frame=image;self.paint_overlay()
                        if now-self.render_recovered_at>60.:self.render_retries=0
                        if (self.resume_pending and self.render_landed and self.render_generation==self.resume_generation
                                and self.power and self.lift==0. and self.head_drag is None):
                            self.cancel_audio();self.player.set_paused(False)
                if not self.pending:
                    state=self.state();self.render_landed=self.needle_ready;self.render_generation=self.resume_generation
                    self.client.requests.put_nowait(state);self.pending=True;self.requested_at=time.monotonic()
            except TimeoutError:
                if self.render_retries>=2:
                    self.close();on_error('OpenGL 渲染连续超时，自动恢复失败。');return
                self.render_retries+=1;self.render_recovered_at=now
                self.client.close();self.client=RenderClient();self.pending=False
                self.requested_at=now;self.last=now
                self.job=self.after(100,self.tick);return
            except Exception as error:
                if self.native:
                    self.native.close();self.native=None;self.native_failed=True;self.overlay_key=None
                    self.client=RenderClient();self.pending=False;self.last=now
                    self.player.status.set('唱机已切换到兼容渲染：'+str(error))
                    self.job=self.after(100,self.tick);return
                self.close();on_error(str(error));return
            self.job=self.after(33,self.tick)
        def paint_overlay(self):
            if self.native:
                w,h=max(1,self.winfo_width()),max(1,self.winfo_height())
                key=(w,h,self.fullscreen,self.menu_open,self.menu_offset,self.pad_visible,self.room_light,self.rpm,self.pitch,
                     self.cue_index,self.head_drag is not None,self.player.current_track_id,id(self.player.album),
                     tuple((t.get('highlighted'),t.get('selected')) for t in (self.player.album or {}).get('tracks',[])) if self.menu_open else ())
                if key==self.overlay_key:return
                self.overlay_key=key;image=Image.new('RGBA',(w,h))
            else:
                if self.frame is None:return
                image=self.frame.convert('RGBA');w,h=image.size
            overlay=Image.new('RGBA',image.size);draw=ImageDraw.Draw(overlay)
            self.delete('hud');self.hits=[]
            texts=[(52,h-22,f'{self.rpm:.2f} RPM   {self.pitch*8:+.1f}%   ×{self.rpm/(100/3)*(1+self.pitch*.08):.3f}','#b7c3d1')]
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
                    import tkinter.font as tkfont
                    font=tkfont.Font(self,font=('TkDefaultFont',11))
                    text=track_menu_text(index+1,title,track,width-35,font.measure)
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
            draw.ellipse((54,17,62,25),outline=bulb,width=1)
            draw.line((56,25,56,29,60,29,60,25),fill=bulb,width=1)
            draw.line((57,31,59,31),fill=bulb,width=1)
            if self.room_light:
                for line in [(58,13,58,15),(50,16,52,18),(64,18,66,16),(49,22,51,22),(65,22,67,22)]:draw.line(line,fill=bulb,width=1)
            else:draw.line((51,30,65,16),fill=bulb,width=1)
            self.hits.append(((44,6,76,40),('lighting','toggle')))
            cx,cy=25,h-23
            for sx,sy in ((-1,-1),(1,-1),(-1,1),(1,1)):
                radius=3 if self.fullscreen else 8
                xx,yy=cx+sx*radius,cy+sy*radius
                direction=1 if self.fullscreen else -1
                draw.rectangle((min(xx,xx+sx*direction*5),yy,max(xx,xx+sx*direction*5)+1,yy+1),fill='#e9eef5')
                draw.rectangle((xx,min(yy,yy+sy*direction*5),xx+1,max(yy,yy+sy*direction*5)+1),fill='#e9eef5')
            self.hits.append(((8,h-42,42,h-5),('fullscreen','toggle')))

            if self.native:
                overlay.alpha_composite(ImageTk.getimage(self.menu_icon),(16,14))
                overlay=overlay.resize((w*2,h*2),Image.Resampling.LANCZOS)
                self.native.hud(overlay,texts);return
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
            self.end_scratch()
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
        def begin_scratch(self,point):
            p=self.player
            self.scratch=dict(angle=math.atan2(point[1]-SPINDLE[1],point[0]-SPINDLE[0]),
                started=time.monotonic(),last=time.monotonic(),sent=0.,dragged=False,
                position=p.position.get(),identity=p.current_track_id,resume=p.playback_state=='playing',
                initial=self.velocity,velocity=self.velocity,direction='forward',rate=None,paused=None,seeked=None,
                audio_velocity=self.velocity,audio_at=time.monotonic(),rate_at=0.)
            p.control('set_property','audio-pitch-correction',False)
            self.scratch_tick()
        def scratch_tick(self):
            self.scratch_job=None;s=self.scratch
            if s is None:return
            p=self.player;now=time.monotonic()
            if p.current_track_id!=s['identity'] or p.playback_state=='stopped':
                self.end_scratch(False);return
            if not s['dragged']:
                s['velocity']=s['initial']*max(0.,1.-(now-s['started'])/.16)
            elif now-s['last']>.16:s['velocity']=0.
            dt=max(0.,now-s['audio_at']);s['audio_at']=now
            s['audio_velocity']+=(s['velocity']-s['audio_velocity'])*(1.-math.exp(-dt/.025))
            if not s['dragged']:s['audio_velocity']=s['velocity']
            speed=abs(s['audio_velocity'])/(100/3)
            paused=speed<.03 or not self.needle_ready
            direction=s['direction'] if paused else ('backward' if s['audio_velocity']<0 else 'forward')
            if direction!=s['direction']:
                p.control('set_property','play-direction',direction);s['direction']=direction
            rate=round(max(.05,min(4.,speed)),2)
            if s['rate'] is None or (now-s['rate_at']>=.05 and abs(rate-s['rate'])>=.04):
                p.control('set_property','speed',rate);s['rate']=rate;s['rate_at']=now
            if paused!=s['paused']:
                p.control('set_property','pause',paused);s['paused']=paused
            # Keep the decoder running throughout the gesture. Repeated exact
            # seeks flush its audio buffer; reconcile position only on release.
            self.scratch_job=self.after(20,self.scratch_tick)
        def end_scratch(self,resume=True):
            s=self.scratch
            if s is None:return
            self.scratch=None
            if self.scratch_job is not None:self.after_cancel(self.scratch_job);self.scratch_job=None
            p=self.player
            p.control('set_property','play-direction','forward');self.pitch_control()
            if resume and p.current_track_id==s['identity'] and p.playback_state!='stopped':
                if s['dragged']:p.seek(s['position'])
                p.set_paused(not s['resume'])
        def scratch_drag(self,event):
            point=deck_point(event.x,event.y,self.winfo_width(),self.winfo_height(),camera_eye(self.yaw,self.elevation,self.distance),.453)
            if point is None or math.dist(point,SPINDLE)<.15:return
            s=self.scratch;now=time.monotonic()
            angle=math.atan2(point[1]-SPINDLE[1],point[0]-SPINDLE[0])
            delta=math.atan2(math.sin(angle-s['angle']),math.cos(angle-s['angle']))
            dt=max(.008,now-s['last']);s['angle']=angle;s['last']=now;s['dragged']=True
            s['velocity']=max(-133.,min(133.,delta/dt*60/math.tau))
            s['position']=max(0.,min(max(0.,self.player.duration-.02),s['position']+delta/math.tau*60/(100/3)))
            self.angle=(self.angle+delta)%math.tau
        def pitch_control(self):
            # Disable time-stretch compensation: playback rate now changes pitch too.
            engine=self.player.engine
            if getattr(self,'pitch_engine',None) is not engine:
                self.player.control('set_property','audio-pitch-correction',False);self.pitch_engine=engine
            self.player.control('set_property','speed',self.rpm/(100/3)*(1+self.pitch*.08))

        def click(self,event):
            for (x1,y1,x2,y2),(kind,value) in self.hits:
                if x1<=event.x<=x2 and y1<=event.y<=y2:
                    if kind=='fullscreen':self.toggle_fullscreen()
                    elif kind=='lighting':
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
            if self.swap_disc is not None:return 'break'
            if self.pending_disc and pending_disc_hit(event.x,event.y,self.winfo_width(),self.winfo_height(),camera_eye(self.yaw,self.elevation,self.distance)):
                self.accept_disc();return 'break'
            point=deck_point(event.x,event.y,self.winfo_width(),self.winfo_height(),camera_eye(self.yaw,self.elevation,self.distance))
            p=self.player
            if power_hit(event.x,event.y,self.winfo_width(),self.winfo_height(),camera_eye(self.yaw,self.elevation,self.distance)):
                self.toggle_power();return 'break'
            tip,_,_=tonearm_geometry(self.groove,self.arm)
            head=deck_point(event.x,event.y,self.winfo_width(),self.winfo_height(),camera_eye(self.yaw,self.elevation,self.distance),.55+self.lift*.27)
            tracks=(p.album or {}).get('tracks',[])
            if self.power and head and math.dist(head,tip)<.28 and tracks:
                self.cue_index=next((i for i,t in enumerate(tracks) if p.folder/t['filename']==p.current_track_id),0)
                self.head_drag=(event.x,self.cue_index);self.lift=1.;self.needle_ready=False;self.menu_open=True
                if p.playback_state=='playing':p.toggle_pause()
                self.show_cue();return 'break'
            record=deck_point(event.x,event.y,self.winfo_width(),self.winfo_height(),camera_eye(self.yaw,self.elevation,self.distance),.453)
            if self.power and record and .15<math.dist(record,SPINDLE)<1.50 and p.current_track_id and self.needle_ready:
                self.begin_scratch(record);return 'break'
            if point is None:
                self.orbit_drag=(event.x,event.y,self.yaw,self.elevation);return 'break'
            x,z=point
            if not self.power:
                self.orbit_drag=(event.x,event.y,self.yaw,self.elevation)
            elif abs(x+1.91)<.26 and abs(z-1.43)<.24:
                self.key_index=0;self.key_until=time.monotonic()+.12
                if self.resume_pending:self.cancel_audio();p.set_paused(True)
                else:p.toggle_pause()
            elif abs(x+1.295)<.26 and abs(z-1.61)<.10:
                self.key_index=1 if x<-1.295 else 2;self.key_until=time.monotonic()+.12
                self.rpm=100/3 if x<-1.295 else 45.;self.pitch_control()
            elif abs(x-1.35755)<.13 and abs(z+.012552)<.13 and self.arm==0. and self.motion_lift==0.:self.clip=1.-self.clip
            elif abs(x-.54)<.20 and abs(z-1.54)<.16:self.lamp_target=1.-self.lamp_target
            elif abs(x-1.93)<.22 and -.15<z<1.15:self.drag_pitch=True;self.drag(event)
            elif abs(x-1.93)<.2 and abs(z-1.29)<.12:
                self.pitch=0.;self.pitch_control()
            elif abs(x-1.70)<.2 and abs(z+0.677596)<.18:
                self.lift=1.-self.lift
                if self.lift:self.needle_ready=False
                if self.lift and p.playback_state=='playing':
                    p.set_paused(True);self.defer_audio()
                elif not self.lift and p.playback_state=='paused' and self.resume_pending:
                    self.motion_lift=1.;self.needle_ready=False
            else:self.orbit_drag=(event.x,event.y,self.yaw,self.elevation)
            return 'break'
        def drag(self,event):
            if self.scratch is not None:self.scratch_drag(event);return 'break'
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


def sleeve_image(path):
    from PIL import Image,ImageOps
    try:
        with Image.open(path) as source:return ImageOps.fit(ImageOps.exif_transpose(source).convert('RGBA'),(512,512))
    except (OSError,ValueError):
        background=Image.new('RGBA',(512,512),'#202428')
        logo_path=Path(__file__).resolve().parent/'web/assets/cratelog.png'
        try:
            with Image.open(logo_path) as source:logo=ImageOps.contain(source.convert('RGBA'),(384,384))
            background.alpha_composite(logo,((512-logo.width)//2,(512-logo.height)//2))
        except (OSError,ValueError):pass
        return background


def sleeve_spine_image(title,artist):
    from PIL import Image,ImageDraw,ImageFont
    image=Image.new('RGBA',(1024,64),'#d6d0bd');draw=ImageDraw.Draw(image)
    def font(bold):
        candidates=(('C:/Windows/Fonts/msyhbd.ttc' if bold else 'C:/Windows/Fonts/msyhl.ttc'),
                    ('DejaVuSans-Bold.ttf' if bold else 'DejaVuSans.ttf'),
                    '/System/Library/Fonts/STHeiti Light.ttc')
        for path in candidates:
            try:return ImageFont.truetype(path,22)
            except OSError:pass
        return ImageFont.load_default(size=22)
    for x,text,bold,width in ((16,title,True,580 if artist else 992),(620,artist,False,388)):
        face=font(bold)
        if draw.textlength(text,font=face)>width:
            while text and draw.textlength(text+'…',font=face)>width:text=text[:-1]
            text+='…'
        draw.text((x,32),text,font=face,fill='#242424',anchor='lm')
    return image


def panel_image():
    from PIL import Image,ImageDraw,ImageFont
    panel=Image.new('RGBA',(1359,1059));draw=ImageDraw.Draw(panel)
    try:font=ImageFont.truetype('DejaVuSans.ttf',20)
    except OSError:font=ImageFont.load_default(size=20)
    def label(x,z,text,size=font):draw.text(((x+2.265)*300,(z+1.765)*300),text,font=size,fill=(26,30,34,255))
    label(.75,1.42,'CRATELOG');label(.75,1.52,'DIRECT DRIVE');label(-2.10,1.40,'START / STOP')
    label(-1.50,1.51,'33');label(-1.23,1.51,'45');label(1.70,-.24,'PITCH');label(1.73,1.42,'RESET');label(1.64,-.06,'-8');label(1.64,1.02,'+8')
    for i in range(-4,5):
        z=.52+i*.135
        draw.line([(1190,(z+1.765)*300),(1205,(z+1.765)*300)],fill=(20,20,20,255),width=2)
    return panel


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
    panel=panel_image()
    panel_tex=texture(panel);cover_tex=texture(Image.new('RGBA',(256,256),'#bd692d'));last_cover=None
    pending_tex=texture(Image.new('RGBA',(256,256),'#bd692d'));last_pending=None
    spine_tex=texture(sleeve_spine_image('',''));last_spine=None
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
        if state.get('pending_cover','')!=last_pending:
            pending_tex.delete()
            pending_image=sleeve_image(state.get('pending_cover',''))
            pending_tex=texture(pending_image);last_pending=state.get('pending_cover','')
        spine=(state.get('pending_title',''),state.get('pending_artist',''))
        if spine!=last_spine:
            spine_tex.delete();spine_tex=texture(sleeve_spine_image(*spine));last_spine=spine
        gl.glViewport(0,0,w,h);program.use()
        program['pending_record']=float(state.get('pending_record',False))
        program['swap_progress']=float(state.get('swap_progress',-1.))
        center,angle,radius=exchange_pose(state.get('swap_progress',-1.))
        program['exchange_center']=center;program['exchange_angle']=angle;program['exchange_radius']=radius
        gl.glActiveTexture(gl.GL_TEXTURE3);gl.glBindTexture(pending_tex.target,pending_tex.id);program['pending_cover']=3
        gl.glActiveTexture(gl.GL_TEXTURE4);gl.glBindTexture(spine_tex.target,spine_tex.id);program['pending_spine']=4
        program['resolution']=(w,h)
        program['eye']=tuple(state.get('eye',(6.6,7.4,8.4)))
        for key in ('rotation','lamp','pitch'):program[key]=float(state[key])
        program['strobe_phase']=tuple(state.get('strobe',(0.,0.,0.,0.)))
        program['room_light']=float(state.get('room_light',True))
        program['power']=float(state.get('power',True))
        program['speed_mix']=float(state.get('speed_mix',0.))
        program['velocity']=float(state.get('velocity',0.))
        program['keys']=tuple(state.get('keys',(0.,0.,0.)))
        program['clip_closed']=float(state.get('clip',0.))
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
