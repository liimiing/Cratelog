"""Organizer actions must target the selected full path, not a duplicate name."""
import sys
import tempfile
import tkinter as tk
from tkinter import ttk
from pathlib import Path
from unittest.mock import Mock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from cratelog import CratelogOrganizer, LanguageManager, AlbumInfo

with tempfile.TemporaryDirectory() as tmp:
    root=tk.Tk();organizer=CratelogOrganizer.__new__(CratelogOrganizer)
    organizer.root=root;organizer.lang=LanguageManager()
    organizer.tree=ttk.Treeview(root,columns=('folder','artist','album','year','status','suggestion'))
    organizer.album_folders=[]
    first=Path(tmp)/'root'/'Same Album';second=Path(tmp)/'root'/'Nested'/'Same Album'
    first.mkdir(parents=True);second.mkdir(parents=True)
    for folder in (first,second):organizer.select_player_folder(folder)
    assert organizer.selected_folder_path()==second
    assert len(organizer.album_folders)==2
    info=AlbumInfo.from_dict({'音乐人':'Artist','专辑名':'Album'})
    organizer.album_folders=[(first,first.name,info),(second,second.name,info)]
    organizer.show_details_dialog=Mock();organizer.view_details()
    assert organizer.show_details_dialog.call_args.args[1]==second
    player=Mock();organizer.open_cratelog=Mock(return_value=player)
    organizer.sync_cratelog();player.sync_paths.assert_called_once_with([second])
    organizer.select_player_folder(first)
    assert organizer.selected_folder_path()==first and len(organizer.album_folders)==2
    root.destroy()
print('PASS: nested folder target, duplicate folder names, details and selected sync')
