"""In-process libmpv renderer attached to the existing Tk toplevel's NSView."""
import ctypes
import json
import hashlib
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def check_bridge(lib, binary, source):
    hint=f'请完整更新项目后执行 bash tools/build_macos.sh。加载位置：{binary}'
    try:
        version=lib.cratelog_bridge_version
        fingerprint=lib.cratelog_source_sha256
    except AttributeError as e:
        raise RuntimeError('检测到旧版原生频谱库（缺少版本标识）。'+hint) from e
    version.argtypes=[];version.restype=ctypes.c_int
    fingerprint.argtypes=[];fingerprint.restype=ctypes.c_char_p
    if version()!=2:
        raise RuntimeError('原生频谱库与 Python 接口版本不一致。'+hint)
    if fingerprint()!=hashlib.sha256(source.read_bytes()).hexdigest().encode():
        raise RuntimeError('原生频谱库不是由当前源码编译的。'+hint)


class NativeProcess:
    """Popen-shaped lifetime adapter; MPV's existing IPC clients remain unchanged."""
    def __init__(self, host, options):
        import _tkinter
        self.host = host
        self.handle = None
        self.bindings = []
        self.geometry = None
        self.parent_size = None
        self.trace_job = None
        self.last_trace = None
        binary = ROOT/'runtime'/'macos'/'libcratelog.dylib'
        if not binary.is_file():
            raise RuntimeError('缺少 Mac 原生频谱组件，请运行 bash install_macos.sh')
        try:
            self.lib = ctypes.CDLL(str(binary))
        except OSError as e:
            raise RuntimeError('Mac 原生频谱库加载失败，请在本机执行 bash tools/build_macos.sh 重新编译：'+str(e)) from e
        check_bridge(self.lib,binary,ROOT/'native'/'cratelog_macos.m')
        self.lib.cratelog_create.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_void_p, ctypes.c_size_t]
        self.lib.cratelog_create.restype = ctypes.c_void_p
        self.lib.cratelog_geometry.argtypes = [ctypes.c_void_p]+[ctypes.c_double]*4+[ctypes.c_int]
        self.lib.cratelog_geometry.restype = None
        self.lib.cratelog_destroy.argtypes = [ctypes.c_void_p]
        self.lib.cratelog_destroy.restype = None
        self.lib.cratelog_frames.argtypes = [ctypes.c_void_p]
        self.lib.cratelog_frames.restype = ctypes.c_uint64
        # Resolve Tk's exported platform API; winfo_id itself is NOT an NSView*.
        self.tk_library = ctypes.CDLL(_tkinter.__file__)
        try:
            get_view = self.tk_library.TkMacOSXGetRootControl
        except AttributeError as e:
            raise RuntimeError('当前 Tk 未提供 Cocoa 接口，请使用 install_macos.sh 安装的 Homebrew Tk 环境。') from e
        get_view.argtypes = [ctypes.c_void_p]
        get_view.restype = ctypes.c_void_p
        root = host.winfo_toplevel()
        root.update_idletasks()
        parent = get_view(root.winfo_id())
        error = ctypes.create_string_buffer(1024)
        self.handle = self.lib.cratelog_create(parent, json.dumps(options).encode(), error, len(error))
        if not self.handle:
            raise RuntimeError(error.value.decode('utf-8', errors='replace'))
        try:
            for widget, event in ((root,'<Configure>'),(host,'<Map>'),(host,'<Unmap>')):
                self.bindings.append((widget,event,widget.bind(event,self.reposition,add='+')))
            self.reposition()
            if os.environ.get('CRATELOG_GEOMETRY_TRACE')=='1':
                self.lib.cratelog_geometry_snapshot.argtypes=[ctypes.c_void_p,ctypes.POINTER(ctypes.c_double)]
                self.lib.cratelog_geometry_snapshot.restype=None
                self.trace_geometry()
        except Exception:
            self.terminate()
            raise

    def reposition(self, event=None):
        if not self.handle:return
        root = self.host.winfo_toplevel()
        rect = (self.host.winfo_rootx()-root.winfo_rootx(),
                self.host.winfo_rooty()-root.winfo_rooty(),
                self.host.winfo_width(),self.host.winfo_height(),int(self.host.winfo_viewable()))
        parent_size=(root.winfo_width(),root.winfo_height())
        if rect != self.geometry or parent_size != self.parent_size:
            self.lib.cratelog_geometry(self.handle,*rect)
            self.geometry = rect
            self.parent_size = parent_size

    def poll(self):return None if self.handle else 0
    def trace_geometry(self):
        if not self.handle:return
        root=self.host.winfo_toplevel()
        values=(ctypes.c_double*11)()
        self.lib.cratelog_geometry_snapshot(self.handle,values)
        record={'tk_root':[root.winfo_width(),root.winfo_height()],
                'tk_cached_rect':self.geometry,
                'cocoa':dict(zip(('flipped','parent_x','parent_y','parent_w','parent_h',
                                 'view_x','view_y','view_w','view_h','backing_w','backing_h'),values))}
        line=json.dumps(record)
        if line!=self.last_trace:
            print('CRATELOG_GEOMETRY '+line,flush=True);self.last_trace=line
        self.trace_job=self.host.after(250,self.trace_geometry)
    def render_stats(self):
        values=(ctypes.c_uint64*3)()
        method=self.lib.cratelog_render_stats
        method.argtypes=[ctypes.c_void_p,ctypes.POINTER(ctypes.c_uint64)];method.restype=None
        method(self.handle,values)
        return dict(zip(('frames','wakeups','skipped'),values))
    def frame_count(self):return self.lib.cratelog_frames(self.handle) if self.handle else 0
    def terminate(self):
        if self.trace_job:
            self.host.after_cancel(self.trace_job);self.trace_job=None
        for widget,event,binding in self.bindings:
            widget.unbind(event,binding)
        self.bindings.clear()
        if self.handle:
            self.lib.cratelog_destroy(self.handle)
            self.handle = None
    def wait(self,timeout=None):return 0
    kill = terminate
