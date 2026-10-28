"""Last.fm desktop auth, durable scrobbles, and seek-safe listening accounting."""
import hashlib
import json
import sqlite3
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from urllib.parse import urlencode
import requests
import os
import base64


def credential(value,decode=False):
    """Protect local secrets using the current Windows account's DPAPI."""
    if not value:return ''
    if os.name!='nt':
        if decode and value.startswith('dpapi:'):raise OSError('Windows 加密凭据不能用于 macOS，请重新授权 Last.fm')
        return value
    import ctypes
    from ctypes import wintypes
    class Blob(ctypes.Structure):_fields_=[('size',wintypes.DWORD),('data',ctypes.POINTER(ctypes.c_char))]
    if decode and not value.startswith('dpapi:'):return value
    raw=base64.b64decode(value[6:]) if decode else value.encode('utf-8')
    buf=ctypes.create_string_buffer(raw);source=Blob(len(raw),ctypes.cast(buf,ctypes.POINTER(ctypes.c_char)));target=Blob()
    dll=ctypes.WinDLL('crypt32',use_last_error=True)
    fn=dll.CryptUnprotectData if decode else dll.CryptProtectData
    fn.argtypes=[ctypes.POINTER(Blob),ctypes.c_void_p,ctypes.c_void_p,ctypes.c_void_p,ctypes.c_void_p,wintypes.DWORD,ctypes.POINTER(Blob)]
    fn.restype=wintypes.BOOL
    if not fn(ctypes.byref(source),None,None,None,None,1,ctypes.byref(target)):raise OSError('无法读取或保护 Last.fm 凭据，请在当前 Windows 账户重新授权')
    try:
        result=ctypes.string_at(target.data,target.size)
        return result.decode('utf-8') if decode else 'dpapi:'+base64.b64encode(result).decode('ascii')
    finally:
        free=ctypes.WinDLL('kernel32').LocalFree;free.argtypes=[ctypes.c_void_p];free.restype=ctypes.c_void_p;free(target.data)


def stored_config(config,decode=False):
    result=dict(config)
    for key in ('secret','session'):result[key]=credential(result.get(key,''),decode)
    return result


class LastfmError(Exception):
    def __init__(self,message,code=0):super().__init__(message);self.code=code


class LastfmAPI:
    def __init__(self,key,secret,session=''):
        self.key,self.secret,self.session=key.strip(),secret.strip(),session
    def call(self,method,**params):
        if not self.key or not self.secret:raise LastfmError('请填写 Last.fm API Key 和 Shared Secret')
        params.update(method=method,api_key=self.key)
        if self.session:params['sk']=self.session
        params={k:str(v) for k,v in params.items()}
        signed=''.join(k+params[k] for k in sorted(params))+self.secret
        params['api_sig']=hashlib.md5(signed.encode('utf-8')).hexdigest()
        params['format']='json'
        try:
            response=requests.post('https://ws.audioscrobbler.com/2.0/',data=params,timeout=(5,15),allow_redirects=False)
            data=response.json()
        except (requests.RequestException,ValueError):raise LastfmError('Last.fm 网络连接失败，待提交记录已保留') from None
        if data.get('error'):
            code=int(data['error'])
            hints={9:'授权失效，请重新授权',14:'尚未在浏览器中允许授权',15:'授权令牌过期，请重新开始',10:'API Key 无效',13:'签名无效，请核对 Shared Secret',26:'API Key 被暂停',29:'请求过于频繁，稍后重试'}
            raise LastfmError('Last.fm：'+hints.get(code,str(data.get('message','请求失败'))),code)
        if response.status_code!=200:raise LastfmError('Last.fm 服务暂不可用')
        return data
    def authorize_url(self,token):return 'https://www.last.fm/api/auth/?'+urlencode({'api_key':self.key,'token':token})


