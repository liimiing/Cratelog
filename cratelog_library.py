"""Portable album identities, verified sidecars and revision-checked synchronization."""
import copy
import hashlib
import json
import os
import re
import threading
import uuid
import io
import tempfile
from collections import OrderedDict
from PIL import Image, ImageOps
from pathlib import Path
from urllib.parse import urlparse

import requests
try:
    from mutagen import File as AudioMetadata
except ModuleNotFoundError:
    import sys
    sys.path.insert(0,str(Path(__file__).resolve().parent/'vendor'))
    from mutagen import File as AudioMetadata

AUDIO = {'.mp3', '.mpa', '.mp2', '.wav', '.flac', '.ape', '.ogg', '.opus', '.m4a', '.aac', '.aiff', '.aif', '.wma'}
LOCK = threading.RLock()
SCAN_CACHE = OrderedDict()
SESSION_IDS = {}
TRANSIENT_KEYS = {"_durations", "_track_sources", "_scan_warnings"}


def normalize_metadata(metadata):
    """Unify legacy catalog-number aliases without discarding conflicting values."""
    result=copy.deepcopy(metadata)
    if '厂牌编号' not in result:return result
    old=result['厂牌编号'];current=result.get('唱片编号')
    empty=lambda value:value is None or value==[] or isinstance(value,str) and not value.strip()
    if empty(current):
        if not empty(old):result['唱片编号']=old
        result.pop('厂牌编号',None)
    elif empty(old) or old==current or isinstance(old,str) and isinstance(current,str) and old.strip()==current.strip():
        result.pop('厂牌编号',None)
    return result


def read_json(path, default):
    return json.loads(path.read_text(encoding='utf-8-sig')) if path.exists() else copy.deepcopy(default)


def direct_json(path,data):
    """Portable JSON: local recovery copies, in-place write, then readback verification."""
    path=Path(path)
    encoded=json.dumps(data,ensure_ascii=False,indent=2,allow_nan=False).encode('utf-8')
    with LOCK:
        try:previous=path.read_bytes()
        except FileNotFoundError:previous=None
        if previous is not None and json.loads(previous.decode('utf-8-sig'))==data:return False
        backup=Path(tempfile.mkdtemp(prefix='cratelog-json-recovery-'))
        def recover_file(name,content):
            with (backup/name).open('xb') as stream:
                stream.write(content);stream.flush();os.fsync(stream.fileno())
        if previous is not None:recover_file('previous.json',previous)
        recover_file('pending.json',encoded)
        recover_file('target.txt',str(path.absolute()).encode('utf-8'))
        try:
            with path.open('r+b' if previous is not None else 'xb') as stream:
                if previous is not None:
                    if stream.read()!=previous:raise OSError('文件已被其他程序修改，已取消保存')
                    stream.seek(0)
                stream.write(encoded);stream.truncate();stream.flush();os.fsync(stream.fileno())
            if path.read_bytes()!=encoded:raise OSError('写入后校验不一致')
        except OSError as error:
            raise OSError(f'未确认保存到移动硬盘：{path}。恢复副本：{backup}。{error}') from error
        # Verified writes no longer need temporary recovery copies.
        try:
            for item in backup.iterdir():item.unlink()
            backup.rmdir()
        except OSError:
            pass  # The external copy has already been verified.
        return True


