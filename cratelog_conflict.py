"""Explicit, lossless album conflict choices and portable folder names."""
import copy
import re
import unicodedata
from pathlib import Path

from cratelog_library import parse_album_folder,normalize_metadata


def clean(value):
    return ' '.join(str(value or '').split())


def safe_component(value):
    value=unicodedata.normalize('NFKC', clean(value))
    value=re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', value).strip(' .')
    value=re.sub(r'_+', '_', value)
    if value.upper().split('.')[0] in {'CON','PRN','AUX','NUL', *(f'COM{i}' for i in range(1,10)), *(f'LPT{i}' for i in range(1,10))}:
        value='_'+value
    return value


def standard_folder_name(metadata):
    artist=safe_component(metadata.get('音乐人'))
    title=safe_component(metadata.get('专辑名'))
    year=clean(metadata.get('出版年份'))
    if not artist or not title:
        raise ValueError('艺术家和专辑名不能为空，无法安全生成专辑文件夹名')
    if year and not re.fullmatch(r'\d{4}',year):
        raise ValueError('发行年份须为四位数字或留空')
    name=f'{artist} -{year}- {title}' if year else f'{artist} - {title}'
    if len(name.encode('utf-8'))>240:
        raise ValueError('专辑文件夹名过长，请在对比面板缩短艺术家或专辑名')
    return name


def target_folder(folder,metadata):
    folder=Path(folder)
    target=folder.with_name(standard_folder_name(metadata))
    if target==folder:
        return folder
    if target.exists():
        # macOS paths compare case-sensitively even on case-insensitive volumes.
        # An existing alias of this directory is not a destination collision.
        if target.samefile(folder):
            return folder
        raise FileExistsError('目标专辑文件夹已存在：'+str(target))
    return target


def fields(local,remote):
    lm=normalize_metadata(local.get('metadata') or {});rm=normalize_metadata(remote.get('metadata') or {})
    names=list(dict.fromkeys((*lm,*rm)))
    names=[key for key in names if key!='编号']
    names.sort(key=lambda key:(key not in ('音乐人','专辑名','出版年份','唱片厂牌','唱片编号','音乐风格','风格标签','国家','备注信息','曲目表'),key))
    return [('metadata',key,lm.get(key),rm.get(key)) for key in names]+[
        ('rating',None,local.get('rating',0),remote.get('rating',0)),
        ('personal_comment',None,local.get('personal_comment',''),remote.get('personal_comment',''))]


def merge(local,remote,choices):
    result=copy.deepcopy(local)
    lm=normalize_metadata(local.get('metadata') or {});rm=normalize_metadata(remote.get('metadata') or {})
    result['metadata']={}
    for key in dict.fromkeys((*lm,*rm)):
        source=remote if choices.get(('metadata',key))=='remote' else local
        if key=='编号':source=remote
        metadata=rm if source is remote else lm
        if key in metadata:result['metadata'][key]=copy.deepcopy(metadata[key])
    for key in ('rating','personal_comment'):
        source=remote if choices.get((key,None))=='remote' else local
        result[key]=copy.deepcopy(source.get(key,0 if key=='rating' else ''))
    remote_marks={t['filename']:t for t in remote.get('tracks',[])}
    for track in result.get('tracks',[]):
        other=remote_marks.get(track['filename'])
        if not other:continue
        for key in ('selected','highlighted'):
            if choices.get(('track',track['filename'],key))=='remote':track[key]=bool(other.get(key))
    result['id']=remote['id']
    result['_revision']=remote['_revision']
    return result


def catalog_candidates(index,folder,local):
    metadata=local.get('metadata') or {}
    parsed=parse_album_folder(folder)
    pairs=[(metadata.get('音乐人'),metadata.get('专辑名')),(parsed.get('音乐人'),parsed.get('专辑名'))]
    return [record for record in index.records if any(
        index.filename_key(artist) and index.filename_key(title) and
        index.filename_key(record.get('artist'))==index.filename_key(artist) and
        index.filename_key(record.get('album'))==index.filename_key(title)
        for artist,title in pairs)]
