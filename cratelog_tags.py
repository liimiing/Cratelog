"""Edit common audio tags without touching covers or unrelated metadata."""
import os
import shutil
import tempfile
from pathlib import Path
from cratelog_library import AudioMetadata
from mutagen.id3 import ID3, TIT2, TPE1, TALB, TPE2, TDRC, TRCK, TPOS, TCON, TCOM, COMM
from mutagen.mp4 import MP4
from mutagen.apev2 import APEv2

FIELDS = [('title','曲名'),('artist','艺术家'),('album','专辑'),('albumartist','专辑艺术家'),('date','发行年份 / 日期'),('tracknumber','音轨编号'),('discnumber','碟号'),('genre','流派'),('composer','作曲者'),('comment','备注')]
FRAMES = dict(zip([k for k,_ in FIELDS], [TIT2,TPE1,TALB,TPE2,TDRC,TRCK,TPOS,TCON,TCOM,COMM]))
ALIASES={'albumartist':('albumartist','album artist','album_artist'),
         'date':('date','year'), 'comment':('comment','description'),
         'tracknumber':('tracknumber','track'), 'discnumber':('discnumber','disc')}
MP4_FIELDS={'title':'\xa9nam','artist':'\xa9ART','album':'\xa9alb','albumartist':'aART',
            'date':'\xa9day','tracknumber':'trkn','discnumber':'disk','genre':'\xa9gen',
            'composer':'\xa9wrt','comment':'\xa9cmt'}
APE_FIELDS={'albumartist':'Album Artist','date':'Year','tracknumber':'Track','discnumber':'Disc'}

def mp4_value(key,value):
    if key not in ('tracknumber','discnumber'):return [value]
    parts=value.strip().split('/')
    if len(parts)>2 or not all(p.strip().isdigit() for p in parts):
        raise ValueError('Track/disc number must be a number or number/total (e.g. 1/12)')
    numbers=[int(p) for p in parts]
    if any(n>65535 for n in numbers):raise ValueError('Track/disc number must be between 0 and 65535')
    return [(numbers[0],numbers[1] if len(numbers)>1 else 0)]

def read_tags(path):
    audio=AudioMetadata(path)
    if audio is None:raise ValueError('无法识别此音频文件')
    tags=audio.tags
    if isinstance(audio,MP4):
        result={}
        for key,atom in MP4_FIELDS.items():
            values=tags.get(atom,[]) if tags is not None else []
            if key in ('tracknumber','discnumber'):
                result[key]='/'.join(str(n) for n in values[0]) if values and values[0][1] else str(values[0][0]) if values else ''
            else:result[key]='; '.join(str(v) for v in values)
        return result
    if isinstance(tags,ID3) or Path(path).suffix.lower() in ('.mp3','.mpa','.wav','.aif','.aiff'):
        return {key:'; '.join(str(t) for frame in (tags.getall(cls.__name__) if tags else []) for t in frame.text) for key,cls in FRAMES.items()}
    if Path(path).suffix.lower() not in ('.flac','.ogg','.opus','.ape'):raise ValueError('当前支持 MP3、MPA、WAV、AIFF、FLAC、APE、OGG、Opus、M4A 标签编辑')
    result={}
    for key,_ in FIELDS:
        values=[]
        for candidate in ALIASES.get(key,(key,)):
            values=tags.get(candidate,[]) if tags is not None else []
            if values:break
        result[key]='; '.join(str(v) for v in values)
    return result

def stamp(path):
    s=Path(path).stat();return (s.st_size,s.st_mtime_ns)

def save_tags(path,values,original,expected):
    path=Path(path)
    if stamp(path)!=expected:raise ValueError('文件已被其他程序修改，请关闭编辑窗口后重新打开')
    changed={k:v for k,v in values.items() if v!=original[k]}
    if not changed:return
    fd,name=tempfile.mkstemp(prefix='.cratelog-tags-',suffix=path.suffix,dir=path.parent);os.close(fd)
    try:
        shutil.copy2(path,name)
        audio=AudioMetadata(name)
        if audio.tags is None:audio.add_tags()
        for key,value in changed.items():
            if isinstance(audio,MP4):
                atom=MP4_FIELDS[key]
                if value:audio.tags[atom]=mp4_value(key,value)
                elif atom in audio.tags:del audio.tags[atom]
            elif isinstance(audio.tags,ID3):
                cls=FRAMES[key];audio.tags.delall(cls.__name__)
                if value:
                    frame=cls(encoding=3,text=[value],lang='eng',desc='') if key=='comment' else cls(encoding=3,text=[value])
                    audio.tags.add(frame)
            else:
                for candidate in ALIASES.get(key,(key,)):
                    if candidate in audio.tags:del audio.tags[candidate]
                if value:audio.tags[APE_FIELDS.get(key,key) if isinstance(audio.tags,APEv2) else key]=[value]
        audio.save()
        if stamp(path)!=expected:raise ValueError('保存期间原文件发生变化，已取消覆盖')
        os.replace(name,path)
    finally:
        if os.path.exists(name):os.unlink(name)
