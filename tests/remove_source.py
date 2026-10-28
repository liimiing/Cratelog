"""One-off source-field cleanup, backup, idempotence and web authorization."""
import json
import os
import re
import secrets
import socket
import sqlite3
import subprocess
import tempfile
import time
from pathlib import Path
import requests

base=Path(__file__).resolve().parents[1]
script=base/'web/cratelog_remove_source.php'
with tempfile.TemporaryDirectory(dir=base) as tmp:
    data=Path(tmp)/'data';env=dict(os.environ,CRATELOG_DATA_DIR=str(data),CRATELOG_API_TOKEN=secrets.token_hex(32))
    env.pop('CRATELOG_DSN',None)
    cmd=['php','-d','xdebug.mode=off','-d','display_errors=0',str(script)]
    first=subprocess.run(cmd,env=env,capture_output=True,text=True,encoding='utf-8',check=True)
    assert '0' in first.stdout
    db=sqlite3.connect(data/'cratelog.sqlite')
    metadata={'编号':'12','音乐人':'Artist','专辑名':'Album','来源':'old','导入来源':'Records.xlsx'}
    album_id='11111111-1111-4111-a111-111111111111'
    db.execute('INSERT INTO cratelog_albums(id,local_path,metadata,images,documents) VALUES(?,?,?,?,?)',(album_id,'/Music/Album',json.dumps(metadata),'[]','[]'))
    db.commit();db.close()
    result=subprocess.run(cmd,env=env,capture_output=True,text=True,encoding='utf-8',check=True)
    assert '1' in result.stdout
    db=sqlite3.connect(data/'cratelog.sqlite')
    saved,revision=db.execute('SELECT metadata,revision FROM cratelog_albums WHERE id=?',(album_id,)).fetchone()
    saved=json.loads(saved)
    assert saved=={'编号':'12','音乐人':'Artist','专辑名':'Album'} and revision==2
    backup=next((data/'backups').glob('removed-source-*.json'))
    assert json.loads(backup.read_text(encoding='utf-8'))[0]['removed']=={'来源':'old','导入来源':'Records.xlsx'}
    assert '0' in subprocess.run(cmd,env=env,capture_output=True,text=True,encoding='utf-8',check=True).stdout
    db.execute('UPDATE cratelog_albums SET metadata=? WHERE id=?',(json.dumps(metadata),album_id));db.commit();db.close()
    sock=socket.socket();sock.bind(('127.0.0.1',0));port=sock.getsockname()[1];sock.close()
    proc=subprocess.Popen(['php','-d','xdebug.mode=off','-d','display_errors=0','-d','session.save_path='+str(Path(tmp)),'-S',f'127.0.0.1:{port}','-t',str(base/'web')],env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    try:
        url=f'http://127.0.0.1:{port}/cratelog_remove_source.php'
        session=requests.Session()
        for _ in range(50):
            try:
                page=session.get(url,timeout=.3)
                if page.status_code==200:break
            except requests.RequestException:pass
            time.sleep(.1)
        else:raise AssertionError('PHP server did not start')
        assert '同步令牌' in page.text and '当前仍有' not in page.text
        csrf=re.search(r'name="csrf" value="([a-f0-9]+)"',page.text)[1]
        wrong=session.post(url,data={'csrf':csrf,'token':'wrong'},timeout=5)
        assert '不正确' in wrong.text
        db=sqlite3.connect(data/'cratelog.sqlite')
        before=json.loads(db.execute('SELECT metadata FROM cratelog_albums').fetchone()[0]);db.close()
        assert '来源' in before
        done=session.post(url,data={'csrf':csrf,'token':env['CRATELOG_API_TOKEN']},timeout=5)
        assert '已清理 1 条' in done.text
        db=sqlite3.connect(data/'cratelog.sqlite')
        after=json.loads(db.execute('SELECT metadata FROM cratelog_albums').fetchone()[0]);db.close()
        assert '来源' not in after
    finally:
        proc.terminate();proc.wait(timeout=5)
print('PASS: source keys removed with backup; web form requires token and CSRF')
