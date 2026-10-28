"""Cratelog desktop player. Network/decoder work never calls Tk from workers."""
import json
import os
import queue
import re
import shutil
import subprocess
import threading
import time
import uuid
import webbrowser
import sys
import socket
import tempfile
from urllib.parse import urlencode, urlsplit, urlunsplit
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from cratelog_platform import load_tk
tk=load_tk()
from tkinter import ttk, filedialog, messagebox, colorchooser
from tkinter import font as tkfont
from PIL import Image, ImageTk

from cratelog_library import Remote, Conflict, CatalogIndex, load_album, save_album, read_json, atomic_json, payload, digest
from cratelog_widgets import SpectrumTimeline, VolumeMeter, SpectrumAxis, SPECTRUM_FILTER, SPECTRUM_HEIGHT, transport_icon, Tooltip, HalfStarPicker
from cratelog_lastfm import LastfmAPI,LastfmService,Listening,stored_config
from cratelog_platform import state_dir,executable,ui_font,SocketStream
from cratelog_i18n import tr,language

BASE = Path(__file__).resolve().parent
BRAND_DIR=Path(__file__).resolve().parent/'web'
BRAND=json.loads((BRAND_DIR/'cratelog-brand.json').read_text(encoding='utf-8'))
UI_FONT=ui_font()


_BaseTooltip=Tooltip
def Tooltip(widget,text):
    return _BaseTooltip(widget,lambda:tr(text() if callable(text) else text))


def subtitle_style(raw):
    """Saved subtitle appearance. Invalid values fall back to mpv's defaults."""
    raw = raw if isinstance(raw, dict) else {}
    font = str(raw.get('font') or '').replace('\n', ' ').strip()[:200]
    try:
        size = int(float(raw.get('size', 55)))
    except (TypeError, ValueError):
        size = 55
    color = str(raw.get('color') or '').strip().upper()
    if re.fullmatch(r'[0-9A-F]{6}', color): color = '#' + color
    if not re.fullmatch(r'#[0-9A-F]{6}', color): color = '#FFFFFF'
    return {'font': font, 'size': min(300, max(8, size)), 'color': color}


def parse_subtitle_form(font, size, color):
    font = str(font or '').replace('\n', ' ').strip()
    if len(font) > 200: raise ValueError('字幕字体名称过长。')
    text = str(size).strip()
    try: value = float(text)
    except ValueError: value = None
    if value is None or value != int(value) or not 8 <= int(value) <= 300:
        raise ValueError('字高须为 8 到 300 的整数。')
    color = str(color or '').strip().upper()
    if re.fullmatch(r'[0-9A-F]{6}', color): color = '#' + color
    if not re.fullmatch(r'#[0-9A-F]{6}', color):
        raise ValueError('字幕颜色须为 #RRGGBB。')
    return {'font': font, 'size': int(value), 'color': color}


def subtitle_argv(raw):
    style = subtitle_style(raw)
    # exact sidecars are added after the file loads. Fuzzy names stay in the spectrum menu.
    return ['--sub-auto=no', '--sid=no',
            '--sub-font=' + (style['font'] or 'sans-serif'),
            '--sub-font-size=' + str(style['size']),
            '--sub-color=' + style['color']]


SUBTITLE_EXTENSIONS = ('.srt', '.ass', '.ssa', '.vtt', '.sub', '.lrc')


def subtitle_candidates(audio):
    """Exact stem matches first, then stem.lang sidecars such as track.en.srt."""
    audio = Path(audio) if audio else None
    if audio is None: return []
    stem, folder = audio.stem, audio.parent
    exact, variants = [], []
    try: entries = list(folder.iterdir())
    except OSError: return []
    prefix = (stem + '.').casefold()
    for path in entries:
        if not path.is_file() or path.suffix.lower() not in SUBTITLE_EXTENSIONS: continue
        if path.stem.casefold() == stem.casefold(): exact.append(path)
        elif path.name.casefold().startswith(prefix): variants.append(path)
    rank = {ext: index for index, ext in enumerate(SUBTITLE_EXTENSIONS)}
    exact.sort(key=lambda path: (rank.get(path.suffix.lower(), len(rank)), path.name.casefold()))
    variants.sort(key=lambda path: path.name.casefold())
    return exact + variants


def preferred_subtitle(audio):
    audio = Path(audio) if audio else None
    if audio is None: return None
    for path in subtitle_candidates(audio):
        if path.stem.casefold() == audio.stem.casefold(): return path
    return None


def _subtitle_key(path):
    try: return str(Path(path).resolve()).casefold()
    except OSError: return str(path).casefold()


def mpv_control_error(event):
    error=event.get('error')
    if error in (None,'success'):return None
    command=event.get('_command',[])
    # Audio formats and file transitions do not always expose these properties.
    if command and command[0] in ('get_property','observe_property') and error in ('property unavailable','property not found'):
        return None
    context=' '.join(str(v) for v in command[:2])
    return '播放控制失败：'+str(error)+('（{0}）'.format(context) if context else '')


class MPV:
    def __init__(self, executable, events, spectrum_window=None, subtitle=None):
        self.events = events
        self.stream = None
        self.command_stream = None
        self.closed = False
        self.event_id = uuid.uuid4().hex
        self.request_id = 0
        self.commands = queue.Queue()
        self.pipe = r'\\.\pipe\cratelog-' + uuid.uuid4().hex
        self.socket_dir=None;self.sockets=[]
        if os.name!='nt':
            self.socket_dir=tempfile.mkdtemp(prefix='cl-',dir='/tmp')
            self.pipe=self.socket_dir+'/mpv.sock'
        options = [executable, '--idle=yes', '--no-config', '--no-terminal',
                   # Local/removable media need explicit caching: auto mainly
                   # targets network streams. Bound memory, and prebuffer before
                   # starting rather than feeding an underfilled audio device.
                   '--cache=yes', '--cache-secs=15', '--demuxer-readahead-secs=15',
                   '--demuxer-max-bytes=32MiB', '--demuxer-max-back-bytes=8MiB',
                   '--cache-pause=yes', '--cache-pause-initial=yes', '--cache-pause-wait=1',
                   ('--audio-buffer=0.1' if sys.platform=='darwin' else '--audio-buffer=0.5'), '--gapless-audio=no',
                   '--input-default-bindings=no', '--input-vo-keyboard=no',
                   '--osc=no', '--osd-level=0', '--input-ipc-server=' + self.pipe]
        if spectrum_window and sys.platform!='darwin':
            options += ['--wid=' + str(spectrum_window), '--force-window=yes',
                        '--keepaspect=no', '--vo=gpu', '--window-dragging=no',
                        '--script=' + str(BASE / 'cratelog_spectrum.lua'),
                        '--lavfi-complex=' + SPECTRUM_FILTER]
        else:
            options += ['--no-video']
        options += subtitle_argv(subtitle)
        try:
            if sys.platform=='darwin' and spectrum_window:
                from cratelog_macos import NativeProcess
                native_options = dict(arg[2:].split('=',1) if '=' in arg else (arg[2:],'yes') for arg in options[1:])
                native_options.pop('no-video',None)
                native_options.pop('no-config',None)
                native_options.pop('no-terminal',None)
                native_options.update({'config':'no','terminal':'no','vo':'libmpv',
                    'keepaspect':'no','force-window':'yes','video-timing-offset':'0',
                    # Use the actual list option, not CLI aliases/list actions.
                    'scripts':[str(BASE/'cratelog_spectrum.lua')],'lavfi-complex':SPECTRUM_FILTER})
                self.process = NativeProcess(spectrum_window,native_options)
            else:
                self.process = subprocess.Popen(options,
                    creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:
            if self.socket_dir:shutil.rmtree(self.socket_dir,ignore_errors=True)
            raise
        threading.Thread(target=self.connect, daemon=True).start()

    def connect(self):
        try:
            self.stream = self.open_pipe()
            if self.stream is None: return
            # Register subscriptions on the event connection before blocking reads.
            for i, prop in enumerate(['time-pos', 'duration', 'pause', 'audio-params', 'idle-active', 'metadata','audio-bitrate','seeking','paused-for-cache','track-list','sid']):
                request = {'command': ['observe_property', i, prop], 'request_id': -i-1}
                self.stream.write((json.dumps(request) + '\n').encode())
                while not self.closed:
                    line = self.stream.readline()
                    if not line: raise RuntimeError('mpv 事件连接已关闭')
                    event = json.loads(line)
                    if event.get('request_id') == -i-1:event['_command']=request['command']
                    self.emit(event)
                    if event.get('request_id') == -i-1: break
            threading.Thread(target=self.writer, daemon=True).start()
            while not self.closed:
                line = self.stream.readline()
                if not line: break
                self.emit(json.loads(line))
        except Exception as e:
            if not self.closed: self.events.put(('error', str(e)))

    def open_pipe(self):
        for _ in range(100):
            if self.closed: return None
            try:
                if os.name=='nt':return open(self.pipe,'r+b',buffering=0)
                client=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM)
                try:client.connect(self.pipe)
                except OSError:client.close();raise
                self.sockets.append(client)
                return SocketStream(client)
            except OSError:
                if self.process.poll() is not None: raise RuntimeError('mpv 启动失败')
                time.sleep(.05)
        raise RuntimeError('mpv IPC 连接超时')

    def emit(self, event):
        event['_engine'] = self.event_id
        self.events.put(('mpv', event))

    def writer(self):
        try:
            # Windows synchronous named-pipe reads serialize writes on the same
            # handle. A second IPC client keeps commands working while paused/idle.
            self.command_stream = self.open_pipe()
            if self.command_stream is None: return
            while not self.closed:
                command = self.commands.get()
                if command is None: break
                self.request_id += 1
                self.command_stream.write((json.dumps({'command': command, 'request_id': self.request_id}) + '\n').encode())
                while not self.closed:
                    line = self.command_stream.readline()
                    if not line: raise RuntimeError('mpv 控制连接已关闭')
                    reply = json.loads(line)
                    # Lifecycle events also arrive on this client; the event
                    # client owns them so end-of-file is never handled twice.
                    if reply.get('request_id') == self.request_id:
                        reply['_command']=command
                        if command[0] == 'get_property' and reply.get('error') == 'success':
                            self.emit({'event': 'property-change', 'name': command[1], 'data': reply.get('data')})
                        self.emit(reply)
                        break
        except Exception as e:
            if not self.closed: self.events.put(('error', str(e)))

    def command(self, *args):
        self.commands.put(list(args))


    def close(self):
        self.closed = True
        self.commands.put(None)
        if self.process.poll() is None:
            self.process.terminate()
            try: self.process.wait(timeout=3)
            except subprocess.TimeoutExpired: self.process.kill()
        if self.stream:
            self.stream.close()
        if self.command_stream:
            self.command_stream.close()
        for client in self.sockets:client.close()
        if self.socket_dir:shutil.rmtree(self.socket_dir,ignore_errors=True)


