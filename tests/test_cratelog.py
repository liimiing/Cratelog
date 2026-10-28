import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from PIL import Image

from cratelog_library import load_album, save_album, Remote, Conflict, digest, payload, parse_album_folder, CatalogIndex


class LibraryTests(unittest.TestCase):
    def test_folder_metadata_case_difference_is_not_conflict(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp)/'ARTIST -1989- ALBUM';folder.mkdir()
            info={'音乐人':'Artist','专辑名':'Album','出版年份':'1989'}
            path=folder/'album_info.json';path.write_text(json.dumps(info),encoding='utf-8')
            remote=Remote('http://localhost/api','token')
            def response(method,**kwargs):
                if method=='GET':return {'schema_version':5}
                self.assertEqual(json.loads(kwargs['data']['album'])['metadata'],info)
                return {'revision':1,'schema_version':5}
            with patch.object(remote,'catalog') as catalog,patch.object(remote,'request',side_effect=response):
                remote.sync(folder)
                catalog.assert_not_called()
            self.assertEqual(json.loads(path.read_text(encoding='utf-8')),info)

    def test_folder_match_does_not_replace_discogs_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp)/'Folder Artist -1989- Folder Album';folder.mkdir()
            info={'音乐人':'Discogs Artist','专辑名':'Discogs Album','出版年份':'1990'}
            path=folder/'album_info.json';path.write_text(json.dumps(info),encoding='utf-8')
            original=path.read_bytes()
            remote=Remote('http://localhost/api','token')
            index=CatalogIndex([{'id':'remote','artist':'Folder Artist','album':'Folder Album','year':'1989'}])
            with patch.object(remote,'catalog',return_value=index),patch.object(remote,'request') as request:
                with self.assertRaises(Conflict):remote.sync(folder)
                request.assert_not_called()
            self.assertEqual(path.read_bytes(),original)
            # A new album without a remote match must keep its Discogs names too.
            def response(method,**kwargs):
                if method=='GET':return {'schema_version':5}
                self.assertEqual(json.loads(kwargs['data']['album'])['metadata'],info)
                return {'revision':1,'schema_version':5}
            with patch.object(remote,'catalog',return_value=CatalogIndex()),patch.object(remote,'request',side_effect=response):
                remote.sync(folder)
            self.assertEqual(path.read_bytes(),original)

    def test_server_number_change_allows_local_review_sync(self):
        a=load_album(self.folder);a['metadata']['编号']='12'
        (self.folder/'album_info.json').write_text(json.dumps(a['metadata']),encoding='utf-8')
        baseline=copy.deepcopy(a);a['_synced']=digest(payload(baseline));a['_revision']=1
        a['rating']=4.5;a['personal_comment']='本地新评论';save_album(self.folder,a)
        latest=copy.deepcopy(baseline);latest['metadata']['编号']='99';latest['_revision']=2
        remote=Remote('http://localhost/api','token')
        calls=[]
        def post(method,**kwargs):
            calls.append(kwargs)
            if len(calls)==1:raise Conflict('revision')
            outgoing=json.loads(kwargs['data']['album'])
            self.assertEqual(outgoing['metadata']['编号'],'99')
            self.assertEqual((outgoing['rating'],outgoing['personal_comment']),(4.5,'本地新评论'))
            return {'revision':3,'schema_version':3,'album':outgoing}
        # A real edit beyond the number must still require conflict resolution.
        changed=copy.deepcopy(latest);changed['personal_comment']='远端评论'
        with patch.object(remote,'fetch',return_value=changed),patch.object(remote,'request',side_effect=Conflict('revision')) as request:
            with self.assertRaises(Conflict):remote.sync(self.folder)
            self.assertEqual(request.call_count,1)
        with patch.object(remote,'fetch',return_value=latest),patch.object(remote,'request',side_effect=post):remote.sync(self.folder)
        saved=load_album(self.folder)
        self.assertEqual(saved['metadata']['编号'],'99')
        self.assertEqual(saved['_revision'],3)
        self.assertEqual(saved['personal_comment'],'本地新评论')

    def test_rating_sync_retries_only_unchanged_remote_content(self):
        a=load_album(self.folder); baseline=copy.deepcopy(a)
        a['_revision']=1;a['_synced']=digest(payload(baseline));a['rating']=4.5;a['personal_comment']='新评论'
        save_album(self.folder,a)
        remote=Remote('http://localhost/api','token')
        baseline['_revision']=2
        with patch.object(remote,'fetch',return_value=baseline),patch.object(remote,'request',side_effect=[Conflict('stale'),{'revision':3,'schema_version':3}]) as request:
            remote.sync(self.folder)
            self.assertEqual(request.call_args.kwargs['data']['revision'],2)
        saved=load_album(self.folder)
        self.assertEqual((saved['_revision'],saved['rating'],saved['personal_comment']),(3,4.5,'新评论'))
        baseline['rating']=5
        with patch.object(remote,'fetch',return_value=baseline),patch.object(remote,'request',side_effect=Conflict('changed')) as request:
            with self.assertRaises(Conflict):remote.sync(self.folder)
            self.assertEqual(request.call_count,1)

    def test_undated_folder_matching(self):
        records=[{'id':'remote','artist':'VA','album':'Kha Nam Nom'}]
        index=CatalogIndex(records)
        for name in ('VA - Kha Nam Nom','VA -- Kha Nam Nom'):
            self.assertEqual(parse_album_folder(name),{'音乐人':'VA','专辑名':'Kha Nam Nom'})
            self.assertTrue(index.contains(Path(name),{}))
            self.assertEqual(index.lookup(Path(name),{})['id'],'remote')
            self.assertIsNone(CatalogIndex(records+[dict(records[0],id='duplicate')]).lookup(Path(name),{}))
        self.assertEqual(parse_album_folder('Luc Ferrari -2009- A - B')['出版年份'],'2009')
        self.assertEqual(parse_album_folder('VA - A - B')['专辑名'],'A - B')
        self.assertEqual(parse_album_folder('AC-DC'),{})

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.folder = Path(self.temp.name) / 'album'
        self.folder.mkdir()
        for name in ('02.flac', '01.mp3', '10.MPA', '03.wav', '04.ogg'):
            (self.folder/name).write_bytes(b'audio fixture')
        (self.folder/'album_info.json').write_text(json.dumps({'专辑名':'原名','音乐人':'音乐人'},ensure_ascii=False),encoding='utf-8')
        Image.new('RGB',(8,8),'orange').save(self.folder/'cover.jpg')

    def tearDown(self):self.temp.cleanup()

    def test_identity_marks_survive_folder_rename_and_discogs_refresh(self):
        a=load_album(self.folder); a['rating']=4; a['tracks'][0]['selected']=True
        save_album(self.folder,a)
        new=self.folder.with_name('standardized'); self.folder.rename(new)
        (new/'album_info.json').write_text('{"专辑名":"新版资料"}',encoding='utf-8')
        b=load_album(new)
        self.assertEqual(a['id'],b['id']); self.assertEqual(b['rating'],4)
        self.assertTrue(b['tracks'][0]['selected']); self.assertEqual(b['metadata']['专辑名'],'新版资料')
        self.assertEqual(b['local_path'],str(new.resolve()))

    def test_changed_track_set_and_independent_marks(self):
        a=load_album(self.folder); a['tracks'][0].update(selected=True,highlighted=True); save_album(self.folder,a)
        (self.folder/'02.flac').unlink(); (self.folder/'05.opus').touch()
        a=load_album(self.folder)
        self.assertEqual([t['filename'] for t in a['tracks']],['01.mp3','03.wav','04.ogg','05.opus','10.MPA'])
        self.assertTrue(a['tracks'][0]['selected'] and a['tracks'][0]['highlighted'])

    def test_corrupt_sidecar_is_not_silently_replaced(self):
        path=self.folder/'.cratelog.json'; path.write_text('{broken')
        with self.assertRaises(json.JSONDecodeError):load_album(self.folder)
        self.assertEqual(path.read_text(),'{broken')

    def test_sync_keeps_concurrent_local_edit_dirty(self):
        remote=Remote('http://127.0.0.1/api','token')
        def upload(*args,**kwargs):
            a=load_album(self.folder); a['rating']=5; save_album(self.folder,a)
            return {'revision':1,'schema_version':2}
        with patch.object(remote,'request',side_effect=upload):remote.sync(self.folder)
        a=load_album(self.folder)
        self.assertEqual(a['rating'],5); self.assertEqual(a['_revision'],1)
        self.assertNotEqual(a['_synced'],digest(payload(a)))

    def test_conflict_preserves_local_and_explicit_pull_backs_up(self):
        a=load_album(self.folder); r=copy.deepcopy(a); r['rating']=5; r['_revision']=3
        remote=Remote('http://localhost/api','token')
        with self.assertRaises(Conflict):remote.pull(self.folder,r)
        self.assertEqual(load_album(self.folder)['rating'],0)
        b=remote.pull(self.folder,r,force=True)
        self.assertEqual(b['rating'],5); self.assertEqual(b['_revision'],3)
        self.assertTrue((self.folder/'.cratelog-conflict-backup.json').exists())

    def test_http_remote_is_rejected(self):
        with self.assertRaises(ValueError):Remote('http://example.com/api','secret')

    def test_pull_does_not_mark_unsent_local_path_as_synced(self):
        a=load_album(self.folder); r=copy.deepcopy(a)
        r['local_path']='D:/another-computer/album'; r['_revision']=2
        b=Remote('http://localhost/api','token').pull(self.folder,r,force=True)
        self.assertNotEqual(b['_synced'],digest(payload(b)))

    def test_half_star_comment_and_markdown_survive_rename(self):
        (self.folder/'听后感.md').write_text('# Notes\n内容',encoding='utf-8')
        a=load_album(self.folder); a.update(rating=3.5,personal_comment='个人评论\n第二行')
        save_album(self.folder,a)
        new=self.folder.with_name('renamed');self.folder.rename(new)
        b=load_album(new)
        self.assertEqual(b['rating'],3.5);self.assertEqual(b['personal_comment'],a['personal_comment'])
        self.assertEqual(b['documents'],a['documents'])

    def test_remote_review_pull_and_numeric_digest(self):
        a=load_album(self.folder);r=copy.deepcopy(a)
        r.update(rating=4.5,personal_comment='远端评价',_revision=3)
        b=Remote('http://localhost/api','token').pull(self.folder,r,force=True)
        self.assertEqual((b['rating'],b['personal_comment']),(4.5,'远端评价'))
        self.assertEqual(digest({'rating':4}),digest({'rating':4.0}))

    def test_old_server_does_not_mark_new_review_as_synced(self):
        remote=Remote('http://localhost/api','token')
        with patch.object(remote,'request',return_value={'revision':1}):
            with self.assertRaises(ValueError):remote.sync(self.folder)
        self.assertEqual(load_album(self.folder)['_revision'],0)


if __name__=='__main__':unittest.main()
