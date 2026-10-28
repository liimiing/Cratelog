"""Cocoa image gestures, polled by Tk without callbacks from native code."""
import ctypes
import hashlib
from pathlib import Path

class PictureGestures:
    def __init__(self,canvas,on_scale=None,on_scroll=None):
        import _tkinter
        self.on_scale=on_scale or canvas.scale;self.on_scroll=on_scroll
        self.canvas=canvas;self.job=None;self.handle=None;self.bindings=[]
        root=Path(__file__).resolve().parent
        binary=root/'runtime/macos/libcratelog_gestures.dylib'
        hint='请在项目目录执行 bash tools/build_macos.sh，再重启播放器以启用捏合缩放。'
        if not binary.is_file():raise RuntimeError(hint)
        self.lib=ctypes.CDLL(str(binary))
        self.lib.cratelog_gesture_hash.restype=ctypes.c_char_p
        if self.lib.cratelog_gesture_hash()!=hashlib.sha256((root/'native/cratelog_gestures.m').read_bytes()).hexdigest().encode():raise RuntimeError(hint)
        self.lib.cratelog_gestures_create.argtypes=[ctypes.c_void_p];self.lib.cratelog_gestures_create.restype=ctypes.c_void_p
        self.lib.cratelog_gestures_region.argtypes=[ctypes.c_void_p]+[ctypes.c_double]*4;self.lib.cratelog_gestures_region.restype=None
        self.lib.cratelog_gestures_pop.argtypes=[ctypes.c_void_p,ctypes.POINTER(ctypes.c_double)];self.lib.cratelog_gestures_pop.restype=ctypes.c_int
        self.lib.cratelog_gestures_destroy.argtypes=[ctypes.c_void_p];self.lib.cratelog_gestures_destroy.restype=None
        self.tk_lib=ctypes.CDLL(_tkinter.__file__)
        view=self.tk_lib.TkMacOSXGetRootControl;view.argtypes=[ctypes.c_void_p];view.restype=ctypes.c_void_p
        self.window=canvas.winfo_toplevel()
        parent=view(self.window.winfo_id())
        if not parent:raise RuntimeError('Tk 未取得看图窗口的 Cocoa 视图。请关闭看图窗口后重新打开。')
        self.handle=self.lib.cratelog_gestures_create(parent)
        if not self.handle:raise RuntimeError('手势组件已加载，但 Cocoa 窗口或事件监听器未就绪。请关闭看图窗口后重新打开；无需重复编译。')
        try:
            for widget in (canvas,self.window):
                self.bindings.append((widget,widget.bind('<Configure>',self.region,add='+')))
            self.region();self.poll()
        except Exception:
            self.close();raise
    def region(self,event=None):
        self.lib.cratelog_gestures_region(self.handle,self.canvas.winfo_rootx()-self.window.winfo_rootx(),self.canvas.winfo_rooty()-self.window.winfo_rooty(),self.canvas.winfo_width(),self.canvas.winfo_height())
    def poll(self):
        self.job=None
        out=(ctypes.c_double*5)()
        for _ in range(256):
            if not self.lib.cratelog_gestures_pop(self.handle,out):break
            if out[0]==1:self.on_scale(out[1],out[3],out[4])
            elif self.on_scroll:self.on_scroll(out[1],out[2],out[3],out[4])
            else:self.canvas.pan(out[1],out[2])
        self.job=self.canvas.after(16,self.poll)
    def close(self):
        if self.job is not None:self.canvas.after_cancel(self.job);self.job=None
        for widget,binding in self.bindings:
            if widget.winfo_exists():widget.unbind('<Configure>',binding)
        self.bindings=[]
        if self.handle:self.lib.cratelog_gestures_destroy(self.handle);self.handle=None
