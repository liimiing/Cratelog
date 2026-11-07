"""Exercise batch editor against real WAV tags without starting playback."""
import sys,tempfile,wave,tkinter as tk
from tkinter import ttk
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from cratelog_player import Player
from cratelog_tags import read_tags,save_tags,stamp
with tempfile.TemporaryDirectory() as tmp:
    folder=Path(tmp)
    for i in range(2):
        p=folder/f'{i}.wav'
        with wave.open(str(p),'wb') as w:
            w.setnchannels(1);w.setsampwidth(2);w.setframerate(8000);w.writeframes(b'\0\0'*800)
        original=read_tags(p)
        save_tags(p,{'title':f'Title {i}','tracknumber':str(i+1),'artist':f'Artist {i}','album':'Old','comment':'Keep'},original,stamp(p))
    root=tk.Tk();root.withdraw()
    try:
        player=SimpleNamespace(root=root,folder=folder,album={'tracks':[{'filename':f'{i}.wav'} for i in range(2)]},current_file=None,playback_state='stopped',status=tk.StringVar(root),render=lambda:None,submit=lambda work,done:done(work()))
        Player.edit_tags_batch(player,(0,1))
        win=next(w for w in root.winfo_children() if isinstance(w,tk.Toplevel))
        assert 'title' not in win.tag_variables and 'tracknumber' not in win.tag_variables
        assert not any(v.get() for v in win.tag_enabled.values())
        win.tag_variables['album'].set('New');win.tag_enabled['album'].set(True)
        win.tag_variables['comment'].set('');win.tag_enabled['comment'].set(True)
        win.tag_variables['artist'].set('Must not write')
        next(w for w in win.winfo_children() if isinstance(w,ttk.Button) and int(w.grid_info()['column'])==1).invoke()
        for i in range(2):
            tags=read_tags(folder/f'{i}.wav')
            assert tags['album']=='New' and tags['comment']==''
            assert tags['title']==f'Title {i}' and tags['tracknumber']==str(i+1) and tags['artist']==f'Artist {i}'
        tree=ttk.Treeview(root)
        tree.insert('','end',iid='0');tree.insert('','end',iid='1');tree.selection_set('0','1')
        player.tracks=tree
        player.copy_track_info=lambda i:None
        player.edit_tags_batch=lambda indices:None
        player.edit_tags=lambda index:None
        with patch.object(tree,'identify_row',return_value='1'),patch('cratelog_player.tk.Menu.tk_popup'):
            Player.track_menu(player,SimpleNamespace(y=0,x_root=0,y_root=0))
        assert tree.selection()==('0','1')
        print('PASS: batch tags, untouched titles/numbers/unchecked fields, clearing fields and multiselection')
    finally:root.destroy()