class Player:
    def __init__(self, root):
        self.root = root
        self.settings_path = state_dir() / 'cratelog_settings.json'
        self.settings = read_json(self.settings_path,{})
        legacy=read_json(self.settings_path.parent/'config.json',{})
        language.set_language(self.settings.get('language',legacy.get('language','auto')))
        self.root.title(tr('Cratelog · 音乐资料库与播放器'))
        self.brand_icon=ImageTk.PhotoImage(Image.open(BRAND_DIR/'assets'/'cratelog.png').resize((64,64),Image.Resampling.LANCZOS))
        self.root.iconphoto(True,self.brand_icon)
        if os.name=='nt':self.root.iconbitmap(str(BRAND_DIR/'assets'/'cratelog.ico'))
        self.root.geometry('1280x820')
        self.root.minsize(1100, 620)
        self.root.configure(bg='#151719')
        self.root.option_add('*Font', (UI_FONT, 10))
        self.events = queue.Queue()
        self.pool = ThreadPoolExecutor(max_workers=3)
        self.load_generation = 0
        self.sync_cancel = threading.Event()
        self.folder = None
        self.album = None
        self.remote_catalog = CatalogIndex()
        self.catalog_generation = 0
        self.confirmed_remote = set()
        self.engine = None
        self.subtitle_ids = {}
        self.subtitle_sid = None
        self.active_subtitle = None
        self.subtitle_menu = None
        self.playlist = []
        self.play_index = -1
        self.current_file = None
        self.current_track_id=None
        self.playlist_sources={}
        self.track_start=0
        self.track_end=None
        self.cue_title=''
        self.paused = False
        self.playback_state = 'stopped'
        self.seek_pending = None
        self.duration = 0
        self.seeking = False
        self.busy = False
        self.organizer = None
        self.cover_preview = None
        self.settings_window = None
        self.review_window = None
        self.pending_restore = None
        self.normal_geometry = self.settings.get('layout', {}).get('geometry', '1280x820')
        def remember_geometry(event):
            if event.widget is root and root.state()=='normal':self.normal_geometry=root.geometry()
        root.bind('<Configure>',remember_geometry,add='+')
        self.url = tk.StringVar(value=self.settings.get('url', ''))
        self.token = tk.StringVar(value=self.settings.get('token', os.getenv('CRATELOG_API_TOKEN', '')))
        self.mpv = tk.StringVar(value=self.settings.get('mpv', ''))
        self.status = tk.StringVar(value=tr('选择音乐根目录开始浏览'))
        try:self.lastfm_config=stored_config(self.settings.get('lastfm',{}),decode=True)
        except OSError:self.lastfm_config={};self.status.set(tr('Last.fm 凭据不可用，请重新授权'))
        self.lastfm=LastfmService(self.settings_path.parent/'cratelog_lastfm_queue.sqlite',lambda text:self.events.put(('status',text)))
        self.lastfm.configure(self.lastfm_config)
        self.lastfm_listening=None;self.lastfm_tags={};self.lastfm_loaded=False;self.lastfm_flush_at=0
        self.now = tk.StringVar(value=tr('CRATELOG  /  尚未播放'))
        self.details = tk.StringVar(value=tr('本地播放 · Discogs 整理 · 资料同步'))
        self.tag_details = ''
        self.audio_details = ''
        self.rating = tk.StringVar(value='0')
        self.position = tk.DoubleVar()
        self.volume = tk.DoubleVar(value=max(0,min(100,float(self.settings.get('volume',70)))))
        saved_mode=self.settings.get('mode','顺序播放')
        self.mode = tk.StringVar(value=saved_mode if saved_mode in ('顺序播放','列表循环','单曲循环') else '顺序播放')
        self.pause_text = tk.StringVar(value='暂停')
        style = ttk.Style(root)
        style.theme_use('clam')
        style.configure('.', background='#202428', foreground='#e7e7e7', fieldbackground='#202428', font=(UI_FONT, 10), bordercolor='#343a40', lightcolor='#343a40', darkcolor='#343a40')
        style.configure('TButton', padding=(10, 7), borderwidth=0, background='#30363c')
        style.configure('Transport.TButton', padding=(10,7), borderwidth=0, background='#30363c')
        style.map('TButton', background=[('active','#4b3b2d')])
        # Explicit player styles survive the organizer's global TButton changes.
        # ttk/clam also honors these colors on Aqua, unlike native tk.Button.
        for name in ('Cratelog.TButton','Transport.TButton'):
            style.configure(name,background='#30363c',foreground='#e7e7e7',
                            padding=(10,7),borderwidth=0,relief='flat',
                            bordercolor='#343a40',lightcolor='#343a40',darkcolor='#343a40',
                            focuscolor='#e9b965')
            style.map(name,background=[('disabled','#292f34'),('pressed','#704a2c'),('active','#4b3b2d'),('!disabled','#30363c')],
                      foreground=[('disabled','#838b92'),('!disabled','#e7e7e7')])
        style.map('TCombobox', fieldbackground=[('readonly','#30363c')], foreground=[('readonly','#e7e7e7')], selectbackground=[('readonly','#30363c')], selectforeground=[('readonly','#e7e7e7')])
        style.configure('Treeview.Heading', background='#292f34', padding=7, borderwidth=0, font=(UI_FONT, 10))
        style.map('Treeview.Heading',background=[('active','#292f34'),('pressed','#292f34')],foreground=[('active','#e7e7e7'),('pressed','#e7e7e7')])
        style.configure('Horizontal.TScale', background='#202428', troughcolor='#353b40')
        style.configure('Treeview', rowheight=29, background='#202428', fieldbackground='#202428', foreground='#e7e7e7', font=(UI_FONT, 10))
        style.map('Treeview', background=[('selected', '#704a2c')])
        root.columnconfigure(0,weight=1)
        for row in range(5):root.rowconfigure(row,weight=1 if row==2 else 0)
        top = ttk.Frame(root, padding=14,height=SPECTRUM_HEIGHT+28)
        top.grid(row=1,column=0,sticky='ew');top.pack_propagate(False)
        self.top_pane=ttk.Panedwindow(top,orient='horizontal',height=SPECTRUM_HEIGHT)
        self.top_pane.pack(fill='x')
        summary = ttk.Frame(self.top_pane, width=330)
        summary.pack_propagate(False)
        ttk.Label(summary, textvariable=self.now, wraplength=310, font=(UI_FONT, 15, 'bold')).pack(anchor='w')
        ttk.Label(summary, textvariable=self.details, wraplength=310).pack(anchor='w', pady=5)
        summary.bind('<Configure>',lambda e:[child.configure(wraplength=max(60,e.width-12)) for child in summary.winfo_children()])
        spectrum = ttk.Frame(self.top_pane, height=SPECTRUM_HEIGHT, width=774)
        self.spectrum_panel = spectrum
        self.top_pane.add(summary,weight=1);self.top_pane.add(spectrum,weight=3)
        spectrum.pack_propagate(False)
        plot = ttk.Frame(spectrum); plot.pack(fill='both', expand=True)
        SpectrumAxis(plot, vertical=True).pack(side='left', fill='y')
        self.spectrum_host = SpectrumTimeline(plot, command=self.seek)
        self.seekbar = self.spectrum_host
        self.spectrum_host.pack(fill='both', expand=True)
        self.spectrum_host.pack_propagate(False)
        self.spectrum_host.bind('<Button-3>', self.open_subtitle_menu)
        if sys.platform=='darwin':
            self.spectrum_host.bind('<Button-2>', self.open_subtitle_menu)
            self.spectrum_host.bind('<Control-Button-1>', self.open_subtitle_menu)
        SpectrumAxis(spectrum).pack(fill='x', padx=(34,0))
        bar = ttk.Frame(root, padding=8); bar.grid(row=0,column=0,sticky='ew')
        self.toolbar = bar
        toolbar_buttons=[]
        for label, command in [('音乐根目录', self.choose_root), ('刷新目录', self.refresh_root), ('Discogs 文件整理', self.open_organizer), ('同步当前专辑', self.sync_current), ('批量同步根目录', self.sync_all), ('取消同步', self.sync_cancel.set), ('远端版本处理', self.resolve), ('设置', self.configure), ('关于',self.show_about)]:
            toolbar_buttons.append(ttk.Button(bar,style='Cratelog.TButton', text=tr(label), command=command))
        toolbar_width=[None]
        def wrap_toolbar(event):
            if event.width==toolbar_width[0]:return
            toolbar_width[0]=event.width
            row=used=0
            height=max(button.winfo_reqheight() for button in toolbar_buttons)+4
            for button in toolbar_buttons:
                width=button.winfo_reqwidth()+6
                if used and used+width>event.width-16:row+=1;used=0
                button.place(x=8+used,y=8+row*height,width=width-6,height=height-4)
                used+=width
            bar.configure(height=16+(row+1)*height)
        bar.bind('<Configure>',wrap_toolbar)
        pane = ttk.Panedwindow(root, orient='horizontal'); pane.grid(row=2,column=0,sticky='nsew',padx=12)
        self.library_pane = pane
        left = ttk.Frame(pane); right = ttk.Frame(pane); pane.add(left, weight=1); pane.add(right, weight=4)
        self.tree = ttk.Treeview(left, show='tree', selectmode='browse')
        self.tree.tag_configure('remote',foreground='#e9a65d')
        self.tree.pack(side='left', fill='both', expand=True)
        scroll = ttk.Scrollbar(left, command=self.tree.yview); scroll.pack(side='right', fill='y'); self.tree.configure(yscrollcommand=scroll.set)
        self.tree.bind('<<TreeviewOpen>>', self.expand)
        self.tree.bind('<<TreeviewSelect>>', self.choose_folder)
        info = ttk.Frame(right, padding=12); info.pack(fill='x')
        self.cover = ttk.Label(info); self.cover.pack(side='left', padx=(0,16))
        self.cover.bind('<Double-Button-1>', self.show_cover)
        self.title = ttk.Label(info, text=tr('选择左侧专辑目录'), font=(UI_FONT, 15), wraplength=650); self.title.pack(anchor='w')
        self.album_subtitle = tk.Label(info,text='',bg='#202428',fg='#89939b',font=(UI_FONT,10),anchor='w',wraplength=650,justify='left')
        self.album_subtitle.pack(anchor='w',pady=(5,0))
        ratebar = ttk.Frame(info); ratebar.pack(anchor='w', pady=12)
        self.review_summary = tk.Label(ratebar,text=tr('未评价'),bg='#202428',fg='#c5a575',font=(UI_FONT,10))
        self.review_summary.pack(side='left',padx=(0,12))
        ttk.Button(ratebar,style='Cratelog.TButton',text=tr('评价'),command=self.show_review).pack(side='left',padx=(0,8))
        self.album_menu_icon=transport_icon('menu',width=20)
        self.album_menu_button=ttk.Button(ratebar,style='Cratelog.TButton',image=self.album_menu_icon,command=self.show_album_menu)
        self.album_menu_button.pack(side='left',padx=4)
        Tooltip(self.album_menu_button,'专辑整理菜单')
        self.copy_album_icon=transport_icon('copy',width=20)
        self.copy_album_button=ttk.Button(ratebar,style='Cratelog.TButton',image=self.copy_album_icon,command=self.copy_album_info)
        self.copy_album_button.pack(side='left',padx=4)
        Tooltip(self.copy_album_button,'复制艺术家 - 专辑名（发行年份）')
        self.douban_icon=transport_icon('search',width=20)
        self.douban_button=ttk.Button(ratebar,style='Cratelog.TButton',image=self.douban_icon,command=self.search_douban)
        self.douban_button.pack(side='left',padx=4)
        Tooltip(self.douban_button,'在豆瓣音乐搜索当前专辑')
        self.remote_icon=transport_icon('remote',width=20)
        self.remote_button=ttk.Button(ratebar,image=self.remote_icon,style='Cratelog.TButton',command=self.open_remote_album,state='disabled')
        self.remote_button.pack(side='left',padx=4)
        Tooltip(self.remote_button,'打开服务端专辑详情')
        self.mark_icons = {name: transport_icon(name, width=20) for name in ('selected','highlighted')}
        for name,hint in [('highlighted','切换重点'),('selected','切换入选')]:
            button=ttk.Button(ratebar,style='Cratelog.TButton',image=self.mark_icons[name],command=lambda key=name:self.mark(key))
            button.pack(side='left',padx=4);Tooltip(button,hint)
        self.track_area=ttk.Frame(right);self.track_area.pack(fill='both',expand=True)
        table = ttk.Frame(self.track_area); table.pack(fill='both', expand=True)
        self.track_table=table;self.turntable=None;self.turntable_visible=False
        self.fixed_track_widths={'number':45,'duration':76,'selected':70,'highlighted':70}
        self.tracks = ttk.Treeview(table, columns=('number','file','duration','highlighted','selected'), show='headings', selectmode='extended')
        for key, title, width in [('number','#',45),('file','本地音频文件名',480),('duration','时长',76),('highlighted','重点',70),('selected','入选',70)]:
            self.tracks.heading(key,text=tr(title)); self.tracks.column(key,width=width,stretch=key=='file')
            if key in self.fixed_track_widths:self.tracks.column(key,minwidth=width,anchor='center')
        self.tracks.bind('<Button-1>',self.prevent_fixed_column_resize,add='+')
        self.tracks.tag_configure('highlighted', foreground='#ffc077')
        self.tracks.tag_configure('selected', foreground='#91d6bc')
        self.tracks.tag_configure('playing', background='#333d43')
        self.tracks.pack(side='left', fill='both', expand=True)
        scroll = ttk.Scrollbar(table,command=self.tracks.yview); scroll.pack(side='right',fill='y'); self.tracks.configure(yscrollcommand=scroll.set)
        self.show_id3_titles=bool(self.settings.get('show_id3_titles',False))
        self.tracks.heading('file',text=tr('ID3曲名') if self.show_id3_titles else tr('本地音频文件名'))
        self.tracks.bind('<Double-1>',self.track_double_click)
        self.tracks.bind('<Motion>',self.track_heading_hover,add='+')
        self.tracks.bind('<Leave>',lambda event:self.tracks.configure(cursor=''),add='+')
        self.root.bind('<space>', self.space_next)
        self.tracks.bind('<Button-3>',self.track_menu)
        if sys.platform=='darwin':
            self.tracks.bind('<Button-2>',self.track_menu)
            self.tracks.bind('<Control-Button-1>',self.track_menu)
        bottom = ttk.Frame(root,padding=12); bottom.grid(row=3,column=0,sticky='ew')
        self.clock=ttk.Label(bottom,text='00:00 / 00:00')  # Actual clock is rendered inside mpv's spectrum.
        self.transport_icons = {name: transport_icon(name) for name in ('previous','play','pause','stop','next','sequential','repeat','repeat_one')}
        self.transport_buttons = {}
        for icon, hint, command in [('previous','上一曲',lambda:self.next(-1)),('play',lambda:'暂停' if self.current_file and not self.paused else '播放 / 继续',self.toggle_pause),('stop','停止',self.stop),('next','下一曲',lambda:self.next(1))]:
            button = ttk.Button(bottom,image=self.transport_icons[icon],width=0,style='Transport.TButton',command=command)
            self.transport_buttons[icon] = button
            Tooltip(button,hint)
            button.pack(side='left',padx=3)
        self.pause_text.trace_add('write', lambda *args: self.update_play_button())
        self.mode_button=ttk.Button(bottom,image=self.transport_icons['sequential'],style='Transport.TButton',command=self.cycle_mode)
        self.mode_button.pack(side='left',padx=12)
        Tooltip(self.mode_button,lambda:tr(self.mode.get())+tr(' · 点击切换'))
        self.mode.trace_add('write',lambda *args:self.update_mode_button())
        self.update_mode_button()
        self.view_icons={name:transport_icon(name) for name in ('turntable','list')}
        self.view_button=ttk.Button(bottom,image=self.view_icons['turntable'],style='Transport.TButton',command=self.toggle_turntable)
        self.view_button.pack(side='left',padx=(0,12))
        Tooltip(self.view_button,lambda:'曲目列表' if self.turntable_visible else '唱机模式')
        self.volume_bar = VolumeMeter(bottom, self.volume, command=lambda v:self.control('set_property','volume',float(v)),
                                      height=self.transport_buttons['play'].winfo_reqheight())
        self.volume_bar.pack(side='left')
        Tooltip(self.volume_bar, '音量 · 点击或拖动调整，滚轮微调')
        status_line = ttk.Frame(root,padding=(10,6))
        status_line.grid(row=4,column=0,sticky='ew')
        self.status_expand=ttk.Button(status_line,style='Cratelog.TButton',text='⋯',width=3,command=self.show_status_details)
        self.status_expand.pack(side='right')
        Tooltip(self.status_expand,'查看完整状态信息')
        self.status_label=ttk.Label(status_line,text='',anchor='w')
        self.status_label.pack(side='left',fill='x',expand=True)
        self.status_font=tkfont.Font(root=root,font=ttk.Style(root).lookup('TLabel','font'))
        self.status.trace_add('write',lambda *_:self.refresh_status_line())
        self.status_label.bind('<Configure>',lambda event:self.refresh_status_line())
        self.refresh_status_line()
        root.protocol('WM_DELETE_WINDOW',self.close)
        if sys.platform=='darwin':root.createcommand('::tk::mac::Quit',self.close)
        def bind_buttons(widget):
            for child in widget.winfo_children():
                if isinstance(child,ttk.Button):child.bind('<space>',self.space_next)
                bind_buttons(child)
        bind_buttons(root)
        self.poll_job = root.after(100,self.poll)
        if self.settings.get('root') and Path(self.settings['root']).is_dir(): self.set_root(self.settings['root'])
        self.restore_job = root.after(100,self.restore_workspace)

    def restore_workspace(self):
        layout=self.settings.get('layout',{})
        try:self.root.geometry(layout.get('geometry','1280x820'))
        except tk.TclError:pass
        if layout.get('maximized'):
            try:self.root.state('zoomed')
            except tk.TclError:pass
        self.root.update_idletasks()
        top_ratio=layout.get('top_split')
        if isinstance(top_ratio,(int,float)) and 0<top_ratio<1:self.top_pane.sashpos(0,round(self.top_pane.winfo_width()*top_ratio))
        ratio=layout.get('split')
        if isinstance(ratio,(int,float)) and 0<ratio<1:
            self.library_pane.sashpos(0,round(self.library_pane.winfo_width()*ratio))
        widths=layout.get('columns',{})
        for key in self.tracks['columns']:
            if key in self.fixed_track_widths:continue
            ratio=widths.get(key)
            if isinstance(ratio,(int,float)) and 0<ratio<=1:self.tracks.column(key,width=max(30,round(self.tracks.winfo_width()*ratio)))
        browse=self.settings.get('browse',{})
        folder=Path(browse.get('folder') or '.')
        if self.folder is not None or not browse.get('folder') or not folder.is_dir():return
        self.pending_restore=browse
        paths=list(browse.get('expanded',[]))
        paths.extend(str(p) for p in reversed([folder,*folder.parents]))
        for path in sorted(set(paths),key=lambda p:len(Path(p).parts)):
            if self.tree.exists(path):
                self.tree.focus(path);self.expand();self.tree.item(path,open=True)
        if self.tree.exists(str(folder)):
            self.tree.selection_set(str(folder));self.tree.focus(str(folder));self.tree.see(str(folder))
        self.load_folder(folder)

    def save_workspace(self):
        self.root.update_idletasks()
        columns=self.tracks['columns'];total=sum(self.tracks.column(k,'width') for k in columns)
        self.settings['layout']={'geometry':self.normal_geometry,'maximized':self.root.state()=='zoomed',
            'top_split':self.top_pane.sashpos(0)/max(1,self.top_pane.winfo_width()),
            'split':self.library_pane.sashpos(0)/max(1,self.library_pane.winfo_width()),
            'columns':{k:self.tracks.column(k,'width')/max(1,total) for k in columns}}
        expanded=[]
        def collect(parent=''):
            for node in self.tree.get_children(parent):
                if self.tree.item(node,'open'):expanded.append(node);collect(node)
        collect()
        self.settings.update(volume=self.volume.get(),mode=self.mode.get())
        selected=[self.album['tracks'][int(i)]['filename'] for i in self.tracks.selection()] if self.album else []
        focus=self.tracks.focus()
        playing=''
        if self.folder and self.current_track_id:
            try:playing=self.current_track_id.relative_to(self.folder).as_posix()
            except ValueError:pass
        self.settings['browse']={'folder':str(self.folder) if self.folder else '', 'selected':selected,'playing':playing,
            'focus':self.album['tracks'][int(focus)]['filename'] if focus and self.album else '', 'scroll':self.tracks.yview()[0], 'expanded':expanded}
        atomic_json(self.settings_path,self.settings)

    def space_next(self,event):
        if event.widget.winfo_toplevel()!=self.root or self.root.grab_current():return
        if event.widget.winfo_class() in ('Entry','TEntry','Text','TCombobox','Spinbox','TSpinbox'):return
        self.next()
        return 'break'

    def track_menu(self,event):
        row=self.tracks.identify_row(event.y)
        if not row or not self.album:return 'break'
        self.tracks.selection_set(row);self.tracks.focus(row)
        menu=tk.Menu(self.root,tearoff=False,bg='#30363c',fg='#e7e7e7')
        menu.add_command(label=tr('复制曲名'),command=lambda:self.copy_track_info(int(row)))
        menu.add_command(label=tr('编辑音频标签（ID3）'),command=lambda:self.edit_tags(int(row)))
        try:menu.tk_popup(event.x_root,event.y_root)
        finally:menu.grab_release()
        return 'break'

    def copy_track_info(self,index):
        if not self.album:return
        from cratelog_tags import read_tags
        from cratelog_library import parse_album_folder
        key=self.album['tracks'][index]['filename']
        source=self.album.get('_track_sources',{}).get(key,{})
        cached=self.album.get('_durations',{}).get(key,{})
        file=self.folder/source.get('file',key)
        try:tags=read_tags(file)
        except Exception:tags={}
        metadata=self.display_metadata()
        parsed=parse_album_folder(self.folder) or {}
        clean=lambda value:' '.join(str(value or '').split())
        def first(*values):return next((clean(v) for v in values if clean(v)), '')
        artist=first(source.get('performer'),tags.get('artist'),cached.get('artist'),metadata.get('音乐人'),parsed.get('音乐人'))
        title=first(source.get('title'),tags.get('title'),cached.get('title'),file.stem)
        album=first(source.get('album_title'),tags.get('album'),metadata.get('专辑名'),parsed.get('专辑名'),self.folder.name)
        label=clean(metadata.get('唱片厂牌'))
        year=first(metadata.get('出版年份'),tags.get('date'),parsed.get('出版年份'))
        text='[::] '+ ' - '.join((artist,title,album))+' ['+', '.join((label,year))+']'
        self.root.clipboard_clear();self.root.clipboard_append(text)
        self.status.set(tr('已复制：')+text)

    def edit_tags(self,index):
        from cratelog_tags import FIELDS,read_tags,save_tags,stamp
        key=self.album['tracks'][index]['filename']
        is_cue='#track=' in key
        album_folder=self.folder
        if is_cue:
            from cratelog_tracks import parse_cue,save_cue_track
            cue_name,number=key.rsplit('#track=',1);number=int(number)
            path=album_folder/cue_name
            try:
                expected=path.read_bytes()
                part=next(t for t in parse_cue(path,album_folder.resolve()) if t['number']==number)
                original={'title':part.get('title',''),'artist':part.get('performer','')}
            except Exception as e:messagebox.showerror(tr('读取标签失败'),str(e),parent=self.root);return
            FIELDS=[('title','TITLE'),('artist','PERFORMER')]
        else:
            path=album_folder/key
            try:expected=stamp(path);original=read_tags(path)
            except Exception as e:messagebox.showerror(tr('读取标签失败'),tr(str(e)),parent=self.root);return
        win=tk.Toplevel(self.root);win.title(tr('编辑音频标签'));win.configure(bg='#202428');win.transient(self.root)
        win.geometry('660x570+{0}+{1}'.format(self.root.winfo_rootx() + 80, self.root.winfo_rooty() + 60))
        win.columnconfigure(1,weight=1)
        ttk.Label(win,text=tr(key),wraplength=600).grid(row=0,column=0,columnspan=3,padx=16,pady=12,sticky='w')
        variables={}
        win.tag_variables=variables
        win.copy_icon=transport_icon('copy',width=20)
        def copy(value):win.clipboard_clear();win.clipboard_append(value.get())
        for row,(name,label) in enumerate(FIELDS,1):
            value=tk.StringVar(win,value=original[name]);variables[name]=value
            ttk.Label(win,text=tr(label)).grid(row=row,column=0,padx=12,pady=5,sticky='w')
            tk.Entry(win,textvariable=value,bg='#30363c',fg='#e7e7e7',insertbackground='#ffe2aa',relief='flat',
                     borderwidth=0,highlightthickness=1,highlightbackground='#454e56',highlightcolor='#e9a65d',
                     selectbackground='#704a2c',selectforeground='#ffffff').grid(row=row,column=1,sticky='ew',ipady=5)
            copy_button=ttk.Button(win,image=win.copy_icon,style='Cratelog.TButton',command=lambda v=value:copy(v))
            copy_button.grid(row=row,column=2,padx=12)
            Tooltip(copy_button,tr('复制')+' '+tr(label))
        def save():
            if self.current_file==path and self.playback_state!='stopped':
                messagebox.showinfo(tr('音频正在使用'),tr('请先停止该文件的播放，再保存标签。'),parent=win);return
            values={k:v.get() for k,v in variables.items()}
            button.state(['disabled'])
            def work():
                try:
                    if is_cue:
                        save_cue_track(path,number,values,expected)
                        return None,parse_cue(path,album_folder.resolve())
                    save_tags(path,values,original,expected)
                    from cratelog_tracks import read_audio_info
                    from cratelog_library import AudioMetadata
                    return None,read_audio_info(path,AudioMetadata)
                except Exception as e:return str(e),None
            def done(result):
                error,info=result
                if error:
                    if win.winfo_exists():button.state(['!disabled'])
                    messagebox.showerror(tr('保存标签失败'),tr(error),parent=win if win.winfo_exists() else self.root);return
                if self.folder==album_folder and is_cue:
                    for part in info:
                        self.album['_track_sources'][part['id']]=part
                        for track in self.album['tracks']:
                            if track['filename']==part['id']:track['display_name']=f"{part['number']:02} {part.get('title','')}".strip()
                    self.render()
                if self.folder==album_folder and not is_cue:
                    relative=path.relative_to(album_folder).as_posix()
                    durations=self.album.setdefault('_durations',{})
                    durations[relative]=info
                    for identity,source in self.album.get('_track_sources',{}).items():
                        if source.get('file')!=relative:continue
                        end=source.get('end') if source.get('end') is not None else info['seconds']
                        durations[identity]={**info,'seconds':max(0,end-source.get('start',0)) if end is not None else None}
                    self.render()
                self.status.set(tr('音频标签已保存：') + path.name)
                win.destroy()
            self.submit(work,done)
        button=ttk.Button(win,text=tr('保存'),style='Cratelog.TButton',command=save);button.grid(row=12,column=1,pady=15)
        ttk.Button(win,text=tr('关闭'),style='Cratelog.TButton',command=win.destroy).grid(row=12,column=2)
        win.bind('<Escape>',lambda e:win.destroy())

    def configure(self):
        if self.settings_window and self.settings_window.winfo_exists():
            self.settings_window.lift(); return
        win=tk.Toplevel(self.root); win.title(tr('Cratelog 设置')); win.geometry('760x860')
        self.settings_window = win
        win.configure(bg='#202428')
        win.transient(self.root)
        win.geometry('760x860+{0}+{1}'.format(max(0, self.root.winfo_rootx() + (self.root.winfo_width() - 760) // 2), max(0, self.root.winfo_rooty() + (self.root.winfo_height() - 860) // 2)))
        win.resizable(True, False)
        win.bind('<Escape>', lambda e: win.destroy())
        # Native Tk fields retain their palette even when the organizer changes
        # global ttk styles. Explicit cursor/selection colors stay readable.
        for label,var in [('同步 API（HTTPS）',self.url),('同步令牌（保存后长期有效）',self.token),('mpv 路径（可留空自动检测）',self.mpv)]:
            tk.Label(win,text=tr(label),bg='#202428',fg='#e7e7e7').pack(anchor='w',padx=18,pady=(12,4))
            tk.Entry(win,textvariable=var,show='*' if var is self.token else '',
                     bg='#30363c',fg='#e7e7e7',insertbackground='#ffe2aa',
                     selectbackground='#704a2c',selectforeground='#ffffff',relief='flat',
                     highlightthickness=1,highlightbackground='#454e56',highlightcolor='#e9a65d').pack(fill='x',padx=18,ipady=5)
        languages=language.get_available_languages()
        codes=[code for code,_ in languages]
        selected=self.settings.get('language',read_json(self.settings_path.parent/'config.json',{}).get('language','auto'))
        ttk.Label(win,text=tr('界面语言')).pack(anchor='w',padx=18,pady=(12,4))
        language_choice=ttk.Combobox(win,values=[name for _,name in languages],state='readonly')
        language_choice.current(codes.index(selected) if selected in codes else 0)
        language_choice.pack(fill='x',padx=18)
        ttk.Label(win,text=tr('语言设置将在重启后应用')).pack(anchor='w',padx=18,pady=4)
        self.subtitle_settings_panel(win)
        self.lastfm_settings_panel(win)
        def save():
            try: style=parse_subtitle_form(self.sub_font.get(),self.sub_size.get(),self.sub_color.get())
            except ValueError as e:
                messagebox.showerror(tr('字幕设置'),tr(str(e)),parent=win);return
            if not self.save_lastfm_settings():return
            selected_language=codes[language_choice.current()]
            self.settings.update(url=self.url.get().strip(),mpv=self.mpv.get().strip(),token=self.token.get().strip(),language=selected_language,subtitle=style)
            self.apply_subtitle()
            config=read_json(self.settings_path.parent/'config.json',{})
            config['language']=selected_language
            atomic_json(self.settings_path.parent/'config.json',config)
            if self.organizer:self.organizer.saved_language=selected_language
            atomic_json(self.settings_path,self.settings); win.destroy(); self.refresh_catalog()
        ttk.Button(win,text=tr('保存'),command=save,style='Cratelog.TButton').pack(pady=16)

    def subtitle_settings_panel(self,win):
        style=subtitle_style(self.settings.get('subtitle'))
        panel=ttk.LabelFrame(win,text=tr('字幕'),padding=10);panel.pack(fill='x',padx=18,pady=(14,0))
        self.sub_font=tk.StringVar(value=style['font'])
        self.sub_size=tk.StringVar(value=str(style['size']))
        self.sub_color=tk.StringVar(value=style['color'])
        row=ttk.Frame(panel);row.pack(fill='x',pady=4)
        ttk.Label(row,text=tr('字幕字体'),width=12).pack(side='left')
        families=sorted({name for name in tkfont.families() if name and not name.startswith('@')},key=str.casefold)
        ttk.Combobox(row,textvariable=self.sub_font,values=families).pack(side='left',fill='x',expand=True)
        row=ttk.Frame(panel);row.pack(fill='x',pady=4)
        ttk.Label(row,text=tr('字高'),width=12).pack(side='left')
        ttk.Spinbox(row,from_=8,to=300,textvariable=self.sub_size,width=8).pack(side='left')
        ttk.Label(row,text=tr('字幕颜色'),width=12).pack(side='left',padx=(18,0))
        swatch=tk.Label(row,width=4,bg=style['color'],relief='solid',bd=1)
        swatch.pack(side='left')
        tk.Entry(row,textvariable=self.sub_color,width=10,bg='#30363c',fg='#e7e7e7',insertbackground='#ffe2aa',
                 selectbackground='#704a2c',selectforeground='#ffffff',relief='flat',
                 highlightthickness=1,highlightbackground='#454e56',highlightcolor='#e9a65d').pack(side='left',padx=8,ipady=3)
        def paint(*_args):
            color=self.sub_color.get().strip()
            if re.fullmatch(r'#[0-9A-Fa-f]{6}',color):
                try:swatch.configure(bg=color)
                except tk.TclError:pass
        self.sub_color.trace_add('write',paint)
        def pick():
            chosen=colorchooser.askcolor(color=self.sub_color.get() or '#FFFFFF',parent=win,title=tr('字幕颜色'))
            if chosen and chosen[1]:self.sub_color.set(chosen[1].upper())
        ttk.Button(row,style='Cratelog.TButton',text=tr('选择颜色'),command=pick).pack(side='left')
        ttk.Label(panel,text=tr('字体留空使用无衬线默认字体。字高以高度为 720 的画面为基准，频谱窗口较矮时会按比例缩小。'),wraplength=680).pack(anchor='w',pady=(4,0))

    def apply_subtitle(self):
        style=subtitle_style(self.settings.get('subtitle'))
        if not self.engine or self.engine.process.poll() is not None:return
        self.engine.command('set_property','sub-font',style['font'] or 'sans-serif')
        self.engine.command('set_property','sub-font-size',style['size'])
        self.engine.command('set_property','sub-color',style['color'])

    def lastfm_settings_panel(self,win):
        panel=ttk.LabelFrame(win,text=tr('Last.fm · 正在播放与聆听记录'),padding=10);panel.pack(fill='x',padx=18,pady=(14,0))
        self.lfm_key=tk.StringVar(value=self.lastfm_config.get('key',''))
        self.lfm_secret=tk.StringVar(value=self.lastfm_config.get('secret',''))
        self.lfm_enabled=tk.BooleanVar(value=self.lastfm_config.get('enabled',False))
        self.lfm_status=tk.StringVar(value=tr('已授权：')+self.lastfm_config['username'] if self.lastfm_config.get('username') else tr('尚未授权'))
        ttk.Checkbutton(panel,text=tr('启用 Last.fm（发送曲目资料，不上传音频）'),variable=self.lfm_enabled).pack(anchor='w')
        for label,var,mask in [('API Key',self.lfm_key,''),('Shared Secret',self.lfm_secret,'*')]:
            row=ttk.Frame(panel);row.pack(fill='x',pady=4)
            ttk.Label(row,text=tr(label),width=15).pack(side='left');ttk.Entry(row,textvariable=var,show=mask).pack(side='left',fill='x',expand=True)
        row=ttk.Frame(panel);row.pack(fill='x',pady=6)
        ttk.Button(row,style='Cratelog.TButton',text=tr('申请 API Key ↗'),command=lambda:webbrowser.open('https://www.last.fm/api/account/create')).pack(side='left')
        ttk.Button(row,style='Cratelog.TButton',text=tr('浏览器授权'),command=self.lastfm_authorize).pack(side='left',padx=4)
        ttk.Button(row,style='Cratelog.TButton',text=tr('完成授权并启用'),command=self.lastfm_finish_auth).pack(side='left')
        ttk.Button(row,style='Cratelog.TButton',text=tr('断开'),command=self.lastfm_disconnect).pack(side='left',padx=4)
        ttk.Label(panel,textvariable=self.lfm_status,wraplength=620).pack(anchor='w')
        ttk.Label(panel,text=tr('超过 30 秒的曲目，实际聆听达到一半或 4 分钟后录入。\n缺少可靠艺术家或曲名时不提交；网络失败的记录保留并重试。'),wraplength=620).pack(anchor='w',pady=(5,0))

    def save_lastfm_settings(self):
        config=dict(self.lastfm_config);key=self.lfm_key.get().strip();secret=self.lfm_secret.get().strip()
        if (key,secret)!=(config.get('key',''),config.get('secret','')):config.pop('session',None);config.pop('username',None)
        config.update(key=key,secret=secret,enabled=self.lfm_enabled.get())
        if config['enabled'] and not config.get('session'):
            self.lfm_status.set(tr('请先完成浏览器授权'));return False
        self.settings['lastfm']=stored_config(config);self.lastfm_config=config;self.lastfm.configure(config)
        return True

    def lastfm_authorize(self):
        api=LastfmAPI(self.lfm_key.get(),self.lfm_secret.get())
        self.lfm_status.set(tr('正在申请授权令牌…'))
        def work():
            try:return api.call('auth.getToken'),None
            except Exception as e:return None,str(e)
        def done(result):
            data,error=result
            if not self.settings_window.winfo_exists():return
            if error:self.lfm_status.set(tr(error));return
            self.lfm_pending=(api,data['token'])
            webbrowser.open(api.authorize_url(data['token']))
            self.lfm_status.set(tr('请在浏览器允许授权，然后点击“完成授权并启用”'))
        self.submit(work,done)

    def lastfm_finish_auth(self):
        if not getattr(self,'lfm_pending',None):self.lfm_status.set(tr('请先点击“浏览器授权”'));return
        api,token=self.lfm_pending
        if (api.key,api.secret)!=(self.lfm_key.get().strip(),self.lfm_secret.get().strip()):self.lfm_status.set(tr('密钥已改变，请重新开始授权'));return
        def work():
            try:return api.call('auth.getSession',token=token),None
            except Exception as e:return None,str(e)
        def done(result):
            data,error=result
            if not self.settings_window.winfo_exists():return
            if error:self.lfm_status.set(tr(error));return
            session=data['session']
            self.lastfm_config=dict(key=api.key,secret=api.secret,session=session['key'],username=session['name'],enabled=True)
            self.lfm_enabled.set(True);self.lfm_pending=None
            self.save_lastfm_settings();atomic_json(self.settings_path,self.settings)
            self.lfm_status.set(tr('已授权：')+session['name']+tr('；从下一曲开始记录'))
        self.submit(work,done)

    def lastfm_disconnect(self):
        self.lastfm_config.update(enabled=False,session='',username='');self.lfm_enabled.set(False)
        self.lfm_pending=None;self.lastfm.configure(self.lastfm_config);self.lastfm_listening=None
        self.settings['lastfm']=stored_config(self.lastfm_config);atomic_json(self.settings_path,self.settings)
        self.lfm_status.set(tr('已断开；需要时可重新授权'))

    def show_cover(self, event=None):
        if not self.album or not self.album.get('images'): return
        path = self.folder / self.album['images'][0]['filename']
        try:
            from PIL import ImageOps
            with Image.open(path) as im:
                original = ImageOps.exif_transpose(im).convert('RGB')
        except (OSError, ValueError) as e:
            messagebox.showerror(tr('封面读取失败'), tr(str(e)), parent=self.root)
            return
        if self.cover_preview and self.cover_preview.winfo_exists(): self.cover_preview.destroy()
        win = tk.Toplevel(self.root)
        self.cover_preview = win
        win.title('Cratelog · {0} · {1} × {2}'.format(path.name, original.width, original.height))
        win.configure(bg='#151719')
        win.transient(self.root)
        from cratelog_picture import PictureCanvas,visible_screens,bounded_geometry
        screen_areas=visible_screens(self.root)
        paths=[self.folder/item['filename'] for item in self.album['images']]
        index=0
        def move(delta):
            nonlocal index,original
            target=(index+delta)%len(paths)
            try:
                with Image.open(paths[target]) as im:picture=ImageOps.exif_transpose(im).convert('RGB')
            except (OSError,ValueError) as e:
                messagebox.showerror(tr('图片读取失败'),tr(str(e)),parent=win);return
            index=target;original=picture;canvas.set_image(picture)
            win.title('Cratelog · {0} · {1}/{2}'.format(paths[index].name,index+1,len(paths)))
            fit_window()
        def grow_window(image_width,image_height):
            width=max(win.winfo_width(),round(image_width)+24)
            height=max(win.winfo_height(),round(image_height)+24)
            cx=win.winfo_x()+win.winfo_width()/2;cy=win.winfo_y()+win.winfo_height()/2
            width,height,x,y=bounded_geometry(width,height,cx,cy,screen_areas)
            # Keep the gesture's image point stationary when screen-edge clamping
            # makes window expansion asymmetric.
            canvas.offset[0]+=win.winfo_x()-x+(win.winfo_width()-width)/2
            canvas.offset[1]+=win.winfo_y()-y+(win.winfo_height()-height)/2
            win.geometry(f'{width}x{height}+{x}+{y}')
        canvas=PictureCanvas(win,original,move if len(paths)>1 else None,on_zoom=grow_window,on_error=lambda error:messagebox.showwarning('Cratelog',error,parent=win))
        canvas.pack(fill='both',expand=True)
        def fit_window():
            self.root.update_idletasks()
            max_width=max(1,min(self.root.winfo_width(),self.root.winfo_screenwidth()-40))
            max_height=max(1,min(self.root.winfo_height(),self.root.winfo_screenheight()-80))
            scale=max(0,min(1,(max_width-24)/original.width,(max_height-24)/original.height))
            width=min(max_width,max(1,int(original.width*scale))+24)
            height=min(max_height,max(1,int(original.height*scale))+24)
            cx=self.root.winfo_rootx()+self.root.winfo_width()/2
            cy=self.root.winfo_rooty()+self.root.winfo_height()/2
            width,height,x,y=bounded_geometry(width,height,cx,cy,screen_areas)
            win.maxsize(max(int(area[2])-16 for area in screen_areas),max(int(area[3])-56 for area in screen_areas))
            win.geometry(f'{width}x{height}+{x}+{y}')
        def next_image(event):
            move(1);return 'break'
        win.bind('<space>',next_image)
        win.bind('<Left>',lambda e:move(-1));win.bind('<Right>',lambda e:move(1))
        win.bind('<Escape>',lambda e:win.destroy())
        fit_window()
        win.after_idle(canvas.redraw)
        win.after_idle(canvas.focus_set)

    def remote(self):
        return Remote(self.url.get().strip(), self.token.get().strip())

    def choose_root(self):
        folder=filedialog.askdirectory(parent=self.root)
        if folder: self.set_root(folder)

    def set_root(self,folder):
        self.settings['root']=str(folder); atomic_json(self.settings_path,self.settings)
        self.tree.delete(*self.tree.get_children())
        self.tree.insert('', 'end', iid=str(Path(folder)), text=tr(Path(folder).name or str(folder)))
        self.tree.insert(str(Path(folder)),'end',text='…')
        self.tree.focus(str(Path(folder))); self.expand(); self.tree.item(str(Path(folder)),open=True)
        self.refresh_catalog()

    def has_remote(self, folder, album=None):
        return str(folder) in self.confirmed_remote or self.remote_catalog.contains(folder,album)

    def refresh_catalog(self):
        self.catalog_generation+=1;generation=self.catalog_generation
        self.remote_catalog=CatalogIndex();self.confirmed_remote.clear()
        self.paint_remote_folders()
        if not self.url.get().strip() or not self.token.get().strip():return
        try:remote=self.remote()
        except ValueError as e:self.status.set(tr(str(e)));return
        def done(index):
            if generation!=self.catalog_generation:return
            self.remote_catalog=index;self.paint_remote_folders()
            if self.album and not self.album.get('_recursive') and index.lookup(self.folder,self.album):self.load_folder(self.folder)
        self.submit(remote.catalog,done)

    def paint_remote_folders(self, parent=''):
        for node in self.tree.get_children(parent):
            self.tree.item(node,tags=('remote',) if self.has_remote(node) else ())
            self.paint_remote_folders(node)
        if parent=='' and self.album:
            self.update_review_summary()
            self.update_album_heading()

    def update_review_summary(self):
        if not self.album:return
        a=self.album
        self.remote_button.state(['!disabled'] if self.remote_record_id() else ['disabled'])
        self.review_summary.configure(text=('☁ ' if self.has_remote(self.folder, a) else '') + ('★ {0:g} / 5'.format(float(a['rating'])) if a['rating'] else tr('未评分')) + (tr(' · 已写评论') if a.get('personal_comment') else ''))

    def remote_record_id(self):
        if not self.album or not self.folder:return None
        record=self.remote_catalog.lookup(self.folder,self.album)
        if record:return record['id']
        if str(self.folder) in self.confirmed_remote:return self.album.get('id')
        return None

    def open_remote_album(self):
        identifier=self.remote_record_id()
        if not identifier:return
        parts=urlsplit(self.url.get().strip())
        path=parts.path.rsplit('/',1)[0]+'/cratelog.php'
        webbrowser.open(urlunsplit((parts.scheme,parts.netloc,path,urlencode({'album':identifier}),'')))

    def refresh_root(self):
        if self.settings.get('root'): self.set_root(self.settings['root'])

    def reveal_folder(self,folder):
        root=Path(self.settings.get('root',''))
        try:parts=Path(folder).relative_to(root).parts
        except ValueError:return
        parent=root
        for part in parts:
            if not self.tree.exists(str(parent)):return
            self.tree.focus(str(parent));self.expand();self.tree.item(str(parent),open=True)
            parent=parent/part
        if self.tree.exists(str(parent)):
            self.tree.selection_set(str(parent));self.tree.focus(str(parent));self.tree.see(str(parent))

    def expand(self,event=None):
        node=self.tree.focus()
        if not node: return
        self.tree.delete(*self.tree.get_children(node))
        try:
            for path in sorted(Path(node).iterdir(),key=lambda p:p.name.lower()):
                if path.is_dir() and not path.name.startswith('.') and not path.is_symlink() and not getattr(path, 'is_junction', lambda: False)():
                    self.tree.insert(node,'end',iid=str(path),text=tr(path.name),tags=('remote',) if self.has_remote(path) else ())
                    self.tree.insert(str(path),'end',text='…')
        except OSError as e: self.status.set(tr(str(e)))

    def choose_folder(self,event=None):
        selection=self.tree.selection()
        if selection and Path(selection[0]).is_dir() and Path(selection[0])!=self.folder: self.load_folder(Path(selection[0]))

    def submit(self,work,done):
        future=self.pool.submit(work)
        future.add_done_callback(lambda f:self.events.put(('done',(f,done))))

    def load_folder(self,folder,autoplay=False):
        self.load_generation += 1
        generation = self.load_generation
        self.folder=folder; self.album=None
        self.remote_button.state(['disabled'])
        self.status.set(tr('正在读取本地资料…'))
        self.title.configure(text=tr('正在读取：') + folder.name)
        self.album_subtitle.configure(text='')
        self.review_summary.configure(text='')
        self.cover.configure(image='', text='')
        self.tracks.delete(*self.tracks.get_children())
        def loaded(a):
            if self.load_generation != generation: return
            if not a.get('_recursive') and self.remote_catalog.lookup(folder,a):
                self.load_folder(folder,autoplay=autoplay);return
            self.album=a; self.render(); self.status.set('；'.join(a.get('_scan_warnings', [])) or tr('本地资料已加载'))
            if autoplay:self.play_selected()
            if self.pending_restore:
                state=self.pending_restore;self.pending_restore=None
                if str(folder)==state.get('folder'):
                    rows={a['tracks'][int(i)]['filename']:i for i in self.tracks.get_children()}
                    self.tracks.selection_set([rows[name] for name in state.get('selected',[]) if name in rows])
                    if state.get('focus') in rows:self.tracks.focus(rows[state['focus']])
                    self.tracks.yview_moveto(max(0,min(1,state.get('scroll',0))))
                    if state.get('playing') in rows:
                        row=rows[state['playing']]
                        self.tracks.selection_set(row);self.tracks.focus(row);self.tracks.see(row)
        recursive=True if self.remote_catalog.lookup(folder,read_json(folder/'.cratelog.json',{})) else None
        self.submit(lambda:load_album(folder,recursive=recursive),loaded)

    def display_metadata(self):
        m=dict(self.album.get('metadata',{}))
        remote=self.remote_catalog.lookup(self.folder,self.album)
        if remote:
            for field,key in [('音乐人','artist'),('专辑名','album'),('出版年份','year'),('唱片厂牌','label')]:
                if remote.get(key):m[field]=remote[key]
        return m

    def update_album_heading(self):
        m=self.display_metadata()
        self.prepare_album_playlist(m)
        self.title.configure(text=tr(' — '.join((str(v) for v in (m.get(tr('音乐人')), m.get(tr('专辑名')) or self.folder.name) if v))))
        label=' '.join(str(m.get('唱片厂牌','')).split())
        year=' '.join(str(m.get('出版年份','')).split())
        self.album_subtitle.configure(text=tr(' · '.join((part for part in (year, label) if part))))

    def prevent_fixed_column_resize(self,event):
        if self.tracks.identify_region(event.x,event.y)!='separator':return
        column=self.tracks.identify_column(event.x)
        if not column:return
        index=int(column[1:])-1
        columns=self.tracks['columns']
        if any(columns[i] in self.fixed_track_widths for i in (index,index+1) if 0<=i<len(columns)):
            return 'break'

    def refresh_status_line(self):
        full=self.status.get();text=' '.join(full.split())
        available=max(0,self.status_label.winfo_width()-4)
        overflow=self.status_font.measure(text)>available or '\n' in full or '\r' in full
        if self.status_font.measure(text)>available:
            low,high=0,len(text)
            while low<high:
                middle=(low+high+1)//2
                if self.status_font.measure(text[:middle]+'…')<=available:low=middle
                else:high=middle-1
            text=text[:low]+'…'
        self.status_label.configure(text=tr(text))
        self.status_expand.configure(state='normal' if overflow else 'disabled')

    def show_status_details(self):
        full=self.status.get()
        if getattr(self,'status_window',None) and self.status_window.winfo_exists():self.status_window.destroy()
        win=tk.Toplevel(self.root);self.status_window=win
        win.title(tr('Cratelog · 完整状态信息'));win.configure(bg='#202428');win.transient(self.root)
        win.geometry('640x300');win.minsize(360,180)
        frame=ttk.Frame(win,padding=12);frame.pack(fill='both',expand=True)
        text=tk.Text(frame,wrap='word',bg='#202428',fg='#e7e7e7',relief='flat',padx=8,pady=8)
        scroll=ttk.Scrollbar(frame,command=text.yview);scroll.pack(side='right',fill='y')
        text.configure(yscrollcommand=scroll.set);text.pack(fill='both',expand=True)
        text.insert('1.0',full);text.configure(state='disabled')
        ttk.Button(win,style='Cratelog.TButton',text=tr('关闭'),command=win.destroy).pack(pady=(0,12))
        win.bind('<Escape>',lambda event:win.destroy());win.update_idletasks()
        win.geometry('+{0}+{1}'.format(max(0, self.root.winfo_rootx() + (self.root.winfo_width() - win.winfo_width()) // 2), max(0, self.root.winfo_rooty() + (self.root.winfo_height() - win.winfo_height()) // 2)))

    def show_about(self):
        if getattr(self,'about_window',None) and self.about_window.winfo_exists():self.about_window.lift();return
        win=tk.Toplevel(self.root);self.about_window=win
        win.title(tr('关于 Cratelog'));win.configure(bg='#202428');win.resizable(False,False);win.transient(self.root)
        tk.Label(win,image=self.brand_icon,bg='#202428').pack(pady=(24,8))
        tk.Label(win,text='Cratelog  {0}'.format(BRAND['version']),bg='#202428',fg='#f59a38',font=(UI_FONT,18,'bold')).pack(padx=48)
        tk.Label(win,text=tr('音乐收藏 · 整理 · 聆听\n\n开发者：') + BRAND['developer'],bg='#202428',fg='#e7e7e7').pack(pady=14)
        ttk.Button(win,style='Cratelog.TButton',text='like-mix.com ↗',command=lambda:webbrowser.open(BRAND['website'])).pack()
        tk.Label(win,text=tr(BRAND['copyright']),bg='#202428',fg='#89939b').pack(padx=30,pady=18)
        ttk.Button(win,style='Cratelog.TButton',text=tr('关闭'),command=win.destroy).pack(pady=(0,20))
        win.bind('<Escape>',lambda e:win.destroy())
        win.update_idletasks()
        x=self.root.winfo_rootx()+(self.root.winfo_width()-win.winfo_width())//2
        y=self.root.winfo_rooty()+(self.root.winfo_height()-win.winfo_height())//2
        win.geometry('+{0}+{1}'.format(max(0, x), max(0, y)))

    def track_heading_hover(self,event):
        clickable=self.tracks.identify_region(event.x,event.y)=='heading' and self.tracks.identify_column(event.x)=='#2'
        self.tracks.configure(cursor='hand2' if clickable else '')

    def track_double_click(self,event):
        region=self.tracks.identify_region(event.x,event.y)
        if region=='heading' and self.tracks.identify_column(event.x)=='#2':
            self.show_id3_titles=not self.show_id3_titles
            self.settings['show_id3_titles']=self.show_id3_titles
            self.tracks.heading('file',text=tr('ID3曲名') if self.show_id3_titles else tr('本地音频文件名'))
            if self.album:self.render()
        elif region=='cell':self.play_selected()
        return 'break'

    def resize_track_number_column(self):
        font=tkfont.Font(root=self.root,font=ttk.Style(self.root).lookup('Treeview','font'))
        digits=len(str(max(1,len(self.album['tracks']))))
        # Reserve the widest numeral and the playing marker for every row.
        digit=max('0123456789',key=font.measure)
        width=max(45,font.measure('▶ '+digit*digits)+20)
        self.fixed_track_widths['number']=width
        self.tracks.column('number',width=width,minwidth=width,stretch=False,anchor='center')

    def render(self):
        a=self.album
        self.resize_track_number_column()
        self.update_album_heading()
        self.rating.set(str(a['rating']))
        self.update_review_summary()
        selection=self.tracks.selection();focus=self.tracks.focus();scroll=self.tracks.yview()[0]
        self.tracks.delete(*self.tracks.get_children())
        for i,t in enumerate(a['tracks']):
            tag='highlighted' if t['highlighted'] else 'selected' if t['selected'] else ''
            seconds=a.get('_durations',{}).get(t['filename'],{}).get('seconds')
            duration='—'
            if seconds is not None:
                total=max(0,round(seconds));duration='{0}:{1:02}'.format(total // 60, total % 60)
            cue_title=a.get('_track_sources',{}).get(t['filename'],{}).get('title','')
            display='{0}  ·  {1}'.format(cue_title, t['filename']) if cue_title else t['filename']
            if self.show_id3_titles:
                info=a.get('_durations',{}).get(t['filename'],{})
                source=a.get('_track_sources',{}).get(t['filename'],{})
                title=cue_title or info.get('title')
                artist=source.get('performer') or info.get('artist')
                display=' - '.join(v for v in (artist,title) if v) if title else t['filename']
            self.tracks.insert('','end',iid=str(i),values=(i+1,display,duration,'★' if t['highlighted'] else '', '✓' if t['selected'] else ''),tags=(tag,))
        self.tracks.selection_set([i for i in selection if self.tracks.exists(i)])
        if focus and self.tracks.exists(focus):self.tracks.focus(focus)
        self.tracks.yview_moveto(scroll)
        self.highlight_playing(select=False)
        self.cover.configure(image='',text=tr('暂无封面'),cursor=''); self.cover.image=None
        if a['images']:
            try:
                with Image.open(self.folder/a['images'][0]['filename']) as im:
                    im.thumbnail((125,125)); picture=ImageTk.PhotoImage(im.copy())
                self.cover.configure(image=picture,text='',cursor='hand2'); self.cover.image=picture
            except (OSError,ValueError): pass

    def save_rating(self,event=None):
        if self.album:
            self.album['rating']=float(self.rating.get()); self.persist()

    def show_review(self):
        if not self.album:return
        if self.review_window and self.review_window.winfo_exists():self.review_window.lift();return
        folder=self.folder
        win=tk.Toplevel(self.root); self.review_window=win
        win.title(tr('Cratelog · 评价')); win.configure(bg='#202428'); win.transient(self.root)
        win.geometry('600x420+{0}+{1}'.format(max(0, self.root.winfo_rootx() + 120), max(0, self.root.winfo_rooty() + 100)))
        win.minsize(460,340)
        value=tk.DoubleVar(win,value=float(self.album['rating']))
        tk.Label(win,text=tr('专辑评分 · 点击星星左半或右半，支持半星'),bg='#202428',fg='#e7e7e7').pack(anchor='w',padx=18,pady=(16,4))
        stars=HalfStarPicker(win,value); stars.pack(anchor='w',padx=18)
        score=tk.Label(win,bg='#202428',fg='#e9b965')
        score.pack(anchor='w',padx=18)
        def score_changed(*args):score.configure(text='{0:g} / 5'.format(value.get()) if value.get() else tr('未评分'))
        value.trace_add('write',score_changed);score_changed()
        tk.Label(win,text=tr('个人评论'),bg='#202428',fg='#e7e7e7').pack(anchor='w',padx=18,pady=(12,6))
        comment=tk.Text(win,height=7,wrap='word',bg='#30363c',fg='#e7e7e7',insertbackground='#ffe2aa',relief='flat',padx=9,pady=8)
        comment.pack(fill='both',expand=True,padx=18)
        comment.insert('1.0',self.album.get('personal_comment',''))
        def save():
            text=comment.get('1.0','end-1c')
            if len(text)>10000:
                messagebox.showerror(tr('评论过长'),tr('个人评论最多 10000 字。'),parent=win);return
            try:
                from cratelog_library import LOCK
                with LOCK:
                    current=load_album(folder)
                    current['rating']=value.get();current['personal_comment']=text
                    save_album(folder,current)
                if self.folder==folder:self.album=current;self.render()
                self.status.set(tr('评价已保存本地；点击同步当前专辑上传'))
                win.destroy()
            except Exception as e:messagebox.showerror(tr('评价保存失败'),tr(str(e)),parent=win)
        buttons=tk.Frame(win,bg='#202428');buttons.pack(fill='x',padx=18,pady=14)
        for label,command in [('保存',save),('取消',win.destroy),('清除评分',lambda:value.set(0))]:
            ttk.Button(buttons,text=tr(label),command=command,style='Cratelog.TButton').pack(side='left',padx=(0,8))
        win.bind('<Escape>',lambda e:win.destroy());win.grab_set()

    def persist(self):
        try:
            # Preserve sync bookkeeping written by an in-flight upload.
            from cratelog_library import LOCK
            with LOCK:
                disk=read_json(self.folder/'.cratelog.json',self.album)
                for key in ('id','_revision','_synced','_image_uploads','_skipped_documents','_skipped_images'):
                    if key in disk:self.album[key]=disk[key]
                save_album(self.folder,self.album)
            self.status.set(tr('已保存到本地；等待同步'))
        except Exception as e:messagebox.showerror(tr('保存失败'),tr(str(e)),parent=self.root)

    def mark(self,key):
        if not self.album:return
        for item in self.tracks.selection():
            track=self.album['tracks'][int(item)]; track[key]=not track[key]
        self.persist(); self.render()

    def sync_current(self):
        if self.folder:self.sync_paths([self.folder])

    def sync_paths(self,paths):
        if self.busy:return
        try:remote=self.remote()
        except Exception as e:messagebox.showerror(tr('同步设置'),tr(str(e)),parent=self.root); return
        self.busy=True; self.status.set(tr('正在同步；资料仍可在本地编辑…'))
        self.sync_cancel.clear()
        def work():
            failures=[]; conflicts=[]; count=0; skipped=[]; documents=[]
            for folder in paths:
                if self.sync_cancel.is_set():break
                try:
                    result=remote.sync(folder); count+=1
                    skipped.extend('{0}: {1}'.format(folder, name) for name in result.get('skipped_files',[]))
                    documents.append('{0}: {1}'.format(Path(folder).name,', '.join(result.get('confirmed_documents',[])) or '0'))
                except Conflict as e:conflicts.append((Path(folder),str(e)))
                except Exception as e:failures.append('{0}: {1}'.format(folder, e))
                self.events.put(('status','同步进度：成功 {0}，失败 {1}'.format(count, len(failures))))
            return count,failures,skipped,conflicts,documents
        def done(result):
            self.busy=False; count,failures,skipped,conflicts,documents=result
            if self.folder and self.album:
                self.album=read_json(self.folder/'.cratelog.json',self.album)
                self.render()
            self.status.set('{0}{1}{2}{3}{4}'.format(tr('同步已取消') if self.sync_cancel.is_set() else tr('同步完成'), tr('：成功 '), count, tr('，失败 '), len(failures)))
            if documents:self.status.set(self.status.get()+'\n'+tr('服务端已确认附件：')+'\n'+'\n'.join(documents))
            self.refresh_catalog()
            if skipped:messagebox.showinfo(tr('已跳过部分上传文件'),tr('\n'.join(skipped)),parent=self.root)
            if failures:messagebox.showwarning(tr('未同步项目（可重试）'),tr('\n'.join(failures)),parent=self.root)
            if conflicts:
                self.status.set('；'.join('{0}: {1}'.format(folder.name,error) for folder,error in conflicts))
                self.open_conflict_dialog(conflicts[0][0],remote)
        self.submit(work,done)

    def sync_all(self):
        root=self.settings.get('root')
        if not root:return
        def folders():
            from cratelog_library import AUDIO
            for directory,dirs,files in os.walk(root,followlinks=False):
                dirs[:]=[d for d in dirs if not Path(directory,d).is_symlink() and not getattr(Path(directory,d), 'is_junction', lambda: False)()]
                if 'album_info.json' in files or any(Path(f).suffix.lower() in AUDIO for f in files):yield Path(directory)
        self.sync_paths(folders())

    def resolve(self):
        if self.busy:
            self.status.set(tr('请等待同步完成或取消同步后再处理远端版本'))
            return
        if not self.album:return
        try:remote=self.remote()
        except Exception as e:messagebox.showerror(tr('同步设置'),tr(str(e))); return
        self.open_conflict_dialog(self.folder,remote)

    def open_conflict_dialog(self,folder,remote):
        from cratelog_conflict import catalog_candidates,fields,merge,target_folder,clean
        folder=Path(folder)
        def find_records():
            local=load_album(folder)
            catalog=remote.catalog()
            candidates=catalog_candidates(catalog,folder,local)
            if local.get('id') in catalog.ids and not any(r['id']==local['id'] for r in candidates):
                candidates.insert(0,next(r for r in catalog.records if r['id']==local['id']))
            return local,candidates
        def found(result):
            if isinstance(result,Exception):
                messagebox.showerror(tr('读取冲突资料失败'),str(result),parent=self.root);return
            local,candidates=result
            if not candidates:
                messagebox.showwarning(tr('无法确定远端专辑'),tr('目录中没有可安全关联的远端记录。请先在网页核对艺术家与专辑名。'),parent=self.root);return
            win=tk.Toplevel(self.root);win.title(tr('Cratelog · 本地与远端资料对比'))
            win.configure(bg='#202428');win.geometry('1050x690');win.transient(self.root);win.grab_set()
            tk.Label(win,text=tr('选择要更新的远端记录，再逐项选择最终采用的值。编号由服务器保留；附件在服务器取两端合集。'),bg='#202428',fg='#e7e7e7').pack(anchor='w',padx=12,pady=8)
            labels=['#{0}  ·  {1} — {2} ({3})  ·  {4}  ·  {5}'.format(r.get('number') or '—',r.get('artist',''),r.get('album',''),r.get('year',''),r.get('label',''),r.get('path','')) for r in candidates]
            picker=ttk.Combobox(win,values=labels,state='readonly')
            picker.pack(fill='x',padx=12,pady=(0,8))
            def view_record():
                if picker.current()<0 or not getattr(remote,'url',None):return
                identifier=candidates[picker.current()]['id']
                parts=urlsplit(remote.url)
                path=parts.path.rsplit('/',1)[0]+'/cratelog.php'
                webbrowser.open(urlunsplit((parts.scheme,parts.netloc,path,urlencode({'album':identifier}),'')))
            ttk.Button(win,text=tr('查看远端记录'),command=view_record).pack(anchor='w',padx=12,pady=(0,6))
            columns=('field','local','remote','choice')
            table=ttk.Treeview(win,columns=columns,show='headings',selectmode='extended')
            for key,title,width in [('field','字段',155),('local','本地',310),('remote','远端',310),('choice','采用',70)]:
                table.heading(key,text=tr(title));table.column(key,width=width,stretch=key in ('local','remote'))
            table.pack(fill='both',expand=True,padx=12)
            scroll=ttk.Scrollbar(table,orient='vertical',command=table.yview);table.configure(yscrollcommand=scroll.set)
            scroll.pack(side='right',fill='y')
            folder_preview=tk.Label(win,text='',bg='#202428',fg='#e9b965',anchor='w')
            folder_preview.pack(fill='x',padx=12,pady=(5,0))
            tk.Label(win,text=tr('选择行后可批量指定来源；双击行切换来源。下方可查看完整内容。'),bg='#202428',fg='#aeb6bc').pack(anchor='w',padx=12,pady=5)
            preview=tk.Text(win,height=7,wrap='word',bg='#30363c',fg='#e7e7e7',relief='flat',state='disabled')
            preview.pack(fill='x',padx=12)
            bottom=tk.Frame(win,bg='#202428');bottom.pack(fill='x',padx=12,pady=10)
            def close_dialog():
                if self.busy:self.status.set(tr('请等待冲突资料提交完成'))
                else:win.destroy()
            win.protocol('WM_DELETE_WINDOW',close_dialog)
            state={'remote':None,'rows':{},'choices':{}}
            def show_value(value):
                return json.dumps(value,ensure_ascii=False,indent=2) if isinstance(value,(dict,list)) else clean(value)
            def preview_selection(event=None):
                row=next(iter(table.selection()),None)
                if not row:return
                key,left,right=state['rows'][row]
                preview.configure(state='normal');preview.delete('1.0','end')
                preview.insert('end',tr('本地：')+'\n'+show_value(left)+'\n\n'+tr('远端：')+'\n'+show_value(right))
                preview.configure(state='disabled')
            table.bind('<<TreeviewSelect>>',preview_selection)
            def set_choice(choice):
                for row in table.selection():
                    if row in state['rows']:
                        key=state['rows'][row][0];state['choices'][key]=choice
                        table.set(row,'choice',tr('远端') if choice=='remote' else tr('本地'))
                show_target()
            def show_target():
                if not state['remote']:return
                try:
                    selected_album=merge(local,state['remote'],state['choices'])
                    destination=target_folder(folder,selected_album['metadata'])
                    folder_preview.configure(text=tr('提交后文件夹：')+str(destination),fg='#e9b965')
                except (ValueError,FileExistsError) as e:
                    folder_preview.configure(text=tr('文件夹名称需要调整：')+str(e),fg='#ef8172')
            def toggle(event):
                row=table.identify_row(event.y)
                if row and row in state['rows']:
                    table.selection_set(row)
                    set_choice('local' if state['choices'].get(state['rows'][row][0])=='remote' else 'remote')
            table.bind('<Double-1>',toggle)
            ttk.Button(bottom,text=tr('采用本地'),command=lambda:set_choice('local')).pack(side='left',padx=3)
            ttk.Button(bottom,text=tr('采用远端'),command=lambda:set_choice('remote')).pack(side='left',padx=3)
            submit=ttk.Button(bottom,text=tr('提交并统一两端'),state='disabled')
            submit.pack(side='right',padx=3)
            ttk.Button(bottom,text=tr('取消'),command=close_dialog).pack(side='right',padx=3)
            def loaded(record):
                if not win.winfo_exists():return
                if isinstance(record,Exception):
                    messagebox.showerror(tr('读取远端记录失败'),str(record),parent=win);return
                if not record:
                    messagebox.showwarning(tr('远端记录不存在'),tr('请选择其他远端记录。'),parent=win);return
                state['remote']=record;state['rows'].clear();state['choices'].clear()
                table.delete(*table.get_children())
                entries=[((kind,key),left,right,tr(key) if kind=='metadata' else tr('专辑评分') if kind=='rating' else tr('个人评论')) for kind,key,left,right in fields(local,record)]
                remote_marks={t['filename']:t for t in record.get('tracks',[])}
                for track in local.get('tracks',[]):
                    other=remote_marks.get(track['filename'])
                    if not other:continue
                    for field in ('selected','highlighted'):
                        if bool(track.get(field))!=bool(other.get(field)):
                            entries.append((('track',track['filename'],field),bool(track.get(field)),bool(other.get(field)),track['filename']+' · '+tr('入选' if field=='selected' else '重点')))
                for group,label in (('images','封面'),('documents','附件')):
                    existing={item['filename']:item for item in local.get(group,[])}
                    for item in record.get(group,[]):
                        own=existing.get(item['filename'])
                        if own and own['sha256']!=item['sha256']:
                            entries.append((('asset',group,item['filename']),own['sha256'],item['sha256'],tr(label)+' · '+item['filename']))
                for key,left,right,label in entries:
                    choice='remote' if left in ('',None,[]) and right not in ('',None,[]) else 'local'
                    state['choices'][key]=choice
                    row=table.insert('','end',values=(label,show_value(left)[:110],show_value(right)[:110],tr('远端') if choice=='remote' else tr('本地')))
                    state['rows'][row]=(key,left,right)
                show_target()
                submit.configure(state='normal')
            def select_record(event=None):
                submit.configure(state='disabled');state['remote']=None
                index=picker.current()
                if index<0:return
                identifier=candidates[index]['id']
                def fetch_record():
                    try:return remote.fetch({'id':identifier})
                    except Exception as e:return e
                self.submit(fetch_record,lambda record,chosen=index:loaded(record) if picker.current()==chosen else None)
            picker.bind('<<ComboboxSelected>>',select_record)
            if len(labels)==1:
                picker.current(0)
                select_record()
            def commit():
                record=state['remote']
                if not record:return
                try:
                    merged=merge(local,record,state['choices'])
                    target=target_folder(folder,merged['metadata'])
                except (ValueError,FileExistsError) as e:
                    messagebox.showerror(tr('无法提交'),str(e),parent=win);return
                submit.configure(state='disabled')
                self.busy=True;self.status.set(tr('正在取得远端独有的封面与附件…'))
                def fetch_assets():
                    try:
                        assets=[]
                        for group,kind in (('images','image'),('documents','document')):
                            existing={p['filename'] for p in local.get(group,[])}
                            limit=100 if kind=='image' else 10
                            if len(existing | {p['filename'] for p in record.get(group,[])})>limit:
                                raise ValueError(('封面图片' if kind=='image' else '附件')+'合并后超过服务器允许的 '+str(limit)+' 个，请先清理重复文件')
                            for item in record.get(group,[]):
                                name=item['filename']
                                replace=name in existing and state['choices'].get(('asset',group,name))=='remote'
                                if name not in existing or replace:
                                    assets.append((name,remote.download_asset(record['id'],item,kind),replace))
                        return assets
                    except Exception as e:return e
                def assets_ready(assets):
                    if isinstance(assets,Exception):
                        self.busy=False;submit.configure(state='normal')
                        messagebox.showerror(tr('获取远端附件失败'),str(assets),parent=win);return
                    created=[];replaced=[];renamed=False
                    info_path=folder/'album_info.json'
                    previous_info=read_json(info_path,{}) if info_path.exists() else None
                    try:
                        atomic_json(folder/'.cratelog-conflict-backup.json',local)
                        atomic_json(folder/'.cratelog-remote-backup.json',record)
                        if target!=folder and self.current_file and self.current_file.is_relative_to(folder):
                            self.stop()
                            if self.engine:
                                self.engine.close();self.engine=None
                        if target!=folder and self.folder==folder:
                            self.playlist=[];self.playlist_sources={};self.play_index=-1
                        if target!=folder:folder.rename(target);renamed=True
                        for name,content,replace in assets:
                            path=target/name
                            if replace:
                                if not path.is_file():raise FileNotFoundError('待替换附件不存在：'+str(path))
                                backup=target/'.cratelog-conflict-files'/uuid.uuid4().hex/name
                                backup.parent.mkdir(parents=True,exist_ok=True)
                                shutil.copy2(path,backup)
                                replaced.append((path,backup))
                            elif path.exists():raise FileExistsError('附件目标已存在：'+str(path))
                            else:created.append(path)
                            path.write_bytes(content)
                        merged['local_path']=str(target)
                        atomic_json(target/'album_info.json',merged['metadata'])
                        save_album(target,merged)
                    except Exception as e:
                        try:
                            for path in created:path.unlink(missing_ok=True)
                            for path,backup in replaced:shutil.copy2(backup,path)
                            if renamed:target.rename(folder)
                            if previous_info is None:(folder/'album_info.json').unlink(missing_ok=True)
                            else:atomic_json(folder/'album_info.json',previous_info)
                            save_album(folder,local)
                        except Exception as rollback_error:
                            e=RuntimeError(str(e)+'；回退目录失败：'+str(rollback_error))
                        self.busy=False;submit.configure(state='normal')
                        messagebox.showerror(tr('本地更新失败'),str(e),parent=win);return
                    self.status.set(tr('正在提交统一后的专辑资料…'))
                    self.submit(work,complete)
                def complete(result):
                    self.busy=False
                    if win.winfo_exists():win.destroy()
                    if self.folder==folder and target.exists():
                        self.folder=target
                        self.album=load_album(target);self.render()
                    self.refresh_root();self.reveal_folder(target)
                    if isinstance(result,Exception):
                        self.status.set(tr('远端提交失败；本地已保留合并资料和备份：')+str(result))
                        messagebox.showerror(tr('远端提交失败'),str(result),parent=self.root)
                        return
                    self.status.set(tr('两端资料已统一'))
                def work():
                    try:return remote.sync(target,match_folder=False)
                    except Exception as e:return e
                self.submit(fetch_assets,assets_ready)
            submit.configure(command=commit)
        def prepare():
            try:return find_records()
            except Exception as e:return e
        self.submit(prepare,found)

    def update_play_button(self):
        self.transport_buttons['play'].configure(image=self.transport_icons['pause' if self.current_file and not self.paused else 'play'])

    def toggle_turntable(self):
        if self.turntable_visible:
            self.turntable.hide();self.turntable.pack_forget()
            self.track_table.pack(fill='both',expand=True);self.turntable_visible=False
            self.view_button.configure(image=self.view_icons['turntable'])
            self.control('set_property','speed',1.)
            self.control('set_property','audio-pitch-correction',True)
            self.turntable.pitch=0.;self.turntable.rpm=100/3
            return
        if self.turntable is None:
            from cratelog_turntable import create_view
            self.turntable=create_view(self.track_area,self,self.turntable_error)
        self.track_table.pack_forget();self.turntable.pack(fill='both',expand=True)
        self.turntable_visible=True;self.view_button.configure(image=self.view_icons['list'])
        self.turntable.show()

    def turntable_error(self,error):
        if self.turntable_visible:self.toggle_turntable()
        if self.turntable:self.turntable.destroy();self.turntable=None
        self.status.set('唱机渲染失败：'+error)
        messagebox.showerror('Cratelog · 唱机',error,parent=self.root)

    def cycle_mode(self):
        modes=['顺序播放','列表循环','单曲循环']
        self.mode.set(modes[(modes.index(self.mode.get())+1)%len(modes)])

    def update_mode_button(self):
        self.mode_button.configure(image=self.transport_icons[{'顺序播放':'sequential','列表循环':'repeat','单曲循环':'repeat_one'}[self.mode.get()]])

    def update_track_tags(self, metadata):
        if not self.current_file:return
        tags={str(k).lower(): ' '.join(str(v).split()) for k,v in (metadata or {}).items() if v is not None} if isinstance(metadata,dict) else {}
        if self.lastfm_loaded:self.lastfm_tags=tags
        self.now.set(self.cue_title or tags.get('title') or self.current_file.name)
        self.tag_details=' · '.join(v for v in (tags.get('artist'),tags.get('album')) if v)
        self.update_track_details()

    def update_track_details(self):
        self.details.set('\n'.join((v for v in (self.tag_details, self.audio_details) if v)))

    def update_audio_details(self):
        params=getattr(self,'current_audio_params',{})
        info=getattr(self,'current_audio_info',{})
        bitrate=getattr(self,'current_bitrate',0) or info.get('bitrate',0)
        bits=info.get('bits',0)
        parts=['{0:,} bps'.format(round(bitrate)) if bitrate else '码率 —']
        if bits:parts.append('{0} bit'.format(bits))
        if params.get('samplerate'):parts.append('{0} Hz'.format(params['samplerate']))
        parts.extend(str(params[k]) for k in ('channels','format') if params.get(k))
        self.audio_details=' · '.join(parts);self.update_track_details()

    def ensure_engine(self):
        if self.engine and self.engine.process.poll() is None:return
        mpv_path=executable('mpv',self.mpv.get().strip())
        if not mpv_path:raise RuntimeError('未找到 mpv。macOS 请执行 brew install mpv；Windows 可放入 runtime/mpv/mpv.exe。')
        self.root.update_idletasks()
        self.engine=MPV(mpv_path,self.events, self.spectrum_host if sys.platform=='darwin' else self.spectrum_host.winfo_id(), self.settings.get('subtitle'))
        self.engine.command('set_property','volume',self.volume.get())

    def prepare_album_playlist(self, metadata):
        # Prepare the displayed album without changing the active playback queue.
        self.album_playlist=[self.folder/t['filename'] for t in self.album['tracks']]
        self.album_playlist_sources={str(self.folder/key):{**value,'_root':str(self.folder),'_album':metadata,'_audio':self.album.get('_durations',{}).get(key,{})} for key,value in self.album.get('_track_sources',{}).items()}

    def play_selected(self):
        if not self.album or not self.album['tracks']:return
        selection=self.tracks.selection()
        self.playlist=self.album_playlist
        self.playlist_sources=self.album_playlist_sources
        self.play_index=int(selection[0]) if selection else 0
        self.play()

    def play_or_resume(self):
        # Play resumes an existing pause. Double-click explicitly starts a track.
        if self.current_file and self.playback_state in {'playing', 'paused'}:
            self.set_paused(False)
        else:
            self.play_selected()

    def set_paused(self, paused):
        if not self.engine or self.playback_state == 'stopped': return
        if self.turntable_visible and self.turntable:
            if paused:self.turntable.cancel_audio()
            elif not self.turntable.needle_ready:
                self.turntable.defer_audio();paused=True
        self.paused = bool(paused)
        if self.lastfm_listening:self.lastfm_listening.previous=None
        self.pause_text.set('继续' if self.paused else '暂停')
        self.playback_state = 'paused' if self.paused else 'playing'
        self.control('set_property', 'pause', self.paused)

    def toggle_pause(self, event=None):
        if self.turntable_visible and self.turntable and self.turntable.resume_pending:
            self.set_paused(True)
        elif self.playback_state == 'stopped':
            self.play_selected()
        else:
            self.set_paused(not self.paused)
        return 'break'

    def highlight_playing(self, select=True):
        if not self.album: return
        for i, track in enumerate(self.album['tracks']):
            item = str(i)
            if not self.tracks.exists(item): continue
            playing = (self.current_track_id or self.current_file) == self.folder / track['filename']
            tags = [key for key in ('highlighted', 'selected') if track[key]]
            if playing: tags.append('playing')
            self.tracks.item(item, tags=tags)
            self.tracks.set(item, 'number', ('▶ ' if playing else '') + str(i+1))
            if playing and select:
                self.tracks.selection_set(item)
                self.tracks.focus(item)
                self.tracks.see(item)

    def open_subtitle_menu(self, event):
        self.show_subtitle_menu(event.x_root, event.y_root)
        return 'break'

    def show_subtitle_menu(self, x_root=None, y_root=None):
        if x_root is None or y_root is None:
            x_root, y_root = self.root.winfo_pointerx(), self.root.winfo_pointery()
        if self.subtitle_menu:
            self.subtitle_menu.destroy()
        menu = tk.Menu(self.root, tearoff=False, bg='#30363c', fg='#e7e7e7',
                       activebackground='#704a2c', activeforeground='white')
        self.subtitle_menu = menu
        paths = subtitle_candidates(self.current_file)
        if not paths:
            menu.add_command(label=tr('没有匹配的字幕'), state='disabled')
        else:
            if not hasattr(self, 'subtitle_choice'):
                self.subtitle_choice = tk.StringVar(self.root)
            self.subtitle_choice.set(self.shown_subtitle() or '')
            for path in paths:
                menu.add_radiobutton(label=path.name, value=_subtitle_key(path), variable=self.subtitle_choice,
                                      command=lambda chosen=path: self.select_subtitle(chosen))
        try: menu.tk_popup(x_root, y_root)
        finally: menu.grab_release()

    def shown_subtitle(self):
        if isinstance(self.subtitle_sid, int) and self.subtitle_sid > 0:
            for key, track_id in self.subtitle_ids.items():
                if track_id == self.subtitle_sid: return key
        return _subtitle_key(self.active_subtitle) if self.active_subtitle else ''

    def remember_subtitles(self, tracks):
        found = {}
        if isinstance(tracks, list):
            for track in tracks:
                if not isinstance(track, dict) or track.get('type') != 'sub': continue
                filename, track_id = track.get('external-filename'), track.get('id')
                if filename and track_id is not None: found[_subtitle_key(filename)] = track_id
        self.subtitle_ids = found

    def select_subtitle(self, path):
        if not self.engine or self.playback_state == 'stopped': return
        self.active_subtitle = Path(path)
        sid = self.subtitle_ids.get(_subtitle_key(path))
        if sid is not None: self.engine.command('set_property', 'sid', sid)
        else: self.engine.command('sub-add', str(path), 'select')

    def attach_preferred_subtitle(self):
        self.subtitle_ids = {}
        self.subtitle_sid = None
        path = preferred_subtitle(self.current_file)
        self.active_subtitle = path
        if path and self.engine: self.engine.command('sub-add', str(path), 'select')

    def clear_subtitle_choice(self):
        self.subtitle_ids = {}
        self.subtitle_sid = None
        self.active_subtitle = None

    def play(self,continuous=False):
        try:
            self.ensure_engine()
            identity=self.playlist[self.play_index]
            source=self.playlist_sources.get(str(identity),{})
            file=Path(source['_root'])/source['file'] if source else identity
            if not file.is_file():raise FileNotFoundError('播放文件已移动，请刷新目录：'+str(file))
            self.current_file = file
            if self.turntable:self.turntable.continuous_target=identity if continuous else None
            self.current_track_id=identity
            self.track_start=source.get('start',0)
            self.track_end=source.get('end')
            self.cue_title=source.get('title','')
            self.lastfm_listening=Listening() if self.lastfm.enabled() else None
            self.lastfm.begin()
            self.lastfm_loaded=False;self.lastfm_tags={};self.lastfm_source=source
            self.current_audio_info=source.get('_audio',{})
            self.current_audio_params={};            self.current_bitrate=0
            self.clear_subtitle_choice()
            self.paused = False
            self.pause_text.set('暂停')
            self.playback_state = 'playing'
            self.seek_pending = None
            self.position.set(0)
            self.seekbar.set(0, 0)
            self.clock.configure(text='00:00 / 00:00')
            options={'start':str(self.track_start)}
            if self.track_end is not None:options['end']=str(self.track_end)
            self.engine.command('script-message','cratelog-range',str(self.track_start),str(self.track_end if self.track_end is not None else -1))
            wait_for_arm=bool(self.turntable_visible and self.turntable and (not continuous or not self.turntable.needle_ready))
            if wait_for_arm:
                self.turntable.defer_audio()
                self.turntable.transition=time.monotonic();self.turntable.motion_lift=1.
                self.paused=True;self.playback_state='paused'
                self.pause_text.set(tr('继续'))
                options['pause']='yes'
                self.engine.command('set_property','pause',True)
            self.engine.command('loadfile',str(file),'replace',-1,options)
            self.engine.command('set_property','pause',wait_for_arm)
            if self.turntable_visible and self.turntable:self.turntable.pitch_control()
            self.tag_details='';self.audio_details=''
            self.now.set(self.cue_title or file.name); self.details.set(''); self.duration=0
            self.highlight_playing()
        except Exception as e:messagebox.showerror(tr('播放失败'),tr(str(e)),parent=self.root)

    def next(self,delta=1,continuous=False):
        if not self.playlist:return
        target=self.play_index+delta
        if self.mode.get()=='列表循环':target%=len(self.playlist)
        if 0<=target<len(self.playlist):
            keep_arm=continuous and delta==1 and target==self.play_index+1
            self.play_index=target;self.play(continuous=keep_arm)

    def control(self,*args):
        if self.engine:self.engine.command(*args)

    def stop(self):
        if self.turntable:self.turntable.cancel_audio()
        self.control('stop')
        self.reset_playback()

    def reset_playback(self):
        self.lastfm.begin()
        self.lastfm_listening=None;self.lastfm_loaded=False
        self.current_file = None
        self.clear_subtitle_choice()
        self.current_track_id=None
        self.track_start=0;self.track_end=None;self.cue_title=''
        self.paused = False
        self.pause_text.set('暂停')
        self.playback_state = 'stopped'
        self.seek_pending = None
        self.duration = 0
        self.position.set(0)
        self.seekbar.set(0,0)
        self.clock.configure(text='00:00 / 00:00')
        self.now.set(tr('CRATELOG / 已停止'))
        self.tag_details='';self.audio_details='';self.details.set('')
        self.highlight_playing(select=False)

    def seek(self, seconds):
        if not self.engine or not self.duration or self.playback_state == 'stopped': return
        seconds = max(0.0, min(self.duration, float(seconds)))
        if self.lastfm_listening:self.lastfm_listening.previous=None
        self.position.set(seconds)
        self.seek_pending = (seconds, time.monotonic() + 2)
        self.control('seek', seconds+self.track_start, 'absolute+exact')
        self.update_clock(seconds)

    def update_clock(self, seconds):
        self.clock.configure(text='{0:02}:{1:02} / {2:02}:{3:02}'.format(int(seconds) // 60, int(seconds) % 60, int(self.duration) // 60, int(self.duration) % 60))
        self.seekbar.set(seconds, self.duration)

    def copy_album_info(self):
        if not self.album:return
        metadata=self.display_metadata()
        clean=lambda key:' '.join(str(metadata.get(key) or '').split())
        artist,title,year=(clean(key) for key in ('音乐人','专辑名','出版年份'))
        text=' - '.join(value for value in (artist,title) if value)
        if not text and self.folder:text=self.folder.name
        if not text:return
        if year:text+='（{0}）'.format(year)
        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        self.status.set(tr('已复制：') + text)

    def search_douban(self):
        if not self.album:return
        metadata=self.display_metadata()
        query=' '.join(str(metadata.get(key,'')).strip() for key in ('音乐人','专辑名')).strip()
        if not query:query=self.folder.name
        webbrowser.open('https://search.douban.com/music/subject_search?'+urlencode({'search_text':query}))

    def show_album_menu(self):
        if not self.album or not self.folder:return
        lang=language
        folder=self.folder
        if getattr(self,'album_context_menu',None):self.album_context_menu.destroy()
        menu=tk.Menu(self.root,tearoff=False,bg='#30363c',fg='#e7e7e7',activebackground='#704a2c',activeforeground='white')
        self.album_context_menu=menu
        for method in ('view_details','single_search','manual_input','rename_folder','open_folder','play_folder'):
            if method=='open_folder':menu.add_separator()
            menu.add_command(label=lang.t(method),command=lambda name=method:self.run_organizer_action(name,folder))
        try:menu.tk_popup(self.album_menu_button.winfo_rootx(),self.album_menu_button.winfo_rooty()+self.album_menu_button.winfo_height())
        finally:menu.grab_release()

    def run_organizer_action(self, method, folder):
        if not self.organizer or not self.organizer.root.winfo_exists():
            from cratelog import CratelogOrganizer
            win=tk.Toplevel(self.root);win.withdraw()
            self.organizer=CratelogOrganizer(win,dialog_parent=self.root)
            self.organizer.cratelog_player=self
        if self.organizer.processing_thread and self.organizer.processing_thread.is_alive():
            self.status.set(tr('整理器正在批量处理，请等待完成后操作当前专辑'));return
        self.organizer.select_player_folder(folder)
        self.organizer.run_dialog_action(method,self.root)

    def open_organizer(self):
        if self.organizer and self.organizer.root.winfo_exists():
            self.organizer.dialog_parent=self.organizer.root
            self.organizer.root.deiconify();self.organizer.root.lift();return
        from cratelog import CratelogOrganizer
        win=tk.Toplevel(self.root); self.organizer=CratelogOrganizer(win)
        self.organizer.cratelog_player=self

    def lastfm_sample(self,position):
        listening=self.lastfm_listening
        if not listening or not self.lastfm_loaded or not self.lastfm.enabled():return
        listening.sample(position,time.monotonic(),self.paused)
        tags=self.lastfm_tags;source=self.lastfm_source;album=source.get('_album',{})
        cue='#track=' in source.get('id','')
        title=self.cue_title if cue else tags.get('title','')
        artist=source.get('performer') or tags.get('artist') or album.get('音乐人','')
        if not title or not artist:return
        track={'artist':artist,'track':title}
        album_title=source.get('album_title') or tags.get('album') or album.get('专辑名','')
        if album_title:track['album']=album_title
        if self.duration:track['duration']=round(self.duration)
        if not listening.now_sent:
            listening.now_sent=True;self.lastfm.now(dict(track))
        if listening.eligible(self.duration):
            self.lastfm.enqueue({**track,'timestamp':listening.timestamp});listening.sent=True

    def poll(self):
        try:
            while True:
                kind,data=self.events.get_nowait()
                try:
                    if kind=='done':future,callback=data; callback(future.result())
                    elif kind in {'error','status'}:self.status.set(tr(data))
                    elif kind=='mpv':
                        if not self.engine or data.get('_engine') != self.engine.event_id: continue
                        control_error=mpv_control_error(data)
                        if control_error:self.status.set(tr(control_error))
                        if data.get('event') == 'client-message' and (data.get('args') or [None])[0] == 'cratelog-subtitle-menu':
                            self.show_subtitle_menu()
                        elif data.get('event') == 'file-loaded':
                            self.lastfm_loaded=True
                            if self.playback_state != 'stopped': self.attach_preferred_subtitle()
                            # Observers may coalesce identical values across files.
                            # Explicit snapshots make equal-duration tracks seekable.
                            for prop in ('duration', 'time-pos', 'pause', 'metadata','audio-bitrate','audio-params'):
                                self.control('get_property', prop)
                        elif data.get('event')=='property-change':
                            name,value=data.get('name'),data.get('data')
                            if self.playback_state == 'stopped': continue
                            if name=='duration' and value:
                                self.duration=max(0,min(value,self.track_end if self.track_end is not None else value)-self.track_start); self.update_clock(self.position.get())
                            elif name=='time-pos' and value is not None and not self.seekbar.dragging:
                                value=max(0,value-self.track_start)
                                self.lastfm_sample(value)
                                if self.seek_pending:
                                    target, deadline = self.seek_pending
                                    if abs(value-target) > .5 and time.monotonic() < deadline: continue
                                    self.seek_pending = None
                                self.position.set(value); self.update_clock(value)
                            elif name=='pause' and value is not None:
                                if self.lastfm_listening and bool(value)!=self.paused:self.lastfm_listening.previous=None
                                self.paused=bool(value)
                                self.pause_text.set('继续' if self.paused else '暂停')
                                if self.playback_state != 'stopped':self.playback_state='paused' if self.paused else 'playing'
                            elif name=='seeking' and value:
                                if self.lastfm_listening:self.lastfm_listening.previous=None
                            elif name=='paused-for-cache' and value:
                                if self.lastfm_listening:self.lastfm_listening.previous=None
                                self.status.set(tr('正在预缓冲音频，请稍候…'))
                            elif name=='paused-for-cache' and value is False:
                                if self.status.get()==tr('正在预缓冲音频，请稍候…'):self.status.set(tr('音频缓冲就绪'))
                            elif name=='metadata':self.update_track_tags(value)
                            elif name=='audio-params' and value:
                                self.current_audio_params=value;self.update_audio_details()
                            elif name=='audio-bitrate' and value:
                                self.current_bitrate=value;self.update_audio_details()
                            elif name=='track-list': self.remember_subtitles(value)
                            elif name=='sid': self.subtitle_sid=value
                        elif data.get('event')=='end-file':
                            if self.playback_state == 'stopped': continue
                            if data.get('reason')=='eof':
                                if self.mode.get()=='单曲循环':self.play()
                                elif self.play_index + 1 < len(self.playlist) or self.mode.get()=='列表循环':self.next(continuous=True)
                                else:self.reset_playback()
                            elif data.get('reason')=='error':
                                self.reset_playback(); self.status.set(tr('解码失败：') + str(data.get('file_error', tr('未知错误'))))
                except Exception as e:self.busy=False; self.status.set(tr(str(e)))
        except queue.Empty:pass
        if time.monotonic()>=self.lastfm_flush_at:
            self.lastfm_flush_at=time.monotonic()+60;self.lastfm.flush()
        self.poll_job = self.root.after(100,self.poll)

    def close(self):
        if self.busy:
            messagebox.showinfo(tr('同步进行中'),tr('请等待当前同步结束再退出。'),parent=self.root); return
        try:self.save_workspace()
        except (OSError,tk.TclError) as e:
            messagebox.showerror(tr('保存窗口状态失败'),tr(str(e)),parent=self.root);return
        if self.turntable:self.turntable.close()
        if self.engine:self.engine.close()
        self.lastfm.close()
        self.root.after_cancel(self.poll_job)
        self.root.after_cancel(self.restore_job)
        self.pool.shutdown(wait=False,cancel_futures=True)
        self.root.destroy()


def main():
    root=tk.Tk(); Player(root); root.mainloop()


if __name__=='__main__':main()