def atomic_json(path, data):
    path=Path(path)
    if path.name in ('.cratelog.json','album_info.json'):
        return direct_json(path,data)
    temporary = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    try:
        with temporary.open('w', encoding='utf-8') as stream:
            json.dump(data, stream, ensure_ascii=False, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def digest(data):
    data = copy.deepcopy(data)
    if isinstance(data, dict) and isinstance(data.get('rating'), (int, float)):
        if float(data['rating']).is_integer(): data['rating'] = int(data['rating'])
    return hashlib.sha256(json.dumps(data, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def sync_path(value):
    value=re.sub(r'^[A-Za-z]:','',str(value))
    return re.sub(r'^.*?/\.mounty(?=/|$)','',value)


def payload(album):
    data={k: v for k, v in album.items() if not k.startswith('_')}
    data['images']=[{**p,'sha256':album.get('_image_uploads',{}).get(p['filename'],{}).get(p['sha256'],p['sha256'])} for p in album.get('images',[]) if album.get('_skipped_images',{}).get(p['filename'])!=p['sha256']]
    data['documents']=[d for d in album.get('documents',[]) if album.get('_skipped_documents',{}).get(d['filename'])!=d['sha256']]
    if 'local_path' in data:data['local_path']=sync_path(data['local_path'])
    return data

def upload_image(file):
    data=file.read_bytes()
    if len(data)<=400*1024:return data
    with Image.open(io.BytesIO(data)) as source:
        fmt=source.format if source.format in ('JPEG','PNG','WEBP') else 'PNG'
        image=ImageOps.exif_transpose(source).copy()
    if fmt=='JPEG':image=image.convert('RGB')
    while True:
        width,height=image.size
        image=image.resize((max(1,round(width*.85)),max(1,round(height*.85))),Image.Resampling.LANCZOS)
        output=io.BytesIO();image.save(output,format=fmt,**({'quality':80} if fmt in ('JPEG','WEBP') else {'optimize':True}))
        data=output.getvalue()
        if len(data)<400*1024:return data
        if image.size==(1,1):raise ValueError('无法将图片缩小到 400 KB 以下：'+file.name)


UPLOAD_BUDGET=20_000_000-64*1024  # Allow framing/revision changes under either 20 MB convention.

def fit_upload(album,data,files):
    """Drop trailing upload images only; count multipart headers and UTF-8 metadata too."""
    removed=[]
    while True:
        data['album']=json.dumps(payload(album),ensure_ascii=False)
        total=0;empty=[]
        for key,(name,stream,mime) in files:
            position=stream.tell();stream.seek(0,2);total+=stream.tell();stream.seek(position)
            empty.append((key,(name,b'',mime)))
        body=requests.Request('POST','http://localhost/',data=data,files=empty or None).prepare().body or b''
        total+=len(body.encode('utf-8') if isinstance(body,str) else body)
        if total<=UPLOAD_BUDGET:return removed
        if not album['images']:
            raise ValueError('文档及专辑资料本身已超过 20 MB，移除全部上传图片仍无法提交；请减少文档后重试。')
        picture=album['images'].pop();removed.append(picture['filename'])
        for i,(key,(name,stream,mime)) in enumerate(files):
            if key=='images[]' and name==picture['filename']:
                stream.close();files.pop(i);break


def load_album(folder, recursive=None):
    folder = Path(folder).resolve()
    with LOCK:
        path = folder / '.cratelog.json'
        album = read_json(path, {'id': SESSION_IDS.setdefault(str(folder),str(uuid.uuid4())), 'rating': 0, 'tracks': [], '_revision': 0})
        cached=SCAN_CACHE.get(str(folder),{})
        if cached.get('id')==album['id']:album['_durations']=copy.deepcopy(cached.get('_durations',{}))
        album.setdefault('personal_comment', '')
        album['local_path'] = str(folder)
        album['metadata'] = normalize_metadata(read_json(folder / 'album_info.json', album.get('metadata', {})))
        from cratelog_tracks import scan_tracks, natural_key
        if recursive is not None:album['_recursive']=bool(recursive)
        elif (folder / 'album_info.json').is_file():album['_recursive']=True
        tracks,durations,sources,marks,warnings=scan_tracks(folder,album,AUDIO,AudioMetadata,album.get('_recursive',False))
        album['tracks']=tracks
        album['_durations']=durations
        album['_track_sources']=sources
        album['_track_marks']=marks
        album['_scan_warnings']=warnings
        pictures = sorted(p for p in folder.iterdir() if not p.name.startswith('.') and p.is_file() and p.suffix.lower() in {'.jpg', '.jpeg', '.png', '.webp', '.gif'})
        pictures.sort(key=lambda p: (p.stem.lower() not in {'cover', 'folder', 'front'}, natural_key(p)))
        album['images'] = [{'filename': p.name, 'sha256': hashlib.sha256(p.read_bytes()).hexdigest()} for p in pictures]
        documents = sorted(p for p in folder.iterdir() if not p.name.startswith('.') and p.is_file() and p.suffix.lower() in {'.md', '.txt', '.doc', '.docx', '.pdf', '.rtf', '.htm', '.html', '.mht', '.mhtml'})
        album['documents'] = [{'filename': p.name, 'sha256': hashlib.sha256(p.read_bytes()).hexdigest()} for p in documents]
        SCAN_CACHE[str(folder)]={'id':album['id'],'_durations':copy.deepcopy(durations)}
        SCAN_CACHE.move_to_end(str(folder))
        while len(SCAN_CACHE)>128:SCAN_CACHE.popitem(last=False)
        return album


def save_album(folder, album):
    with LOCK:
        stored={key:value for key,value in album.items() if key not in TRANSIENT_KEYS}
        marks=dict(stored.get('_track_marks',{}))
        marks.update({track['filename']:{key:bool(track.get(key)) for key in ('selected','highlighted')} for track in stored.get('tracks',[])})
        stored['_track_marks']=marks
        atomic_json(Path(folder) / '.cratelog.json', stored)


class Conflict(Exception):
    pass


def parse_album_folder(folder):
    name=Path(folder).name
    dated=re.match(r'^(.+?)\s+-\s*(\d{4})\s*-\s*(.+)$',name)
    if dated:
        return {'音乐人':dated[1].strip(),'出版年份':dated[2],'专辑名':dated[3].strip()}
    undated=re.match(r'^(.+?)\s+-{1,2}\s+(.+)$',name)
    if undated:
        return {'音乐人':undated[1].strip(),'专辑名':undated[2].strip()}
    return {}


class CatalogIndex:
    """Small remote presence index; never loads or rewrites local albums."""
    def __init__(self, records=()):
        records=list(records)
        self.records=records
        self.ids={r['id'] for r in records}
        self.paths={self.path_key(r['path']) for r in records if r.get('path')}
        self.names={(self.normal(r.get('artist','')),self.normal(r.get('album',''))) for r in records if r.get('artist') and r.get('album')}
        self.filename_names={(self.filename_key(a),self.filename_key(t)) for a,t in self.names}

    @staticmethod
    def normal(value):return ' '.join(str(value).split()).casefold()

    @classmethod
    def filename_key(cls,value):return cls.normal(re.sub(r'[_<>:"/\\|?*＜＞：＂／＼｜？＊]+',' ',str(value)))

    def has_name(self,artist,title):
        exact=(self.normal(artist),self.normal(title))
        safe=(self.filename_key(artist),self.filename_key(title))
        return exact in self.names or (all(safe) and safe in self.filename_names)

    def lookup(self,folder,album=None):
        album=album or {}
        matches=[r for r in self.records if r['id']==album.get('id')]
        if not matches:matches=[r for r in self.records if r.get('path') and self.path_key(r['path'])==self.path_key(folder)]
        if matches:return matches[0] if len(matches)==1 else None
        m=album.get('metadata',{})
        parsed=parse_album_folder(folder)
        candidates=[(m.get('音乐人',''),m.get('专辑名',''),m.get('出版年份',''))]
        if parsed:candidates.append((parsed['音乐人'],parsed['专辑名'],parsed.get('出版年份','')))
        for artist,title,year in candidates:
            if not self.filename_key(artist) or not self.filename_key(title):continue
            for key in (self.normal,self.filename_key):
                matches=[r for r in self.records if key(r.get('artist',''))==key(artist) and key(r.get('album',''))==key(title)]
                if not matches:continue
                if len(matches)>1:matches=[r for r in matches if str(r.get('year','')).strip()==str(year).strip()]
                return matches[0] if len(matches)==1 else None
        return None

    @classmethod
    def path_key(cls,value):return cls.normal(sync_path(value).replace('\\','/')).rstrip('/')

    def contains(self, folder, album=None):
        if self.path_key(folder) in self.paths:return True
        if album is None:
            try:album=read_json(Path(folder)/'.cratelog.json',{})
            except (OSError,ValueError):album={}
        if album and album.get('id') in self.ids:return True
        match=parse_album_folder(folder)
        if match and self.has_name(match['音乐人'],match['专辑名']):return True
        if album:
            m=album.get('metadata',{})
            return self.has_name(m.get('音乐人',''),m.get('专辑名',''))
        return False


class Remote:
    def __init__(self, url, token):
        token = token.strip()
        parsed = urlparse(url)
        if parsed.scheme != 'https' and not (parsed.scheme == 'http' and parsed.hostname in {'localhost', '127.0.0.1', '::1'}):
            raise ValueError('同步地址必须使用 HTTPS（本机调试除外）')
        if not token:
            raise ValueError('请配置同步令牌')
        self.url, self.token = url, token

    def request(self, method, **kwargs):
        response = requests.request(method, self.url, headers={'Authorization': 'Bearer ' + self.token, 'X-Cratelog-Token': self.token}, timeout=(10, 90), allow_redirects=False, **kwargs)
        if response.status_code == 401:
            try:
                code = response.json().get('code', '')
            except (ValueError, AttributeError):
                code = ''
            messages = {
                'auth_not_configured': '同步接口未读到有效的服务端令牌，请检查 cratelog_config.php 和环境变量配置。',
                'auth_header_missing': '服务器未收到认证请求头，请更新客户端及 cratelog_api.php，或检查服务器请求头转发。',
                'auth_token_mismatch': '客户端令牌与同步接口使用的令牌不一致；服务端环境变量优先于配置文件。',
            }
            raise ValueError(messages.get(code, '同步认证失败（401）：请核对客户端令牌，并更新服务端 cratelog_api.php 以获取具体原因。'))
        if response.status_code == 409:
            try:
                if response.json().get('code') == 'ambiguous_match':
                    raise Conflict('服务端有多个同名专辑，年份也无法区分；请先在网页核对重复记录。')
            except (ValueError, AttributeError):
                pass
            raise Conflict('远端版本已更新。本地资料未覆盖；请先处理冲突。')
        if response.status_code in (413,422):
            try:detail=response.json().get('error','上传数据被拒绝')
            except (ValueError,AttributeError):detail='请求过大或上传数据被服务器拒绝，请检查 PHP 上传限制'
            raise ValueError(f'同步失败（{response.status_code}）：{detail}')
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, dict):
            raise ValueError('服务端返回格式不正确')
        return data

    def fetch(self, album):
        return self.request('GET', params={'id': album['id']}).get('album')

    def download_asset(self, album_id, item, kind):
        """Fetch a remote-only attachment for local reconciliation."""
        name=item['filename'];sha=item['sha256']
        if name in ('','.','..') or Path(name).name!=name or name.startswith('.') or re.search(r'[<>:"/\\|?*\x00-\x1f]',name) or not re.fullmatch(r'[a-f0-9]{64}',sha):
            raise ValueError('远端附件名称或校验码无效')
        page=self.url.rsplit('/',1)[0]+'/cratelog.php'
        params={'image':sha} if kind=='image' else {'album':album_id,'document':sha}
        maximum=10*1024*1024 if kind=='image' else 5*1024*1024
        with requests.get(page,params=params,timeout=(10,90),stream=True,allow_redirects=False) as response:
            response.raise_for_status()
            content=bytearray()
            for chunk in response.iter_content(65536):
                content.extend(chunk)
                if len(content)>maximum:raise ValueError('远端附件超过本地同步限制：'+name)
        if hashlib.sha256(content).hexdigest()!=sha:
            raise ValueError('远端附件校验失败：'+name)
        return bytes(content)

    def catalog(self):
        result=self.request('GET',params={'catalog':'1'})
        if not isinstance(result.get('catalog'),list):raise ValueError('请更新服务端 cratelog_api.php，以支持目录批量查询')
        return CatalogIndex(result['catalog'])

    def sync(self, folder, match_folder=True):
        # Network work uses a snapshot. A local edit during upload stays dirty.
        album = load_album(folder)
        snapshot = copy.deepcopy(album)
        match = parse_album_folder(folder)
        if match and match_folder:
            # Folder names identify candidates, but must not replace saved Discogs data.
            differences=[key for key,value in match.items()
                         if str(album['metadata'].get(key) or '').strip()
                         and str(album['metadata'][key]).strip().casefold()!=str(value).strip().casefold()]
            if differences:
                from cratelog_conflict import catalog_candidates
                catalog=self.catalog()
                if album['id'] in catalog.ids or catalog_candidates(catalog,folder,album):
                    raise Conflict('文件夹名称与本地 album_info.json 的'+ '、'.join(differences)+'不同；请在冲突面板确认，尚未上传或覆盖专辑资料。')
            for key,value in match.items():
                if not str(album['metadata'].get(key) or '').strip():
                    album['metadata'][key]=value
        if match or any(Path(d['filename']).suffix.lower() != '.md' for d in album['documents']):
            if self.request('GET', params={'capabilities': '1'}).get('schema_version', 1) < 3:
                raise ValueError('请先更新服务端 cratelog_api.php、cratelog_match.php，才能使用专辑匹配与多格式附件同步。此次尚未上传。')
        if any('/' in t['filename'] or '#track=' in t['filename'] for t in album['tracks']):
            if self.request('GET',params={'capabilities':'1'}).get('schema_version',1)<4:
                raise ValueError('请更新服务端 cratelog_api.php，才能同步多碟目录与 CUE 分轨标记。此次尚未上传。')
        if not match_folder and self.request('GET',params={'capabilities':'1'}).get('schema_version',1)<5:
            raise ValueError('请先更新服务端 cratelog_api.php，以保留冲突合并时的远端附件。此次尚未上传。')
        if len(album['images'])>100:raise ValueError('每张专辑最多同步 100 张图片')
        files = []
        image_uploads={};skipped={};skipped_images={}
        album['_skipped_images']={}
        try:
            for picture in album['images']:
                file = Path(folder) / picture['filename']
                content=upload_image(file);uploaded_hash=hashlib.sha256(content).hexdigest()
                image_uploads[file.name]={picture['sha256']:uploaded_hash}
                picture['sha256']=uploaded_hash
                files.append(('images[]', (file.name, io.BytesIO(content), 'application/octet-stream')))
            upload_documents=[]
            for document in album['documents']:
                if (Path(folder)/document['filename']).stat().st_size>5*1024*1024:
                    skipped[document['filename']]=document['sha256']
                else:upload_documents.append(document)
            album['documents']=upload_documents
            album['_skipped_documents']={}
            if len(album['documents']) > 10: raise ValueError('每张专辑最多同步 10 个可上传附件')
            for document in album['documents']:
                file = Path(folder) / document['filename']
                files.append(('documents[]', (file.name, file.open('rb'), 'application/octet-stream')))
            data={'album':json.dumps(payload(album),ensure_ascii=False),'revision':album['_revision'],'match_folder':'1' if match and match_folder else '0',
                  'reconcile':'0' if match_folder else '1'}
            removed=fit_upload(album,data,files)
            skipped_images={p['filename']:p['sha256'] for p in snapshot['images'] if p['filename'] in removed}
            try:
                result=self.request('POST',data=data,files=files or None)
            except Conflict:
                latest=self.fetch(album)
                if not latest or latest['id']!=album['id'] or not snapshot.get('_synced'):
                    raise
                # The sort number belongs to the server. Restore only that field
                # in a comparison copy, then verify every other remote field.
                comparison=copy.deepcopy(latest)
                old_metadata=snapshot.get('metadata',{})
                if '编号' in old_metadata:
                    comparison['metadata']['编号']=old_metadata['编号']
                else:
                    comparison['metadata'].pop('编号',None)
                if digest(payload(latest))!=snapshot['_synced'] and digest(payload(comparison))!=snapshot['_synced']:
                    raise
                if '编号' in latest['metadata']:
                    album['metadata']['编号']=latest['metadata']['编号']
                else:
                    album['metadata'].pop('编号',None)
                data['album']=json.dumps(payload(album),ensure_ascii=False)
                data['revision']=latest['_revision']
                for _,(_,stream,_) in files:stream.seek(0)
                result=self.request('POST',data=data,files=files or None)
            if result.get('schema_version', 1) < 2:
                raise ValueError('服务器尚未升级评价与文档同步接口，请更新 PHP 文件并执行数据库迁移后重试')
            if album['documents']:
                saved=result.get('album')
                if not isinstance(saved,dict):saved=self.fetch(album)
                confirmed={(d.get('filename'),d.get('sha256')) for d in (saved or {}).get('documents',[])}
                missing=[d['filename'] for d in album['documents'] if (d['filename'],d['sha256']) not in confirmed]
                if missing:
                    raise ValueError('服务端未确认保存以下附件：'+', '.join(missing)+'。请核对部署的 cratelog_api.php、cratelog_common.php、cratelog_documents.php；此次不标记为同步完成。')
                result['confirmed_documents']=[d['filename'] for d in album['documents']]
        finally:
            for _, (_, stream, _) in files:
                stream.close()
        with LOCK:
            current = load_album(folder)
            current['_revision'] = result['revision']
            current['_image_uploads']=image_uploads
            current['_skipped_documents']=skipped
            current['_skipped_images']=skipped_images
            merged = result.get('album')
            if merged:
                current['id'] = merged['id']
                for key in ('metadata', 'rating', 'personal_comment', 'tracks'):
                    if current.get(key) == snapshot.get(key):
                        current[key] = merged[key]
                if '编号' in merged['metadata']:
                    current['metadata']['编号']=merged['metadata']['编号']
                atomic_json(Path(folder) / 'album_info.json', current['metadata'])
            current['_synced'] = digest(payload(merged or album))
            save_album(folder, current)
        result['skipped_files']=[name+'（文档超过 5 MB）' for name in skipped]+[name+'（为满足 20 MB 上传上限）' for name in skipped_images]
        return result

    def pull(self, folder, remote, force=False):
        with LOCK:
            local = load_album(folder)
            if not force and local.get('_synced') != digest(payload(local)):
                raise Conflict('本地有未同步修改；远端资料未覆盖本地。')
            atomic_json(Path(folder) / '.cratelog-conflict-backup.json', local)
            for key in ('rating', 'metadata'):
                local[key] = remote[key]
            local['personal_comment'] = remote.get('personal_comment', '')
            flags = {t['filename']: t for t in remote['tracks']}
            for track in local['tracks']:
                if track['filename'] in flags:
                    for key in ('selected', 'highlighted'):
                        track[key] = flags[track['filename']][key]
            local['_revision'] = remote['_revision']
            atomic_json(Path(folder) / 'album_info.json', local['metadata'])
            # Local-only files/path changes still need a subsequent upload.
            local['_synced'] = digest(payload(remote))
            save_album(folder, local)
            return local
