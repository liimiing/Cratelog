"""Platform paths and executable discovery without relying on terminal PATH."""
import os
import shutil
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parent
def load_tk():
    try:
        import tkinter
        return tkinter
    except ImportError as e:
        hint=f'brew install python-tk@{sys.version_info.major}.{sys.version_info.minor}' if sys.platform=='darwin' else '请安装与当前 Python 匹配的 Tcl/Tk（见 INSTALL.md）'
        raise SystemExit(f'Cratelog 缺少 Tk 图形组件：{e}\n{hint}\n或执行安装说明中的完整环境安装步骤。') from None
def state_dir():
    override=os.environ.get('CRATELOG_STATE_DIR')
    if override:path=Path(override).expanduser()
    elif sys.platform=='darwin':path=Path.home()/'Library'/'Application Support'/'Cratelog'
    elif os.name=='nt':path=Path(os.environ.get('APPDATA',str(Path.home()/'AppData/Roaming')))/'Cratelog'
    else:path=Path(os.environ.get('XDG_CONFIG_HOME',str(Path.home()/'.config')))/'cratelog'
    path.mkdir(parents=True,exist_ok=True,mode=0o700)
    return path

def executable(name,configured=''):
    candidates=[configured] if configured else []
    candidates += [str(ROOT/'runtime'/name/(name+('.exe' if os.name=='nt' else '')))]
    found=shutil.which(name)
    if found:candidates.append(found)
    if sys.platform=='darwin':candidates += ['/opt/homebrew/bin/'+name,'/usr/local/bin/'+name]
    for item in candidates:
        path=Path(item)
        if sys.platform!='win32' and path.suffix.lower()=='.exe':continue
        if path.is_file() and (os.name=='nt' or os.access(path,os.X_OK)):return str(path)
    return None

def ui_font():return 'Helvetica' if sys.platform=='darwin' else 'Microsoft YaHei UI'

class SocketStream:
    def __init__(self,client):self.client=client;self.reader=client.makefile('rb')
    def write(self,data):self.client.sendall(data)
    def readline(self):return self.reader.readline()
    def close(self):self.reader.close();self.client.close()
