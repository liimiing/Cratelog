"""Real mpv/spectrum transitions across FLAC sample rates, isolated settings."""
import tempfile
import subprocess
import sys
import time
import tkinter as tk
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from cratelog_player import Player

def wait(root,predicate):
    deadline=time.monotonic()+10
    while time.monotonic()<deadline:
        root.update();time.sleep(.03)
        if predicate():return
    raise AssertionError('FLAC transition timed out')

with tempfile.TemporaryDirectory() as tmp:
    folder=Path(tmp)
    for i,rate in enumerate((44100,96000,48000)):
        subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i',f'sine=duration=8:sample_rate={rate}','-c:a','flac','-sample_fmt','s32','-y',str(folder/f'{i}.flac')],check=True,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    root=tk.Tk()
    with patch('cratelog_player.read_json',return_value={}):player=Player(root)
    player.settings_path=folder/'settings.json';player.volume.set(0)
    errors=[];player.status.trace_add('write',lambda *_:errors.append(player.status.get()) if '失败' in player.status.get() else None)
    try:
        player.load_folder(folder);wait(root,lambda:player.album is not None)
        for index in (0,1,2,0,2,1):
            player.tracks.selection_set(str(index));player.play_selected()
            wait(root,lambda:player.position.get()>.3 and player.duration>0)
            assert player.tracks.selection()==(str(index),)
        assert not errors,errors
        print('PASS: six live FLAC/spectrum switches across 44.1/48/96 kHz with buffering enabled')
    finally:player.close()
