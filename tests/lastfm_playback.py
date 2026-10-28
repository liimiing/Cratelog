"""Real-time mpv regression: a tagged 36-second track scrobbles after 18s.
Last.fm calls are mocked; nothing is sent to a real account.
"""
import sys
import tempfile
import subprocess
import time
import tkinter as tk
from pathlib import Path
from unittest.mock import Mock,patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from cratelog_player import Player

with tempfile.TemporaryDirectory() as tmp:
    folder=Path(tmp)
    subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','sine=duration=36','-metadata','title=Regression Track','-metadata','artist=Test Artist','-y',str(folder/'track.mp3')],check=True,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    root=tk.Tk()
    with patch('cratelog_player.read_json',return_value={}):player=Player(root)
    player.settings_path=folder/'settings.json';player.lastfm.close()
    player.lastfm=Mock();player.lastfm.enabled.return_value=True;player.volume.set(0)
    try:
        player.load_folder(folder)
        deadline=time.monotonic()+5
        while player.album is None and time.monotonic()<deadline:root.update();time.sleep(.02)
        player.play_selected();deadline=time.monotonic()+25
        while not player.lastfm.enqueue.called and time.monotonic()<deadline:root.update();time.sleep(.10)
        assert player.lastfm.enqueue.call_count==1,(player.position.get(),player.lastfm_listening.listened,player.status.get())
        assert 18<=player.lastfm_listening.listened<22,player.lastfm_listening.listened
        assert player.lastfm.now.call_count==1
        assert player.lastfm.enqueue.call_args.args[0]['track']=='Regression Track'
        print('PASS: real mpv playback reaches scrobble threshold once; no Last.fm network calls')
    finally:player.close()
