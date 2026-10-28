"""Folder selection reads disk; refresh performs one catalog request."""
import sys
import tempfile
import tkinter as tk
from pathlib import Path
from unittest.mock import Mock,patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from cratelog_player import Player
from cratelog_library import CatalogIndex

with tempfile.TemporaryDirectory() as tmp,patch('cratelog_player.BASE',Path(tmp)):
    base=Path(tmp);first=base/'One';second=base/'Two';first.mkdir();second.mkdir()
    root=tk.Tk();player=Player(root);root.update()
    player.url.set('https://example.test/api');player.token.set('test-token')
    remote=Mock();remote.catalog.return_value=CatalogIndex()
    player.remote=Mock(return_value=remote)
    player.submit=lambda work,done:done(work())
    player.set_root(base);remote.reset_mock()
    for folder in (first,second,first):player.load_folder(folder)
    assert not remote.mock_calls
    player.refresh_root();remote.catalog.assert_called_once_with();remote.fetch.assert_not_called()
    player.close()
print('PASS: repeated folder selection makes no remote requests; refresh queries once')
