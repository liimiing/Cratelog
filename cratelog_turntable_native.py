"""macOS direct GPU presentation for the Tk turntable; no framebuffer readback."""
import ctypes
import hashlib
import json
from pathlib import Path
from PIL import Image,ImageOps

ROOT=Path(__file__).resolve().parent

class NativeTurntable:
    def __init__(self,host):
        import _tkinter
        from cratelog_turntable import panel_image
        self.host=host;self.handle=None;self.cover=None;self.pending_cover=None;self.pending_spine=None
        binary=ROOT/'runtime/macos/libcratelog_turntable.dylib'
        self.lib=ctypes.CDLL(str(binary))
        self.lib.cratelog_turntable_hash.restype=ctypes.c_char_p
        if self.lib.cratelog_turntable_hash()!=hashlib.sha256((ROOT/'native/cratelog_turntable.m').read_bytes()).hexdigest().encode():
            raise RuntimeError('唱机原生组件版本不匹配，请执行 bash tools/build_macos.sh')
        declarations={
            'create':([ctypes.c_void_p,ctypes.c_char_p,ctypes.c_void_p,ctypes.c_size_t],ctypes.c_void_p),
            'geometry':([ctypes.c_void_p]+[ctypes.c_double]*4+[ctypes.c_int],None),
            'texture':([ctypes.c_void_p]+[ctypes.c_int]*3+[ctypes.c_void_p],None),
            'hud':([ctypes.c_void_p,ctypes.c_int,ctypes.c_int,ctypes.c_int,ctypes.c_void_p,ctypes.c_char_p],ctypes.c_int),
            'render':([ctypes.c_void_p,ctypes.c_char_p,ctypes.c_int,ctypes.c_int],ctypes.c_int),
            'error':([ctypes.c_void_p],ctypes.c_char_p),
            'destroy':([ctypes.c_void_p],None)}
        for name,(args,result) in declarations.items():
            method=getattr(self.lib,'cratelog_turntable_'+name);method.argtypes=args;method.restype=result
        self.tk_lib=ctypes.CDLL(_tkinter.__file__)
        get_view=self.tk_lib.TkMacOSXGetRootControl;get_view.argtypes=[ctypes.c_void_p];get_view.restype=ctypes.c_void_p
        self.window=host.winfo_toplevel();self.window.update_idletasks()
        error=ctypes.create_string_buffer(4096)
        self.handle=self.lib.cratelog_turntable_create(get_view(self.window.winfo_id()),(ROOT/'cratelog_turntable.frag').read_bytes(),error,len(error))
        if not self.handle:raise RuntimeError(error.value.decode('utf-8',errors='replace'))
        try:
            self.texture(1,panel_image());self.texture(2,Image.new('RGBA',(1,1)))
        except Exception:
            self.close();raise
    def geometry(self,visible=True):
        self.lib.cratelog_turntable_geometry(self.handle,self.host.winfo_rootx()-self.window.winfo_rootx(),self.host.winfo_rooty()-self.window.winfo_rooty(),self.host.winfo_width(),self.host.winfo_height(),visible)
    def texture(self,slot,image):
        image=image.convert('RGBA')
        if slot!=2:image=image.transpose(Image.Transpose.FLIP_TOP_BOTTOM)
        data=image.tobytes()
        self.lib.cratelog_turntable_texture(self.handle,slot,image.width,image.height,ctypes.c_char_p(data))
    def hud(self,image,texts,slot=2):
        image=image.convert('RGBA');data=image.tobytes()
        if not self.lib.cratelog_turntable_hud(self.handle,slot,image.width,image.height,ctypes.c_char_p(data),json.dumps(texts,ensure_ascii=False).encode()):
            raise RuntimeError('macOS 文字叠加层绘制失败')
    def render(self,state):
        from cratelog_turntable import tonearm_geometry,sleeve_image,exchange_pose
        self.geometry()
        if state['cover']!=self.cover:
            try:
                with Image.open(state['cover']) as source:cover=ImageOps.fit(ImageOps.exif_transpose(source).convert('RGBA'),(512,512))
            except (OSError,ValueError):cover=Image.new('RGBA',(512,512),'#bd692d')
            self.texture(0,cover);self.cover=state['cover']
        pending=state.get('pending_cover','')
        if pending!=self.pending_cover:
            cover=sleeve_image(pending)
            self.texture(3,cover);self.pending_cover=pending
        spine=(state.get('pending_title',''),state.get('pending_artist',''))
        if spine!=self.pending_spine:
            title,artist=spine
            texts=[(8,16,title,'#242424',True,290 if artist else 496)]
            if artist:texts.append((310,16,artist,'#242424',False,194))
            self.hud(Image.new('RGBA',(1024,64),'#d6d0bd'),texts,slot=4)
            self.pending_spine=spine
        values={name:state[name] for name in ('rotation','lamp','pitch','eye','velocity','speed_mix','power','room_light','keys')}
        center,angle,radius=exchange_pose(state.get('swap_progress',-1.))
        values.update(exchange_center=center,exchange_angle=angle,exchange_radius=radius,swap_progress=float(state.get('swap_progress',-1.)),pending_record=float(state.get('pending_record',False)),strobe_phase=state['strobe'],clip_closed=state['clip'],arm_direction=tonearm_geometry(state['progress'],state['arm'])[1],elevation=state['lift']*.12+(1.-state['arm'])*.04)
        # Preserve existing supersampling, but resolve entirely on the GPU.
        result=self.lib.cratelog_turntable_render(self.handle,json.dumps(values).encode(),state['width']*2,state['height']*2)
        if result<0:
            detail=self.lib.cratelog_turntable_error(self.handle).decode('utf-8',errors='replace')
            raise RuntimeError('原生唱机 GPU 绘制失败：'+detail)
        return result==1
    def close(self):
        if self.handle:self.lib.cratelog_turntable_destroy(self.handle);self.handle=None
