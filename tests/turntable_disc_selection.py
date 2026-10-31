"""Real Tk tests for deferred disc selection, stale callbacks and fullscreen."""
import sys
import tempfile
import tkinter as tk
from pathlib import Path
from unittest.mock import Mock,patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from cratelog_player import Player
from cratelog_turntable import create_view,pending_disc_hit,camera_eye
root=tk.Tk();root.withdraw()
with tempfile.TemporaryDirectory() as temp:
    a=Path(temp)/'A';b=Path(temp)/'B';c=Path(temp)/'C'
    for folder in (a,b,c):folder.mkdir()
    p=Mock();p.folder=a;p.album={'tracks':[{'filename':'original.wav'}]};p.current_track_id=a/'original.wav'
    p.turntable_visible=True;p.remote_catalog.lookup.return_value=False
    p.playback_state='playing';p.position.get.return_value=12.
    v=create_view(root,p,lambda error:None);p.turntable=v
    try:
        p.tree.selection.return_value=(str(b),)
        Player.choose_folder(p)
        p.load_folder.assert_not_called();p.stop.assert_not_called()
        assert p.folder==a and p.current_track_id==a/'original.wav'
        callback_b=p.submit.call_args.args[1]
        p.tree.selection.return_value=(str(c),);Player.choose_folder(p)
        callback_c=p.submit.call_args.args[1]
        album_b={'tracks':[{'filename':'b.wav'}]};album_c={'tracks':[{'filename':'c.wav'}]}
        callback_b(album_b);assert v.pending_disc is None
        callback_c(album_c);assert v.pending_disc==(c,album_c)
        p.stop.assert_not_called();p.load_folder.assert_not_called()
        v.accept_disc()
        p.stop.assert_called_once();p.load_folder.assert_called_once_with(c,autoplay=True,prepared=album_c)
        assert v.pending_disc is None
        # Selecting the current folder cancels an unaccepted candidate.
        v.offer_folder(b);callback=p.submit.call_args.args[1];v.offer_folder(a);callback(album_b)
        assert v.pending_disc is None
        v.paint_overlay=Mock()
        v.toggle_fullscreen();assert v.fullscreen and bool(root.attributes('-fullscreen'))
        v.exit_fullscreen();assert not v.fullscreen and not bool(root.attributes('-fullscreen'))
        # At least part of the visible candidate can be selected; empty corners cannot.
        eye=camera_eye()
        assert any(pending_disc_hit(x,y,960,640,eye) for x in range(400,750,20) for y in range(30,230,20))
        assert not pending_disc_hit(0,639,960,640,eye)
    finally:v.close();root.destroy()
print('PASS: browse preserves playing disc; stale previews ignored; explicit swap; fullscreen and picking')
