import sys,tempfile,time,wave
from pathlib import Path
from unittest.mock import patch
import tkinter as tk
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from cratelog_player import Player
from cratelog_turntable import create_view,exchange_pose,track_menu_text
import math

def pump(root,check):
    end=time.monotonic()+8
    while time.monotonic()<end:
        root.update();time.sleep(.02)
        if check():return
    raise AssertionError('Album preparation timed out')

# The actual shader consumes this pose; tilted and moving discs stay above the deck.
for i in range(401,821):
    center,angle,radius=exchange_pose(i/1000)
    bottom=center[1]-radius*abs(math.cos(angle))-.009*abs(math.sin(angle))
    assert bottom>1.4,(i,bottom)
for i in range(820,1001):
    center,angle,radius=exchange_pose(i/1000)
    assert abs(angle-math.pi/2)<1e-8 and abs(center[0]+.53)<1e-8 and abs(center[2])<1e-8
assert abs(exchange_pose(1.)[0][1]-.444)<1e-8
line=track_menu_text(1,'Long name '*100,{'highlighted':True,'selected':True},35,len)
assert line.endswith(' ★ ✓') and len(line)<=35 and '…' in line

with tempfile.TemporaryDirectory() as tmp:
    base=Path(tmp);folders=[base/name for name in ('A','B','C')]
    for folder in folders:
        folder.mkdir()
        with wave.open(str(folder/'01.wav'),'wb') as audio:
            audio.setparams((1,2,8000,0,'NONE','not compressed'));audio.writeframes(b'\0\0'*8000)
    with patch('cratelog_player.BASE',base),patch('cratelog_player.state_dir',return_value=base):
        root=tk.Tk();p=Player(root)
        try:
            a,b,c=folders;p.set_root(base);p.load_folder(a);pump(root,lambda:p.album is not None)
            p.current_track_id=a/'01.wav';p.playback_state='playing';p.remember_playing_album()
            original=p.album;queue=[a/'01.wav'];p.playlist=queue
            v=create_view(p.track_area,p,lambda error:None);p.turntable=v;v.mounted_context=(a,original)
            v.pending_disc=(b,original)
            for folder in (b,c):
                p.load_folder(folder);pump(root,lambda:p.album is not None)
                assert v.pending_disc is None
            p.sync_turntable_album()
            assert p.folder==a and p.album is original and p.playlist is queue
            assert v.pending_disc[0]==c
            # Returning to list mode follows the folder selected in the tree.
            p.tree.selection_set(str(c));p.turntable_visible=True
            p.toggle_turntable();assert p.folder==c and not p.turntable_visible
            with patch.object(v,'show'):
                p.toggle_turntable()
            assert p.folder==a and v.pending_disc[0]==c
            p.turntable_visible=False
            # Repeated toggles retain the latest candidate, never resurrect B.
            p.sync_turntable_album();assert v.pending_disc[0]==c
            p.tree.selection_set(str(a));p.load_folder(a);pump(root,lambda:p.album is not None)
            p.sync_turntable_album();assert v.pending_disc is None
            # A new explicit playback in list mode becomes the mounted album.
            p.tree.selection_set(str(c));p.load_folder(c);pump(root,lambda:p.album is not None)
            p.current_track_id=c/'01.wav';p.remember_playing_album();p.sync_turntable_album()
            assert p.folder==c and v.pending_disc is None
            # Enter during an in-flight folder scan: invalidate it and stage B.
            p.tree.selection_set(str(b));p.load_folder(b);p.turntable_visible=True;p.sync_turntable_album()
            pump(root,lambda:v.pending_disc is not None)
            assert p.folder==c and v.pending_disc[0]==b
        finally:p.close()
print('PASS: exchange clearance, marker truncation, repeated mode/folder changes, new playback and in-flight scan')
