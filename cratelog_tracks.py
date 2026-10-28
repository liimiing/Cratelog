"""Local audio scanning and single-file CUE tracks. IDs are album-relative."""
import math
import re
from pathlib import Path


def natural_key(path):
    return [(1,int(s)) if s.isdigit() else (0,s.casefold()) for s in re.split(r'(\d+)',path.name)]


def parse_cue(cue,root):
    raw=cue.read_bytes()
    for encoding in ('utf-8-sig','utf-16' if raw[:2] in (b'\xff\xfe',b'\xfe\xff') else 'gb18030','cp1252'):
        try:text=raw.decode(encoding);break
        except UnicodeError:continue
    else:return []
    files=[];tracks=[];current=None;performer='';album_title=''
    for line in text.splitlines():
        line=line.strip()
        match=re.match(r'FILE\s+(?:"([^"]+)"|(\S+))\s+\S+\s*$',line,re.I)
        if match:files.append(match[1] or match[2]);continue
        match=re.match(r'TRACK\s+(\d+)\s+(\S+)',line,re.I)
        if match:
            if match[2].upper()!='AUDIO':return []
            current={'number':int(match[1])};tracks.append(current);continue
        match=re.match(r'PERFORMER\s+"?(.*?)"?$',line,re.I)
        if match:
            if current is None:performer=match[1]
            else:current['performer']=match[1]
        if current is None:
            match=re.match(r'TITLE\s+"?(.*?)"?$',line,re.I)
            if match:album_title=match[1]
            continue
        match=re.match(r'TITLE\s+"?(.*?)"?$',line,re.I)
        if match:current['title']=match[1]
        match=re.match(r'INDEX\s+01\s+(\d+):(\d{2}):(\d{2})\s*$',line,re.I)
        if match:
            minutes,seconds,frames=map(int,match.groups())
            if seconds>=60 or frames>=75 or 'start' in current:return []
            current['start']=minutes*60+seconds+frames/75
    if len(files)!=1 or not tracks or any('start' not in t for t in tracks):return []
    reference=files[0].replace('\\','/')
    if re.match(r'^(?:/|[A-Za-z]:)',reference):return []
    source=(cue.parent/reference).resolve()
    if not source.is_relative_to(root) or not source.is_file():return []
    if any(part.startswith('.') for part in source.relative_to(root).parts):return []
    if len({t['number'] for t in tracks})!=len(tracks):return []
    if any(a['start']>=b['start'] for a,b in zip(tracks,tracks[1:])):return []
    for i,track in enumerate(tracks):
        track.setdefault('performer',performer);track['album_title']=album_title
        track.update(file=source.relative_to(root).as_posix(),end=tracks[i+1]['start'] if i+1<len(tracks) else None)
        track['id']=cue.relative_to(root).as_posix()+f"#track={track['number']:02}"
    return tracks


def read_audio_info(file,reader):
    stat=file.stat()
    title='';artist='';bitrate=0;bits=0
    try:
        audio=reader(file)
        # Mutagen objects without tags are falsey, even when audio.info is valid.
        seconds=float(audio.info.length) if audio is not None else None
        if audio is not None:
            bitrate=getattr(audio.info,'bitrate',0) or 0
            bits=getattr(audio.info,'bits_per_sample',0) or 0
            tags=audio.tags
            if tags is not None:
                value=tags.get('TIT2') or tags.get('title') or tags.get('\xa9nam')
                if isinstance(value,(list,tuple)):value=value[0] if value else ''
                title=' '.join(str(value or '').split())
                value=tags.get('TPE1') or tags.get('artist') or tags.get('\xa9ART')
                if isinstance(value,(list,tuple)):value='; '.join(str(v) for v in value)
                artist=' '.join(str(value or '').split())
        if seconds is not None and (not math.isfinite(seconds) or seconds<=0):seconds=None
    except Exception:seconds=None
    return {'reader':4,'size':stat.st_size,'mtime':stat.st_mtime_ns,'seconds':seconds,'title':title,'artist':artist,'bitrate':bitrate,'bits':bits}


