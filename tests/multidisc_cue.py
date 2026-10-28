"""Real audio scanning, persistent CUE marks, and mpv segment controls."""
import sys
import tempfile
import time
import tkinter as tk
import wave
import subprocess
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from cratelog_library import load_album,save_album,CatalogIndex,payload
from cratelog_player import Player

def wait(root,predicate):
    deadline=time.monotonic()+12
    while time.monotonic()<deadline:
        root.update();time.sleep(.025)
        if predicate():return
    raise AssertionError('Playback timed out')

with tempfile.TemporaryDirectory() as tmp:
    rootdir=Path(tmp);folder=rootdir/'Artist - Album';folder.mkdir()
    mp3dir=rootdir/'untagged';mp3dir.mkdir()
    subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','sine=duration=2','-map_metadata','-1','-id3v2_version','0','-y',str(mp3dir/'plain.mp3')],check=True,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    mp3=load_album(mp3dir)
    assert 1.9<mp3['_durations']['plain.mp3']['seconds']<2.2
    for cd in ('CD10','CD2','CD1'):
        sub=folder/cd;sub.mkdir()
        with wave.open(str(sub/'disc.wav'),'wb') as audio:
            audio.setparams((1,2,8000,0,'NONE','not compressed'));audio.writeframes(b'\0\0'*80000)
    cue=folder/'CD1'/'disc.cue'
    cue.write_text('FILE "disc.wav" WAVE\n TRACK 01 AUDIO\n TITLE "First"\n INDEX 01 00:00:00\n TRACK 02 AUDIO\n TITLE "Second"\n INDEX 01 00:04:00\n',encoding='utf-8')
    assert load_album(folder)['tracks']==[]
    a=load_album(folder,recursive=True)
    ids=[t['filename'] for t in a['tracks']]
    assert ids==['CD1/disc.cue#track=01','CD1/disc.cue#track=02','CD2/disc.wav','CD10/disc.wav'],ids
    assert a['_durations'][ids[0]]['seconds']==4
    assert a['_durations'][ids[1]]['seconds']==6
    a['tracks'][1]['highlighted']=True;save_album(folder,a)
    cue.write_text(cue.read_text().replace('Second','Second renamed'),encoding='utf-8')
    assert load_album(folder)['tracks'][1]['highlighted']
    original=cue.read_text();cue.write_text(original.replace('disc.wav','missing.wav'))
    assert load_album(folder)['tracks'][0]['filename']=='CD1/disc.wav'
    cue.write_text(original+'FILE "disc.wav" WAVE\n')
    assert load_album(folder)['tracks'][0]['filename']=='CD1/disc.wav'
    cue.write_text(original.replace('00:04:00','00:03:90'))
    assert load_album(folder)['tracks'][0]['filename']=='CD1/disc.wav'
    cue.write_text(original)
    assert load_album(folder)['tracks'][1]['highlighted']
    assert all(not k.startswith('_') for k in payload(a))
    root=tk.Tk()
    with patch('cratelog_player.read_json',return_value={}):player=Player(root)
    player.settings_path=rootdir/'settings.json';player.volume.set(0)
    try:
        player.remote_catalog=CatalogIndex([{'id':a['id'],'artist':'Artist','album':'Album'}])
        player.load_folder(folder);wait(root,lambda:player.album is not None)
        player.tracks.selection_set('1');player.play_selected()
        wait(root,lambda:player.position.get()>.2 and player.duration>0)
        assert abs(player.duration-6)<.1,player.duration
        assert player.now.get()=='Second renamed',player.now.get()
        assert player.tracks.selection()==('1',)
        player.seek(2);wait(root,lambda:2<=player.position.get()<3)
        player.next();wait(root,lambda:player.now.get()=='disc.wav' and player.position.get()>.1)
        assert abs(player.duration-10)<.1,player.duration
        player.tracks.selection_set('0');player.play_selected()
        wait(root,lambda:player.now.get()=='Second renamed' and player.position.get()>.1)
        assert player.tracks.selection()==('1',)
    finally:player.close()
print('PASS: untagged audio duration, recursive ordering, CUE validation/mark stability, segment seek/end/next')
