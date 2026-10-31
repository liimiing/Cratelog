"""Fullscreen layout restoration and staged sleeve exchange regression."""
import sys,tempfile
from pathlib import Path
from unittest.mock import Mock
import tkinter as tk
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from cratelog_player import Player
from cratelog_turntable import create_view
root=tk.Tk();root.withdraw()
header=tk.Frame(root);header.grid(row=0,column=0)
home=tk.Frame(root);home.grid(row=1,column=0)
p=Mock();p.album={'tracks':[{'filename':'old.wav'}]};p.remote_catalog.lookup.return_value=False
v=create_view(home,p,lambda error:None);v.pack(in_=home,fill='both',expand=True)
p.turntable=v;p.turntable_visible=True
try:
    v.paint_overlay=Mock()
    v.toggle_fullscreen()
    assert v.master is root and v.winfo_manager()=='place'
    assert root.grid_slaves()==[]
    assert v.place_info()['relwidth']=='1' or float(v.place_info()['relwidth'])==1.
    v.exit_fullscreen()
    assert v.winfo_manager()=='pack' and v.pack_info()['in']==home
    assert set(root.grid_slaves())=={header,home}
    with tempfile.TemporaryDirectory() as temp:
        a=Path(temp)/'A';b=Path(temp)/'B';c=Path(temp)/'C'
        for folder in (a,b,c):folder.mkdir()
        p.folder=a;p.current_track_id=a/'old.wav'
        p.tree.selection.return_value=(str(b),);Player.choose_folder(p)
        cb=p.submit.call_args.args[1]
        v.offer_folder(c);cc=p.submit.call_args.args[1]
        album={'tracks':[{'filename':'new.wav'}]}
        cb(album);assert v.pending_disc is None
        cc(album);assert v.pending_disc==(c,album)
        p.stop.assert_not_called();p.load_folder.assert_not_called()
        v.arm=1.;v.accept_disc();p.stop.assert_called_once()
        assert v.update_exchange(10)==0. and v.swap_started is None
        p.load_folder.assert_not_called()
        v.arm=0.;v.motion_lift=0.
        assert v.update_exchange(11)==0.
        assert 0.<v.update_exchange(12)<1.
        p.load_folder.assert_not_called()
        assert v.update_exchange(14)==-1.
        p.load_folder.assert_called_once_with(c,autoplay=True,prepared=album)
        assert v.swap_disc is None and v.pending_disc is None
finally:v.close();root.destroy()
print('PASS: turntable-only fullscreen, restored layout, stale candidate handling, arm parking and delayed album commit')