def scan_tracks(root,album,audio_extensions,reader,recursive=False):
    files=[]
    def visit(directory):
        entries=sorted((p for p in directory.iterdir() if not p.name.startswith('.')),key=natural_key)
        files.extend(p for p in entries if p.is_file() and not p.is_symlink())
        if recursive:
            for p in entries:
                if p.is_dir() and not p.is_symlink() and not getattr(p,'is_junction',lambda:False)():visit(p)
    visit(root)
    durations={};sources={};tracks=[];warnings=[]
    marks=dict(album.get('_track_marks',{}))
    marks.update({t['filename']:{k:bool(t.get(k)) for k in ('selected','highlighted')} for t in album['tracks']})
    def duration(file):
        name=file.relative_to(root).as_posix()
        if name in durations:return durations[name]['seconds']
        stat=file.stat();cached=album.get('_durations',{}).get(name,{})
        if cached.get('reader')==4 and cached.get('seconds') is not None and cached.get('size')==stat.st_size and cached.get('mtime')==stat.st_mtime_ns:
            durations[name]=cached;return cached['seconds']
        durations[name]=read_audio_info(file,reader)
        seconds=durations[name]['seconds']
        return seconds
    cue_sources={}
    for cue in files:
        if cue.suffix.lower()!='.cue':continue
        try:parts=parse_cue(cue,root)
        except (OSError,ValueError):parts=[]
        if not parts or Path(parts[0]['file']).suffix.lower() not in audio_extensions:
            warnings.append('未采用 CUE（需引用一个存在的音频且索引有效）：'+cue.name);continue
        source=parts[0]['file'];length=duration(root/source)
        if length is not None and parts[-1]['start']>=length:
            warnings.append('CUE 索引超过音频长度：'+cue.name);continue
        if source in cue_sources:
            warnings.append('同一音频有多个 CUE，采用按文件名排序的第一个：'+cue.name);continue
        cue_sources[source]=parts
    # A CUE may reference a file in a child directory even in a nonrecursive view.
    for source in cue_sources:
        file=root/source
        if file not in files:files.append(file)
    for file in files:
        if file.suffix.lower() not in audio_extensions:continue
        name=file.relative_to(root).as_posix();length=duration(file)
        parts=cue_sources.get(name,[{'id':name,'file':name,'start':0,'end':None}])
        for part in parts:
            identity=part['id'];sources[identity]=part
            end=part['end'] if part['end'] is not None else length
            durations[identity]={**durations[name],'seconds':max(0,end-part['start']) if end is not None else None}
            track={'filename':identity,**marks.get(identity,{'selected':False,'highlighted':False})}
            if 'number' in part:track['display_name']=f"{part['number']:02} {part.get('title','')}".strip()
            tracks.append(track)
    return tracks,durations,sources,marks,warnings


def save_cue_track(path,number,values,expected):
    """Edit only this TRACK's TITLE/PERFORMER, preserving indexes and encoding."""
    import os,tempfile
    raw=path.read_bytes()
    if raw!=expected:raise ValueError('CUE 文件已被修改，请重新打开编辑窗口')
    for encoding in ('utf-8-sig','utf-16' if raw[:2] in (b'\xff\xfe',b'\xfe\xff') else 'gb18030','cp1252'):
        try:text=raw.decode(encoding);break
        except UnicodeError:continue
    else:raise ValueError('无法识别 CUE 编码')
    if encoding=='utf-8-sig' and not raw.startswith(b'\xef\xbb\xbf'):encoding='utf-8'
    for value in values.values():
        if any(c in value for c in ('"','\r','\n','\0')):raise ValueError('CUE 曲名和艺术家不能包含双引号或换行')
    lines=text.splitlines(keepends=True);start=None;end=len(lines)
    for i,line in enumerate(lines):
        match=re.match(r'\s*TRACK\s+(\d+)\s+',line,re.I)
        if match:
            if start is not None:end=i;break
            if int(match[1])==number:start=i
    if start is None:raise ValueError('未找到 CUE 曲目')
    newline='\r\n' if '\r\n' in text else '\n'
    block=[line for line in lines[start+1:end] if not re.match(r'\s*(TITLE|PERFORMER)\s+',line,re.I)]
    insert=['    TITLE "'+values['title']+'"'+newline,'    PERFORMER "'+values['artist']+'"'+newline]
    encoded=''.join(lines[:start+1]+insert+block+lines[end:]).encode(encoding)
    if encoded==raw:return
    recovery=Path(tempfile.mkdtemp(prefix='cratelog-cue-recovery-'))
    (recovery/'previous.cue').write_bytes(raw);(recovery/'pending.cue').write_bytes(encoded)
    (recovery/'target.txt').write_text(str(path),encoding='utf-8')
    try:
        with path.open('r+b') as stream:
            if stream.read()!=raw:raise OSError('CUE 文件已被其他程序修改')
            stream.seek(0);stream.write(encoded);stream.truncate();stream.flush();os.fsync(stream.fileno())
        if path.read_bytes()!=encoded:raise OSError('写入校验失败')
    except OSError as error:raise OSError(f'{error}；恢复副本：{recovery}') from error
    try:
        for file in recovery.iterdir():file.unlink()
        recovery.rmdir()
    except OSError:pass
