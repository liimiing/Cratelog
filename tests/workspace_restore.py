"""Persist and restore the actual Tk layout and filename-based selection."""
import json
import sys
import tempfile
import time
import tkinter as tk
import wave
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from cratelog_player import Player
from cratelog_library import CatalogIndex

def pump(root,until=lambda:False,seconds=1):
    deadline=time.monotonic()+seconds
    while time.monotonic()<deadline:
        root.update();time.sleep(.02)
        if until():return

with tempfile.TemporaryDirectory() as tmp, patch('cratelog_player.BASE',Path(tmp)), patch('cratelog_player.state_dir',return_value=Path(tmp)):
    base=Path(tmp);music=base/'music';album=music/'Artist'/'Album';album.mkdir(parents=True)
    for i in range(80):(album/f'{i:02}.wav').write_bytes(b'')
    with wave.open(str(album/'01.wav'),'wb') as audio:
        audio.setparams((1,2,8000,0,'NONE','not compressed'));audio.writeframes(b'\0\0'*16000)
    root=tk.Tk();player=Player(root);pump(root,seconds=.2)
    player.set_root(music);player.load_folder(album);pump(root,lambda:player.album is not None)
    root.geometry('1300x860+20+30');pump(root,seconds=.2)
    player.library_pane.sashpos(0,400)
    player.top_pane.sashpos(0,450)
    player.volume.set(37);player.mode.set('单曲循环')
    player.tracks.selection_set('50','51');player.tracks.focus('51');player.tracks.see('51');pump(root,seconds=.1)
    player.close()
    saved=json.loads((base/'cratelog_settings.json').read_text(encoding='utf-8'))
    (album/'00-extra.wav').write_bytes(b'')
    root=tk.Tk();player=Player(root);pump(root,lambda:player.album is not None,seconds=3)
    assert player.folder==album and player.album is not None
    assert root.winfo_width()==1300 and root.winfo_height()==860
    assert player.volume.get()==37 and player.mode.get()=='单曲循环'
    assert abs(player.top_pane.sashpos(0)/player.top_pane.winfo_width()-saved['layout']['top_split'])<.01
    assert abs(player.library_pane.sashpos(0)/player.library_pane.winfo_width()-saved['layout']['split'])<.01,(player.library_pane.sashpos(0),player.library_pane.winfo_width(),saved['layout'])
    assert [player.tracks.set(i,'file') for i in player.tracks.selection()]==['50.wav','51.wav']
    assert player.tracks.set(player.tracks.focus(),'file')=='51.wav'
    assert abs(player.tracks.yview()[0]-saved['browse']['scroll'])<.03
    assert player.tree.selection()==(str(album),)
    assert player.engine is None and player.playback_state=='stopped'
    row=next(i for i in player.tracks.get_children() if player.tracks.set(i,'file')=='01.wav')
    assert player.tracks.set(row,'duration')=='0:02'
    for key,width in player.fixed_track_widths.items():assert player.tracks.column(key,'width')==width
    root.geometry('1450x860');pump(root,seconds=.2)
    for key,width in player.fixed_track_widths.items():assert player.tracks.column(key,'width')==width
    player.remote_catalog=CatalogIndex([{'id':player.album['id'],'path':str(album),'artist':'','album':''}])
    player.paint_remote_folders()
    assert 'remote' in player.tree.item(str(album),'tags')
    assert player.review_summary.cget('text').startswith('☁ ')
    player.remote_catalog=CatalogIndex();player.paint_remote_folders()
    assert not player.tree.item(str(album),'tags')
    assert not player.review_summary.cget('text').startswith('☁ ')
    # The playing identity takes precedence over a different selected row.
    player.current_track_id=album/'01.wav'
    # Exercise the same Tcl Quit callback used by Cocoa's application menu.
    root.tk.eval('namespace eval ::tk::mac {}')
    import ast
    from types import SimpleNamespace
    module=ast.parse(Path(sys.modules[Player.__module__].__file__).read_text(encoding='utf-8'))
    init=next(n for n in ast.walk(module) if isinstance(n,ast.FunctionDef) and n.name=='__init__' and any(isinstance(c,ast.Constant) and c.value=='::tk::mac::Quit' for c in ast.walk(n)))
    binding=next(n for n in init.body if isinstance(n,ast.If) and any(isinstance(c,ast.Constant) and c.value=='::tk::mac::Quit' for c in ast.walk(n)))
    exec(compile(ast.Module(body=[binding],type_ignores=[]),'<mac-quit-binding>','exec'),{'sys':SimpleNamespace(platform='darwin'),'root':root,'self':player})
    root.tk.call('::tk::mac::Quit')
    saved=json.loads((base/'cratelog_settings.json').read_text(encoding='utf-8'))
    assert saved['browse']['playing']=='01.wav'
    root=tk.Tk();player=Player(root);pump(root,lambda:player.album is not None,seconds=3)
    assert player.folder==album
    assert [player.tracks.set(i,'file') for i in player.tracks.selection()]==['01.wav']
    assert player.tracks.set(player.tracks.focus(),'file')=='01.wav'
    assert player.engine is None and player.playback_state=='stopped'
    player.close()
print('PASS: window dimensions, splitter, folder tree, filename selection, focus and scroll restored without autoplay')
