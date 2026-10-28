"""Real Tk/mpv controls and ID3, with temporary files and isolated settings."""
import json
import subprocess
import sys
import tempfile
import time
import tkinter as tk
from tkinter import ttk
from types import SimpleNamespace
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from cratelog_player import Player

def wait(root,predicate):
    end=time.monotonic()+12
    while time.monotonic()<end:
        root.update();time.sleep(.03)
        if predicate():return
    raise AssertionError('Player condition timed out')

with tempfile.TemporaryDirectory() as folder:
    folder=Path(folder)
    for name,options in [('01.mp3',['-metadata','title=ID3 Track','-metadata','artist=Tag Artist','-metadata','album=Tag Album']),('02.wav',[])]:
        subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','sine=frequency=440:duration=10',*options,'-y',str(folder/name)],check=True,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    root=tk.Tk()
    with patch('cratelog_player.read_json',return_value={'language':'zh_CN'}):player=Player(root)
    player.settings_path=folder/'settings.json';player.volume.set(0)
    try:
        player.configure();root.update();player.token.set('test-persisted-token-123456789012345')
        player.sub_font.set('Consolas');player.sub_size.set('96');player.sub_color.set('ffcc00')
        save=next(child for child in player.settings_window.winfo_children() if isinstance(child,(tk.Button,ttk.Button)) and child.cget('text')=='保存')
        root.update()
        assert save.winfo_y()+save.winfo_height()<=player.settings_window.winfo_height()
        save.invoke()
        saved=json.loads(player.settings_path.read_text(encoding='utf-8'))
        assert saved['token']==player.token.get()
        assert saved['subtitle']=={'font':'Consolas','size':96,'color':'#FFCC00'}
        assert set(player.transport_buttons)=={'previous','play','stop','next'}
        root.update()
        assert player.spectrum_panel.winfo_height()==116
        assert player.spectrum_host.winfo_height()==95
        for expected in ['列表循环','单曲循环','顺序播放']:
            player.mode_button.invoke();assert player.mode.get()==expected
        player.load_folder(folder);wait(root,lambda:player.album is not None)
        assert player.tracks.set('0','file')=='01.mp3'
        with patch.object(player.tracks,'identify_region',return_value='heading'),patch.object(player.tracks,'identify_column',return_value='#2'):
            player.track_double_click(SimpleNamespace(x=100,y=5))
            assert player.tracks.heading('file','text')=='ID3曲名'
            assert player.tracks.set('0','file')=='Tag Artist - ID3 Track'
            assert player.tracks.set('1','file')=='02.wav'
            assert player.playback_state=='stopped'
            player.track_double_click(SimpleNamespace(x=100,y=5))
            assert player.tracks.set('0','file')=='01.mp3'
        with patch('cratelog_player.webbrowser.open') as browser:
            player.album['metadata']={'音乐人':'Artist & Name','专辑名':'中文 Album'}
            player.douban_button.invoke()
            from urllib.parse import urlparse,parse_qs
            assert parse_qs(urlparse(browser.call_args.args[0]).query)['search_text']==['Artist & Name 中文 Album']
        with patch('cratelog_player.tk.Menu.tk_popup'),patch.object(player,'run_organizer_action') as action:
            player.show_album_menu()
            assert player.album_context_menu.index('end')==6
            player.album_context_menu.invoke(0)
            action.assert_called_once_with('view_details',folder)
        player.tracks.selection_set('0');player.transport_buttons['play'].invoke()
        wait(root,lambda:player.now.get()=='ID3 Track' and player.position.get()>.3)
        assert 'Tag Artist' in player.details.get() and 'Tag Album' in player.details.get()
        wait(root,lambda:'bps' in player.audio_details and 'Hz' in player.audio_details)
        assert player.audio_details.index('bps')<player.audio_details.index('Hz')
        assert str(player.transport_buttons['play'].cget('image')[0])==str(player.transport_icons['pause'])
        player.transport_buttons['play'].invoke();wait(root,lambda:player.playback_state=='paused')
        assert str(player.transport_buttons['play'].cget('image')[0])==str(player.transport_icons['play'])
        paused_at=player.position.get();player.transport_buttons['play'].invoke()
        wait(root,lambda:player.position.get()>paused_at+.2)
        player.next();wait(root,lambda:player.now.get()=='02.wav' and player.position.get()>.2)
        assert '16 bit' in player.audio_details,player.audio_details
        assert player.tracks.selection()==('1',)
        player.stop();assert str(player.transport_buttons['play'].cget('image')[0])==str(player.transport_icons['play'])
        player.engine.close();player.engine=None
        renamed=folder.with_name(folder.name+'-renamed')
        folder.rename(renamed);renamed.rename(folder)
    finally:player.close()
    root=tk.Tk()
    with patch('cratelog_player.read_json',return_value=saved):reopened=Player(root)
    assert reopened.token.get()==saved['token']
    assert reopened.settings['subtitle']==saved['subtitle']
    reopened.close()
print('PASS: token persisted/reloaded, 70% spectrum, mode cycle, ID3/fallback and combined play/pause/stop')