class Listening:
    def __init__(self):
        self.timestamp=int(time.time());self.listened=0;self.previous=None;self.sent=False;self.now_sent=False
    def sample(self,position,clock,paused=False):
        if self.previous is not None and not paused:
            old,when=self.previous;delta=position-old;elapsed=clock-when
            # IPC notifications arrive in batches. Their processing intervals
            # are not listening time; count continuous media progress instead.
            if 0<delta<=elapsed+0.75 and 0<=elapsed<5:self.listened+=delta
        self.previous=None if paused else (position,clock)
    def eligible(self,duration):return not self.sent and duration>30 and self.listened>=min(duration/2,240)


class LastfmService:
    def __init__(self,path,notify):
        self.path=path;self.notify=notify;self.config={};self.lock=threading.Lock();self.running=False;self.blocked=False;self.generation=0
        self.pool=ThreadPoolExecutor(max_workers=1,thread_name_prefix='lastfm')
        with self.db() as db:db.execute('CREATE TABLE IF NOT EXISTS pending(id INTEGER PRIMARY KEY,username TEXT,api_key TEXT,payload TEXT,error TEXT DEFAULT NULL)')
    @contextmanager
    def db(self):
        db=sqlite3.connect(self.path,timeout=10)
        try:
            with db:yield db
        finally:db.close()
    def configure(self,config):self.config=dict(config);self.blocked=False
    def begin(self):self.generation+=1
    def enabled(self):return bool(self.config.get('enabled') and self.config.get('session') and self.config.get('username'))
    def api(self):return LastfmAPI(self.config['key'],self.config['secret'],self.config['session'])
    def now(self,track):
        config=dict(self.config)
        generation=self.generation
        def work():
            if not self.enabled() or self.config!=config or generation!=self.generation:return
            try:
                result=self.api().call('track.updateNowPlaying',**track)
                ignored=result.get('nowplaying',{}).get('ignoredMessage',{})
                if str(ignored.get('code','0'))!='0':self.notify('Last.fm 未接受正在播放信息')
            except LastfmError as e:self.notify(str(e))
        self.pool.submit(work)
    def enqueue(self,track):
        if not self.enabled():return
        with self.db() as db:db.execute('INSERT INTO pending(username,api_key,payload) VALUES(?,?,?)',(self.config['username'],self.config['key'],json.dumps(track,ensure_ascii=False)))
        self.flush()
    def flush(self):
        if not self.enabled() or self.blocked:return
        with self.lock:
            if self.running:return
            self.running=True
        def work():
            try:
                config=dict(self.config)
                with self.db() as db:rows=db.execute('SELECT id,payload FROM pending WHERE username=? AND api_key=? AND error IS NULL ORDER BY id LIMIT 50',(config['username'],config['key'])).fetchall()
                for identity,raw in rows:
                    if not self.enabled() or self.config!=config:return
                    try:
                        result=self.api().call('track.scrobble',**json.loads(raw))
                        if 'scrobbles' not in result:raise LastfmError('Last.fm 返回格式异常')
                        ignored=result['scrobbles'].get('scrobble',{}).get('ignoredMessage',{})
                        if str(ignored.get('code','0'))!='0':
                            with self.db() as db:db.execute('UPDATE pending SET error=? WHERE id=?',('Last.fm ignored: '+str(ignored.get('code')),identity))
                            self.notify('Last.fm 未录入该曲目（过滤代码 '+str(ignored.get('code'))+'）');continue
                    except LastfmError as e:
                        self.notify(str(e))
                        if e.code==9:self.blocked=True
                        if e.code in (0,9,11,16,29):return
                        with self.db() as db:db.execute('UPDATE pending SET error=? WHERE id=?',(str(e),identity))
                        return
                    with self.db() as db:db.execute('DELETE FROM pending WHERE id=?',(identity,))
                    self.notify('Last.fm 播放记录已提交')
            finally:
                with self.lock:self.running=False
        self.pool.submit(work)
    def close(self):self.pool.shutdown(wait=False,cancel_futures=True)
