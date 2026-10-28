"""Optional isolated MySQL/PHP + real mpv integration test (Windows developer tools)."""
import copy
import json
import os
from pathlib import Path
import queue
import secrets
import subprocess
import sys
import time

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from PIL import Image
import requests
from cratelog_library import Remote, Conflict, load_album, save_album, payload
from cratelog_player import MPV

BASE=Path(__file__).resolve().parents[1]
QA=BASE/'.qa'
MYSQL=Path(os.environ.get('CRATELOG_TEST_MYSQL_BIN','mysql-bin'))
FLAGS=getattr(subprocess,'CREATE_NO_WINDOW',0)


def run():
    QA.mkdir(exist_ok=True)
    processes=[]
    logs=[]
    try:
        def launch(args,env=None):
            log=(QA/f'process-{len(processes)}.log').open('w'); logs.append(log)
            p=subprocess.Popen(args,env=env,stdout=log,stderr=log,creationflags=FLAGS); processes.append(p); return p
        if '--mysql' in sys.argv:
            launch([str(MYSQL/'mysqld.exe'),'--no-defaults','--datadir='+str(QA/'mysql'),'--port=33077','--bind-address=127.0.0.1','--mysqlx=OFF'])
            mysql=[str(MYSQL/'mysql.exe'),'--no-defaults','-h127.0.0.1','-P33077','-uroot','--default-character-set=utf8mb4']
            for _ in range(80):
                check=subprocess.run(mysql+['-e','SELECT 1'],capture_output=True,creationflags=FLAGS)
                if check.returncode==0:break
                time.sleep(.25)
            else:raise RuntimeError('Test MySQL did not start; see .qa logs')
            schema='CREATE DATABASE IF NOT EXISTS cratelog_test; USE cratelog_test; '+(BASE/'web/cratelog_schema.sql').read_text()
            subprocess.run(mysql,input=schema.encode(),check=True,capture_output=True,creationflags=FLAGS)
            columns=subprocess.run(mysql+['-N','-e',"SHOW COLUMNS FROM cratelog_test.cratelog_albums LIKE 'personal_comment'"],capture_output=True,check=True,creationflags=FLAGS)
            if not columns.stdout.strip():
                migration='USE cratelog_test; '+(BASE/'web/cratelog_migrate_v2.sql').read_text()
                subprocess.run(mysql,input=migration.encode(),check=True,capture_output=True,creationflags=FLAGS)
                print('PASS: v1 database migrated to half-star/comment/document schema')
            token=secrets.token_hex(32)
            env=dict(os.environ,CRATELOG_DSN='mysql:host=127.0.0.1;port=33077;dbname=cratelog_test;charset=utf8mb4',
                CRATELOG_DB_USER='root',CRATELOG_DB_PASSWORD='',CRATELOG_API_TOKEN=token,CRATELOG_IMAGE_DIR=str(QA/'images'))
        else:
            token=secrets.token_hex(32)
            env=dict(os.environ,CRATELOG_API_TOKEN=token,CRATELOG_DATA_DIR=str(QA/('sqlite-'+secrets.token_hex(4))))
            env.pop('CRATELOG_DSN',None)
            env.pop('CRATELOG_IMAGE_DIR',None)
        launch(['php','-d','session.save_path='+str(QA),'-d','upload_max_filesize=10M','-d','post_max_size=220M','-d','max_file_uploads=30','-S','127.0.0.1:18765','-t',str(BASE/'web')],env)
        url='http://127.0.0.1:18765/cratelog_api.php'
        for _ in range(80):
            try:
                if requests.get(url,timeout=1).status_code==401:break
            except requests.RequestException:pass
            time.sleep(.1)
        else:raise RuntimeError('PHP test server did not start')
        folder=QA/('album-'+secrets.token_hex(4)); folder.mkdir()
        Image.new('RGB',(80,80),'orange').save(folder/'cover.jpg')
        (folder/'album_info.json').write_text(json.dumps({'音乐人':'Cratelog 测试','专辑名':'同步与解码 <script>alert(1)</script>'}),encoding='utf-8')
        markdown='# Album notes\n\n**Markdown 内容**\n\n<script>alert(99)</script>\n[bad](javascript:alert(1))\n'
        (folder/'听后感.md').write_text(markdown,encoding='utf-8')
        for ext,codec in [('mp3','libmp3lame'),('mpa','mp2'),('wav','pcm_s16le'),('flac','flac'),('ogg','libvorbis')]:
            file=folder/('01 测试.'+ext)
            command=['ffmpeg','-v','error','-f','lavfi','-i','sine=frequency=440:duration=2','-c:a',codec]
            if ext=='mpa':command+=['-f','mp2']
            subprocess.run(command+['-y',str(file)],check=True,creationflags=FLAGS)
            result=subprocess.run([str(BASE/'runtime/mpv/mpv.exe'),'--no-config','--no-video','--ao=null','--untimed',str(file)],capture_output=True,creationflags=FLAGS)
            assert result.returncode==0,(ext,result.stdout,result.stderr)
        print('PASS: real mpv decoding mp3, mpa, wav, flac, ogg')
        import shutil
        multi=QA/('multi-'+secrets.token_hex(4));(multi/'CD1').mkdir(parents=True);(multi/'CD2').mkdir()
        for cd in ('CD1','CD2'):shutil.copyfile(folder/'01 测试.wav',multi/cd/'disc.wav')
        (multi/'CD1'/'disc.cue').write_text('FILE "disc.wav" WAVE\n TRACK 01 AUDIO\n INDEX 01 00:00:00\n TRACK 02 AUDIO\n INDEX 01 00:01:00\n',encoding='utf-8')
        multi_remote=Remote(url,token)
        multi_album=load_album(multi,recursive=True);multi_album['tracks'][1]['highlighted']=True;multi_album['tracks'][2]['selected']=True;save_album(multi,multi_album)
        multi_remote.sync(multi)
        multi_album=load_album(multi);multi_saved=multi_remote.fetch(multi_album)
        assert [t['filename'] for t in multi_saved['tracks']]==['CD1/disc.cue#track=01','CD1/disc.cue#track=02','CD2/disc.wav']
        assert multi_saved['tracks'][1]['highlighted'] and multi_saved['tracks'][2]['selected']
        multi_remote.sync(multi)
        assert load_album(multi)['tracks'][1]['highlighted']
        traversal=payload(load_album(multi));traversal['tracks'][0]['filename']='../outside.mp3'
        rejected=requests.post(url,headers={'Authorization':'Bearer '+token},data={'album':json.dumps(traversal),'revision':2},timeout=10)
        assert rejected.status_code==422,rejected.text
        print('PASS: nested paths and CUE markers survive repeated sync; traversal rejected')
        remote=Remote(url,token)
        empty=QA/('empty-'+secrets.token_hex(4)); empty.mkdir()
        remote.sync(empty)
        first_number=int(remote.fetch(load_album(empty))['metadata']['编号'])
        assert first_number>0
        a=load_album(folder); a['rating']=4; a['tracks'][0].update(selected=True,highlighted=True); save_album(folder,a)
        assert remote.fetch(a) is None
        remote.sync(folder); a=load_album(folder)
        assert int(a['metadata']['编号'])==first_number+1
        r=remote.fetch(a); assert r['rating']==4 and r['tracks'][0]['highlighted'] and r['_revision']==1
        stale=copy.deepcopy(a)
        a['rating']=4.5;a['personal_comment']='个人评论 <script>bad</script>\n第二行';save_album(folder,a);remote.sync(folder)
        save_album(folder,stale)
        try:remote.sync(folder);raise AssertionError('Conflict was not detected')
        except Conflict:pass
        assert load_album(folder)['rating']==4
        remote.pull(folder,remote.fetch(a),force=True)
        assert load_album(folder)['rating']==4.5 and load_album(folder)['personal_comment']==a['personal_comment']
        headers={'Authorization':'Bearer '+token}
        bad=requests.post(url,headers=headers,data={'album':'broken','revision':1},timeout=10)
        assert bad.status_code==422
        invalid=payload(load_album(folder)); invalid['tracks'][0]['filename']='../escape.mp3'
        bad=requests.post(url,headers=headers,data={'album':json.dumps(invalid),'revision':2},timeout=10)
        assert bad.status_code==422
        assert requests.get(url,timeout=10).status_code==401
        assert requests.get(url,timeout=10).json()['code']=='auth_header_missing'
        assert requests.get(url,headers={'X-Cratelog-Token':'wrong'},timeout=10).json()['code']=='auth_token_mismatch'
        assert requests.get(url,headers={'X-Cratelog-Token':token},timeout=10).status_code==200
        assert requests.get(url,headers={'Authorization':'bearer '+token},timeout=10).status_code==200
        invalid=payload(load_album(empty));invalid['rating']=4.25
        bad=requests.post(url,headers=headers,data={'album':json.dumps(invalid),'revision':1},timeout=10)
        assert bad.status_code==422
        session=requests.Session()
        public=requests.get(url.replace('_api',''),timeout=10)
        assert public.status_code==200 and 'data-album-url=' in public.text
        assert '导入 XLSX</a>' not in public.text and '原 Excel 检索</a>' not in public.text
        public_detail=requests.get(url.replace('_api',''),params={'album':a['id']},timeout=10)
        assert public_detail.status_code==200 and '编辑 / 删除' not in public_detail.text
        protected=requests.get(url.replace('_api',''),params={'import':'xlsx'},timeout=10)
        assert 'name="token"' in protected.text and 'name="csrf"' not in protected.text
        blocked=requests.post(url.replace('_api',''),params={'album':a['id'],'edit':1},data={'action':'delete'},timeout=10)
        assert 'name="token"' in blocked.text and remote.fetch(a) is not None
        rejected=session.post(url.replace('_api',''),data={'token':'wrong-token'},timeout=10)
        assert '同步令牌不匹配' in rejected.text
        lost=requests.get(url.replace('_api','')+'?login_check=1',timeout=10)
        assert '登录状态未能保留' in lost.text
        page=session.post(url.replace('_api',''),data={'token':token},timeout=10)
        assert page.history and page.history[0].status_code==303
        assert page.status_code==200 and '&lt;script&gt;' in page.text and '<script>alert' not in page.text
        assert '导入 XLSX</a>' in page.text and '原 Excel 检索</a>' in page.text
        image=session.get(url.replace('_api',''),params={'image':a['images'][0]['sha256']},timeout=10)
        assert image.status_code==200 and image.content==(folder/'cover.jpg').read_bytes()
        detail=session.get(url.replace('_api',''),params={'album':a['id']},timeout=10)
        assert detail.status_code==200 and 'width:90%' in detail.text
        assert 'data-preview' in detail.text and '个人评论' in detail.text
        assert '<script>alert(99)' not in detail.text and 'href="javascript:' not in detail.text
        assert 'https://search.douban.com/music/subject_search?search_text=' in detail.text
        assert 'data-album-url=' in page.text
        doc=remote.fetch(a)['documents'][0]
        download=session.get(url.replace('_api',''),params={'album':a['id'],'document':doc['sha256']},timeout=10)
        assert download.content==(folder/'听后感.md').read_bytes()
        preview=session.get(url.replace('_api',''),params={'album':a['id'],'document':doc['sha256'],'preview':1},timeout=10)
        assert '<h1>Album notes</h1>' in preview.text and '<script>alert(99)' not in preview.text
        assert "frame-ancestors 'self'" in preview.headers['Content-Security-Policy']
        (QA/'web-detail.html').write_text(detail.text,encoding='utf-8')
        # Older clients omit new fields; existing comments/documents remain intact.
        legacy=payload(load_album(empty));legacy.update(personal_comment='Keep me',rating=3.5)
        save_album(empty,{**load_album(empty),**legacy});remote.sync(empty)
        legacy.pop('personal_comment');legacy.pop('documents')
        response=requests.post(url,headers=headers,data={'album':json.dumps(legacy),'revision':2},timeout=10)
        assert response.status_code==200 and remote.fetch(legacy)['personal_comment']=='Keep me'
        print('PASS: half-star roundtrip, comments, Markdown upload/download, safe detail page, legacy compatibility')
        print('PASS: database insert/update, images, flags, conflict, pull, authenticated web, XSS escaping')
        from web_features import check_web_features
        check_web_features(folder,url,token,session,Path(env['CRATELOG_DATA_DIR'])/'cratelog.sqlite' if '--mysql' not in sys.argv else None)
        events=queue.Queue(); engine=MPV(str(BASE/'runtime/mpv/mpv.exe'),events)
        try:
            engine.command('set_property','volume',0)
            engine.command('loadfile',str(folder/'01 测试.wav'),'replace')
            seen=set(); deadline=time.monotonic()+10
            while time.monotonic()<deadline:
                kind,event=events.get(timeout=5)
                assert kind!='error',event
                if event.get('event')=='property-change':seen.add(event.get('name'))
                if {'time-pos','duration','audio-params'}<=seen:break
            assert {'time-pos','duration','audio-params'}<=seen,seen
            engine.command('set_property','pause',True)
            engine.command('seek',1,'absolute')
            paused=False; deadline=time.monotonic()+5
            while time.monotonic()<deadline:
                kind,event=events.get(timeout=5)
                if event.get('event')=='property-change' and event.get('name')=='pause' and event.get('data') is True:
                    paused=True;break
            assert paused
            print('PASS: actual Windows named-pipe IPC and playback events')
        finally:engine.close()
    finally:
        for p in reversed(processes):
            p.terminate()
            try:p.wait(timeout=10)
            except subprocess.TimeoutExpired:p.kill();p.wait()
        for log in logs:log.close()


if __name__=='__main__':run()
