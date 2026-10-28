"""End-to-end reconciliation against an isolated PHP/SQLite server."""
import os
import secrets
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from PIL import Image
import requests
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from cratelog_library import Remote,Conflict,load_album,atomic_json,save_album
from cratelog_conflict import merge,target_folder

with tempfile.TemporaryDirectory() as tmp:
    base=Path(tmp);data=base/'data';folder=base/'VA -1989- Album';folder.mkdir()
    atomic_json(folder/'album_info.json',{'音乐人':'VA','专辑名':'Album','出版年份':'1989','来源':'old','导入来源':'Records.xlsx'})
    Image.new('RGB',(12,12),'orange').save(folder/'cover.png')
    (folder/'info.md').write_text('preserved remote attachment',encoding='utf-8')
    token=secrets.token_hex(32)
    sock=socket.socket();sock.bind(('127.0.0.1',0));port=sock.getsockname()[1];sock.close()
    url=f'http://127.0.0.1:{port}/cratelog_api.php'
    env=dict(os.environ,CRATELOG_DATA_DIR=str(data),CRATELOG_API_TOKEN=token)
    proc=subprocess.Popen(['php','-d','xdebug.mode=off','-d','display_errors=0','-S',f'127.0.0.1:{port}','-t',str(Path(__file__).resolve().parents[1]/'web')],env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    try:
        for _ in range(80):
            try:
                if requests.get(url,timeout=.3).status_code==401:break
            except requests.RequestException:pass
            time.sleep(.1)
        else:raise AssertionError('PHP server did not start')
        api=Remote(url,token)
        first=api.sync(folder)['album'];assert first['images'] and first['documents']
        detail=requests.get(url.replace('_api',''),params={'album':first['id']},timeout=5)
        assert detail.status_code==200 and 'info.md' in detail.text and 'data-preview' in detail.text
        other_folder=base/'VA -1990- Other';other_folder.mkdir()
        atomic_json(other_folder/'album_info.json',{'音乐人':'VA','专辑名':'Other','出版年份':'1990'})
        import wave
        from cratelog_tracks import save_cue_track
        with wave.open(str(other_folder/'disc.wav'),'wb') as audio:
            audio.setparams((1,2,8000,0,'NONE','not compressed'));audio.writeframes(b'\0\0'*16000)
        cue=other_folder/'disc.cue'
        cue.write_text('PERFORMER "VA"\nFILE "disc.wav" WAVE\n  TRACK 01 AUDIO\n    TITLE "Old"\n    INDEX 01 00:00:00\n',encoding='utf-8')
        marked=load_album(other_folder);marked['tracks'][0]['highlighted']=True;save_album(other_folder,marked)
        save_cue_track(cue,1,{'title':'New Title','artist':'Track Artist'},cue.read_bytes())
        edited=load_album(other_folder)
        assert edited['_track_sources']['disc.cue#track=01']['performer']=='Track Artist'
        assert edited['tracks'][0]['highlighted']
        other=api.sync(other_folder)['album']
        assert other['tracks'][0]['display_name']=='01 New Title'
        assert other['tracks'][0]['filename']=='disc.cue#track=01' and other['tracks'][0]['highlighted']
        cue_detail=requests.get(url.replace('_api',''),params={'album':other['id']},timeout=5)
        assert '01 New Title' in cue_detail.text and 'disc.cue#track=01' not in cue_detail.text

        detail=requests.get(url.replace('_api',''),params={'album':first['id']},timeout=5)
        assert detail.status_code==200
        assert '?album='+other['id'] in detail.text and '<strong>Other</strong>' in detail.text
        assert 'cratelog.php?q=VA&amp;page=0' in detail.text
        headings=['曲目','专辑资料','封面与内页','音频文件','收藏信息','个人评论','文档与附件','相关专辑']
        positions=[detail.text.index('<h3>'+heading+'</h3>') for heading in headings]
        assert positions==sorted(positions)

        preview=requests.get(url.replace('_api',''),params={'album':first['id'],'document':first['documents'][0]['sha256'],'preview':1},timeout=5)
        assert preview.status_code==200 and 'preserved remote attachment' in preview.text
        assert '来源' not in first['metadata'] and '导入来源' not in first['metadata']
        assert api.catalog().records[0]['number']==first['metadata']['编号']
        added=folder/'AI-inf.md'
        added.write_text('# Added after first sync\n\nNew document.',encoding='utf-8')
        again=api.sync(folder)['album']
        assert again['id']==first['id']
        assert {d['filename'] for d in again['documents']}=={'info.md','AI-inf.md'}
        detail=requests.get(url.replace('_api',''),params={'album':again['id']},timeout=5)
        assert 'AI-inf.md' in detail.text
        document=next(d for d in again['documents'] if d['filename']=='AI-inf.md')
        downloaded=requests.get(url.replace('_api',''),params={'album':again['id'],'document':document['sha256']},timeout=5)
        assert downloaded.content==added.read_bytes()
        added.unlink()
        api.sync(folder)
        print('PASS: newly added AI-inf.md uploaded on second sync and shown on same web album')
        (folder/'cover.png').unlink();(folder/'info.md').unlink()
        db=sqlite3.connect(data/'cratelog.sqlite')
        db.execute('UPDATE cratelog_albums SET rating=4.5,personal_comment=?,revision=revision+1 WHERE id=?',('Remote review',first['id']))
        db.commit();db.close()
        try:api.sync(folder)
        except Conflict:pass
        else:raise AssertionError('Changed remote version was not detected')
        local=load_album(folder);latest=api.fetch(local)
        choices={('metadata','音乐人'):'remote',('metadata','专辑名'):'remote',('metadata','出版年份'):'remote',('rating',None):'remote',('personal_comment',None):'remote'}
        latest['metadata'].update({'音乐人':'Remote VA','专辑名':'New Album','出版年份':'1990'})
        merged=merge(local,latest,choices)
        target=target_folder(folder,merged['metadata']);folder.rename(target)
        for group,kind in (('images','image'),('documents','document')):
            for item in latest[group]:
                (target/item['filename']).write_bytes(api.download_asset(latest['id'],item,kind))
        merged['local_path']=str(target)
        atomic_json(target/'album_info.json',merged['metadata']);save_album(target,merged)
        result=api.sync(target,match_folder=False)['album']
        assert result['metadata']['音乐人']=='Remote VA' and result['metadata']['专辑名']=='New Album'
        assert result['rating']==4.5 and result['personal_comment']=='Remote review'
        assert len(result['images'])==1 and len(result['documents'])==1
        assert (target/'cover.png').exists() and (target/'info.md').read_text(encoding='utf-8')=='preserved remote attachment'
        assert result['local_path'].replace('\\','/').endswith('/Remote VA -1990- New Album')
        assert load_album(target)['metadata']['专辑名']=='New Album'
        (target/'cover.png').unlink();(target/'info.md').unlink()
        retained=api.sync(target,match_folder=False)['album']
        assert len(retained['images'])==1 and len(retained['documents'])==1
        document=requests.get(url.replace('_api',''),params={'album':retained['id'],'document':retained['documents'][0]['sha256']},timeout=5)
        assert document.content==b'preserved remote attachment'
        print('PASS: real conflict, resolved field choices, folder rename, SQLite update and remote assets preserved')
    finally:
        proc.terminate()
        try:proc.wait(timeout=5)
        except subprocess.TimeoutExpired:proc.kill();proc.wait()
