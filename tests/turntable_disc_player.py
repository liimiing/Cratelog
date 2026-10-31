import sys,tempfile,time,wave
from pathlib import Path
from unittest.mock import patch
import tkinter as tk
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from cratelog_player import Player
from cratelog_turntable import create_view

def pump(root,check):
    end=time.monotonic()+5
    while time.monotonic()<end:
        root.update();time.sleep(.02)
        if check():return
    raise AssertionError('Timed out loading candidate album')

with tempfile.TemporaryDirectory() as temp:
    base=Path(temp);a=base/'A';b=base/'B'
    for folder in (a,b):
        folder.mkdir()
        with wave.open(str(folder/'01.wav'),'wb') as audio:
            audio.setparams((1,2,8000,0,'NONE','not compressed'));audio.writeframes(b'\0\0'*8000)
    with patch('cratelog_player.BASE',base),patch('cratelog_player.state_dir',return_value=base):
        root=tk.Tk();p=Player(root)
        try:
            p.set_root(base);p.load_folder(a);pump(root,lambda:p.album is not None)
            v=create_view(p.track_area,p,lambda error:None);p.turntable=v;p.turntable_visible=True
            p.current_track_id=a/'01.wav';p.playback_state='playing'
            old_album=p.album;old_playlist=list(p.album_playlist)
            v.offer_folder(b);pump(root,lambda:v.pending_disc is not None)
            assert p.folder==a and p.album is old_album and p.album_playlist==old_playlist
            assert p.current_track_id==a/'01.wav' and p.playback_state=='playing'
            with patch.object(p,'play_selected') as play:
                v.accept_disc();play.assert_called_once()
            assert p.folder==b and p.album is not old_album
            assert p.album_playlist==[b/'01.wav']
        finally:p.close()
print('PASS: real Player keeps current album/queue during preview and installs prepared album on acceptance')
