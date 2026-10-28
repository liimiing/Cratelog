import copy
import hashlib
import sys
import tempfile
import tkinter as tk
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from types import SimpleNamespace
from unittest.mock import Mock,patch
from cratelog_conflict import standard_folder_name,catalog_candidates,fields,merge
from cratelog_library import CatalogIndex,Remote,load_album,read_json,atomic_json,save_album
from cratelog_player import Player
from cratelog_i18n import language
language.set_language('zh_CN')

assert standard_folder_name({'音乐人':'A/B: C','出版年份':'2001','专辑名':'X?Y'})=='A_B_ C -2001- X_Y'
assert standard_folder_name({'音乐人':'VA','专辑名':'Album'})=='VA - Album'
index=CatalogIndex([{'id':'a','artist':'VA','album':'Album','year':'1989'},{'id':'b','artist':'VA','album':'Album','year':'1990'}])
assert len(catalog_candidates(index,Path('VA -1989- Album'),{'metadata':{}}))==2
local={'id':'old','metadata':{'音乐人':'Local','专辑名':'Local Album','编号':'4'},'rating':0,'personal_comment':'local','tracks':[{'filename':'01.flac','selected':True,'highlighted':False}]}
remote={'id':'new','_revision':7,'metadata':{'音乐人':'Remote','专辑名':'Remote Album','编号':'9'},'rating':4,'personal_comment':'remote','tracks':[{'filename':'01.flac','selected':False,'highlighted':True}]}
choices={('metadata','音乐人'):'remote',('metadata','专辑名'):'remote',('rating',None):'remote',('track','01.flac','selected'):'remote'}
merged=merge(local,remote,choices)
assert (merged['id'],merged['_revision'],merged['metadata']['编号'],merged['rating'],merged['personal_comment'])==('new',7,'9',4,'local')
assert merged['tracks'][0]['selected'] is False and merged['tracks'][0]['highlighted'] is False

with tempfile.TemporaryDirectory() as tmp:
    rootdir=Path(tmp);folder=rootdir/'VA -1989- Album';folder.mkdir()
    (folder/'cover.png').write_bytes(b'old-cover')
    original=load_album(folder)
    record={**copy.deepcopy(original),'id':'a','_revision':3,'metadata':{'音乐人':'Remote Artist','专辑名':'Remote Album','出版年份':'1991','编号':'100'},'rating':3,'personal_comment':'Comment'}
    record['images']=[{'filename':'cover.png','sha256':hashlib.sha256(b'new-cover').hexdigest()}]
    api=SimpleNamespace(catalog=lambda:CatalogIndex([{'id':'a','artist':'VA','album':'Album','year':'1989'},
                                                      {'id':'b','artist':'VA','album':'Album','year':'1990'}]),
                        fetch=lambda album:record,sync=Mock(return_value={'revision':4}),download_asset=Mock(return_value=b'new-cover'))
    root=tk.Tk()
    with patch('cratelog_player.read_json',return_value={'language':'zh_CN'}):player=Player(root)
    player.settings_path=rootdir/'settings.json';player.settings['root']=str(rootdir)
    player.submit=lambda work,done:done(work())
    player.current_file=folder/'disc.flac';player.stop=Mock()
    try:
        multiple_catalog=api.catalog
        api.catalog=lambda:CatalogIndex([{'id':'a','artist':'VA','album':'Album','year':'1989'}])
        api.fetch=Mock(return_value=record)
        player.open_conflict_dialog(folder,api)
        from tkinter import ttk
        single=next(w for w in root.winfo_children() if isinstance(w,tk.Toplevel) and w.title().endswith('本地与远端资料对比'))
        single_picker=next(w for w in single.winfo_children() if isinstance(w,ttk.Combobox))
        single_table=next(w for w in single.winfo_children() if isinstance(w,ttk.Treeview))
        assert single_picker.current()==0 and single_table.get_children()
        api.fetch.assert_called_once_with({'id':'a'})
        single_bottom=next(w for w in single.winfo_children() if isinstance(w,tk.Frame))
        single_submit=next(w for w in single_bottom.winfo_children() if isinstance(w,ttk.Button) and w.cget('text')=='提交并统一两端')
        assert not single_submit.instate(['disabled'])
        api.sync.assert_not_called()
        single.destroy();api.catalog=multiple_catalog
        player.open_conflict_dialog(folder,api)
        win=next(w for w in root.winfo_children() if isinstance(w,tk.Toplevel) and w.title().endswith('本地与远端资料对比'))
        from tkinter import ttk
        table=next(w for w in win.winfo_children() if isinstance(w,ttk.Treeview))
        bottom=next(w for w in win.winfo_children() if isinstance(w,tk.Frame))
        submit=next(b for b in bottom.winfo_children() if isinstance(b,ttk.Button) and b.cget('text')=='提交并统一两端')
        assert submit.instate(['disabled']) and not table.get_children()
        picker=next(w for w in win.winfo_children() if isinstance(w,ttk.Combobox))
        picker.current(0);picker.event_generate('<<ComboboxSelected>>')
        remote_rows=[r for r in table.get_children() if table.set(r,'field') in ('音乐人','专辑名','出版年份')]
        remote_rows += [r for r in table.get_children() if table.set(r,'field')=='封面 · cover.png']
        table.selection_set(remote_rows)
        next(b for b in bottom.winfo_children() if isinstance(b,ttk.Button) and b.cget('text')=='采用远端').invoke()
        next(b for b in bottom.winfo_children() if isinstance(b,ttk.Button) and b.cget('text')=='提交并统一两端').invoke()
        target=rootdir/'Remote Artist -1991- Remote Album'
        assert target.exists() and not folder.exists()
        assert read_json(target/'album_info.json',{})['专辑名']=='Remote Album'
        assert (target/'cover.png').read_bytes()==b'new-cover'
        assert [p.read_bytes() for p in (target/'.cratelog-conflict-files').rglob('cover.png')]==[b'old-cover']
        saved=read_json(target/'.cratelog.json',{})
        assert saved['id']=='a' and saved['_revision']==3 and saved['local_path']==str(target)
        assert (target/'.cratelog-conflict-backup.json').exists() and (target/'.cratelog-remote-backup.json').exists()
        player.stop.assert_called_once()
        assert api.sync.call_args.args==(target,)
        assert api.sync.call_args.kwargs=={'match_folder':False}
        assert player.tree.selection()==(str(target),)
    finally:
        player.pool.shutdown(wait=False,cancel_futures=True);root.destroy()
print('PASS: duplicate candidates, field choices, safe folder rename, playback stop, backup and sync')

with tempfile.TemporaryDirectory() as tmp:
    folder=Path(tmp)/'Folder Artist -2001- Folder Album';folder.mkdir()
    local=load_album(folder);local['metadata']={'音乐人':'Chosen Artist','专辑名':'Chosen Album','出版年份':'1999'}
    atomic_json(folder/'album_info.json',local['metadata']);save_album(folder,local)
    remote=Remote('http://localhost/api','token')
    def request(method,**kwargs):
        if method=='GET':return {'schema_version':5}
        sent=__import__('json').loads(kwargs['data']['album'])
        assert sent['metadata']==local['metadata']
        assert kwargs['data']['match_folder']=='0' and kwargs['data']['reconcile']=='1'
        return {'revision':1,'schema_version':5,'album':{**sent,'_revision':1}}
    with patch.object(remote,'request',side_effect=request):remote.sync(folder,match_folder=False)
print('PASS: reconciliation uploads chosen metadata without folder-name override')

with tempfile.TemporaryDirectory() as tmp:
    root=tk.Tk()
    with patch('cratelog_player.read_json',return_value={'language':'zh_CN'}):player=Player(root)
    player.settings_path=Path(tmp)/'settings.json'
    player.submit=lambda work,done:done(work())
    player.refresh_catalog=Mock();player.open_conflict_dialog=Mock()
    failing=SimpleNamespace(sync=Mock(side_effect=__import__('cratelog_library').Conflict('ambiguous')))
    player.remote=lambda:failing
    try:
        player.sync_paths([Path(tmp)])
        player.open_conflict_dialog.assert_called_once_with(Path(tmp),failing)
    finally:
        player.pool.shutdown(wait=False,cancel_futures=True);root.destroy()
print('PASS: synchronization conflict automatically opens comparison')
