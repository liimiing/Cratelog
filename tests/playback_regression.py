"""Actual mpv/Tk regression: pause/resume, selection, click seek and live FFT."""
import json
from pathlib import Path
import subprocess
import sys
import time
import tkinter as tk
from unittest.mock import patch

from PIL import Image, ImageChops, ImageGrab, ImageDraw
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from cratelog_player import Player

BASE = Path(__file__).resolve().parents[1]
QA = BASE / '.qa' / 'playback-regression'


def run():
    QA.mkdir(parents=True, exist_ok=True)
    cover = Image.new('RGB', (240,240), '#202428')
    art = ImageDraw.Draw(cover)
    art.rectangle((18,18,222,28),fill='#ff9c38')
    art.text((24,95), 'CRATELOG\nAUDIO TEST', fill='#ff9c38', spacing=12)
    cover.save(QA/'cover.png')
    for number, frequency in [(1, 440), (2, 4400)]:
        signal = (f'aevalsrc=0.15*sin(2*PI*({frequency}*t+20*t*t)):s=44100:d=20'
                  if number == 1 else f'sine=frequency={frequency}:duration=20:sample_rate=44100')
        subprocess.run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-f', 'lavfi',
                        '-i', signal,
                        '-y', str(QA/f'{number:02}.wav')], check=True,
                       creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    (QA/'album_info.json').write_text(json.dumps({'音乐人': 'Cratelog', '专辑名': '播放回归测试'}), encoding='utf-8')
    root = tk.Tk()
    with patch('cratelog_player.read_json', return_value={}):
        player = Player(root)
    player.settings_path = QA / 'settings.json'
    player.volume.set(0)
    errors = []
    def failed(*args, **kwargs): errors.append(str(args))

    def pump(seconds=.2):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            root.update()
            time.sleep(.01)

    def until(predicate, description, timeout=12):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            pump(.05)
            assert not errors, errors
            if predicate(): return
        raise AssertionError(f'{description}: {player.status.get()}, state={player.playback_state}, pos={player.position.get()}')

    def spectrum_frame(name):
        path = QA/name
        path.unlink(missing_ok=True)
        player.engine.command('screenshot-to-file', str(path), 'video')
        until(path.exists, 'spectrum screenshot')
        with Image.open(path) as im: return im.convert('RGB')

    try:
        with patch('cratelog_player.messagebox.showerror', side_effect=failed):
            player.set_root(QA)
            player.load_folder(QA)
            until(lambda: player.album is not None, 'load album')
            assert player.seekbar is player.spectrum_host
            assert player.volume_bar.winfo_width() == 200
            assert player.volume_bar.winfo_height() == player.transport_buttons['play'].winfo_height()
            assert all(not button.cget('text') and button.cget('image') for button in player.transport_buttons.values())
            player.volume_bar.event_generate('<ButtonPress-1>',x=100,y=10)
            player.volume_bar.event_generate('<ButtonRelease-1>',x=100,y=10)
            assert 49 < player.volume.get() < 51
            player.volume_bar.event_generate('<ButtonPress-1>',x=100,y=10)
            player.volume_bar.event_generate('<B1-Motion>',x=160,y=10)
            assert 79 < player.volume.get() < 81
            player.volume_bar.event_generate('<ButtonRelease-1>',x=100,y=10)
            assert 49 < player.volume.get() < 51
            player.volume_bar.event_generate('<ButtonPress-1>',x=0,y=10)
            player.volume_bar.event_generate('<ButtonRelease-1>',x=0,y=10)
            assert player.volume.get() == 0
            print('PASS: timeline integrated into spectrum, 200px volume matches button height, graphical controls')
            player.tracks.selection_set('0')
            player.play_selected()
            until(lambda: player.position.get() > 1 and player.duration > 15, 'start playback with spectrum')
            assert player.tracks.selection() == ('0',)
            first = spectrum_frame('spectrum-low.png')
            assert first.getbbox(), 'Spectrum is black'
            pump(.3)
            assert ImageChops.difference(first, spectrum_frame('spectrum-live.png')).getbbox(), 'Live spectrum did not animate'
            player.toggle_pause()
            assert player.pause_text.get() == '继续'
            pump(.4)
            position = player.position.get()
            paused = spectrum_frame('spectrum-paused.png')
            pump(.5)
            assert abs(player.position.get()-position) < .1, 'Paused position advanced'
            assert ImageChops.difference(paused, spectrum_frame('spectrum-still.png')).getbbox() is None, 'Paused spectrum advanced'
            player.play_or_resume()
            assert player.pause_text.get() == '暂停'
            until(lambda: player.position.get() > position + .3, 'Play resumes without restarting')
            player.toggle_pause(); pump(.25)
            position = player.position.get()
            player.toggle_pause()
            until(lambda: player.position.get() > position + .2, 'Pause button resumes')
            print('PASS: pause, Play resumes from same position, toggle resumes, spectrum freezes')
            player.next()
            until(lambda: player.position.get() > .5 and player.duration > 19 and player.current_file.name == '02.wav', 'next track')
            assert player.tracks.selection() == ('1',) and player.tracks.focus() == '1'
            second = spectrum_frame('spectrum-high.png')
            assert ImageChops.difference(first, second).getbbox(), 'FFT did not respond to frequency change'
            # Brightest frequency columns must move to the right for the higher tone.
            def peak_x(im):
                return max(range(im.width-2), key=lambda x: sum(sum(im.getpixel((x,y))) for y in range(im.height)))
            assert peak_x(second) > peak_x(first) + 50, (peak_x(first),peak_x(second))
            print('PASS: next track selects/focuses row and FFT responds to 440 Hz versus 4400 Hz')
            # Click down maps immediately, without waiting for mouse release.
            player.seekbar.event_generate('<ButtonPress-1>', x=round((player.seekbar.winfo_width()-1)*.6), y=10)
            assert 11.7 < player.position.get() < 12.3, (player.position.get(), player.duration, player.seekbar.position, player.seekbar.duration, player.seekbar.winfo_width(), player.seekbar.winfo_ismapped(), player.seekbar.dragging)
            player.seekbar.event_generate('<ButtonRelease-1>', x=round((player.seekbar.winfo_width()-1)*.6), y=10)
            until(lambda: 11.8 < player.position.get() < 14, 'exact click seek')
            player.toggle_pause(); pump(.3)
            player.seekbar.event_generate('<ButtonPress-1>', x=round((player.seekbar.winfo_width()-1)*.25), y=10)
            player.seekbar.event_generate('<ButtonRelease-1>', x=round((player.seekbar.winfo_width()-1)*.25), y=10)
            until(lambda: abs(player.position.get()-5) < .3, 'seek while paused')
            assert player.paused
            player.play_or_resume()
            until(lambda: player.position.get() > 5.3, 'resume after paused seek')
            print('PASS: immediate proportional click seek, paused seek and continued playback')
            # Exercise the native mpv mouse path, not just the enclosing Tk widget.
            player.toggle_pause(); pump(.3)
            player.engine.command('mouse', round((player.spectrum_host.winfo_width()-1)*.4), 30)
            player.engine.command('keydown', 'MBTN_LEFT')
            until(lambda: abs(player.position.get()-8) < .3, 'native spectrum click')
            player.engine.command('mouse', round((player.spectrum_host.winfo_width()-1)*.25), 30)
            player.engine.command('keyup', 'MBTN_LEFT')
            until(lambda: abs(player.position.get()-5) < .3, 'native spectrum drag release')
            assert player.paused
            overlay_path=QA/'spectrum-progress.png'; overlay_path.unlink(missing_ok=True)
            player.engine.command('screenshot-to-file',str(overlay_path),'window')
            until(overlay_path.exists,'native progress overlay')
            with Image.open(overlay_path) as screenshot:
                rgb=screenshot.convert('RGB')
                played=rgb.getpixel((round(rgb.width*.1),10))
                remaining=rgb.getpixel((round(rgb.width*.8),10))
                assert 10 <= max(played) <= 50 and max(remaining) < 5, (played,remaining)
            player.play_or_resume()
            until(lambda: player.position.get() > 5.3, 'resume after native spectrum drag')
            print('PASS: native spectrum click/drag while paused and muted played-area overlay')
            player.toggle_pause(); pump(.2)
            player.volume_bar.event_generate('<ButtonPress-1>',x=139,y=10)
            player.volume_bar.event_generate('<ButtonRelease-1>',x=139,y=10)
            root.lift(); pump(.2)
            assert player.toolbar.winfo_rooty() < player.spectrum_host.winfo_rooty()
            ImageGrab.grab(bbox=(root.winfo_rootx(), root.winfo_rooty(), root.winfo_rootx()+root.winfo_width(), root.winfo_rooty()+root.winfo_height())).save(QA/'player.png')
            player.volume_bar.event_generate('<ButtonPress-1>',x=0,y=10)
            player.volume_bar.event_generate('<ButtonRelease-1>',x=0,y=10)
            player.stop(); pump(.3)
            assert player.playback_state == 'stopped' and player.position.get() == 0
            player.play_or_resume()
            until(lambda: player.position.get() > .3, 'play after stop')
            player.next(-1)
            until(lambda: player.current_file.name == '01.wav' and player.duration > 19 and player.position.get() > .2, 'previous track')
            assert player.tracks.selection() == ('0',)
            player.seek(19.5)
            until(lambda: player.current_file is not None and player.current_file.name == '02.wav' and player.position.get() < 2,
                  'automatic next selects following row')
            assert player.tracks.selection() == ('1',)
            until(lambda: player.duration > 19 and player.position.get() > .2, 'second duration')
            player.mode.set('列表循环')
            player.seek(19.5)
            until(lambda: player.current_file is not None and player.current_file.name == '01.wav' and player.position.get() < 2,
                  'list loop selects first row')
            assert player.tracks.selection() == ('0',)
            print('PASS: previous, automatic next and list loop selection')
            player.open_organizer(); root.update()
            assert player.organizer.root.title().startswith('Cratelog')
            player.organizer.root.destroy()
            player.configure(); pump(.7)
            settings = player.settings_window
            assert settings.cget('bg') == '#202428'
            entries = [w for w in settings.winfo_children() if isinstance(w,tk.Entry)]
            assert len(entries) == 3 and all(w.cget('bg') == '#30363c' and w.cget('fg') == '#e7e7e7' for w in entries)
            ImageGrab.grab(bbox=(settings.winfo_rootx(),settings.winfo_rooty(),settings.winfo_rootx()+settings.winfo_width(),settings.winfo_rooty()+settings.winfo_height())).save(QA/'settings.png')
            settings.destroy()
            assert player.cover.bind('<Double-Button-1>')
            player.show_cover(); pump(.2)
            preview = player.cover_preview
            assert preview.winfo_exists() and preview.winfo_width() >= 240
            preview.geometry('640x480'); pump(.2)
            ImageGrab.grab(bbox=(preview.winfo_rootx(),preview.winfo_rooty(),preview.winfo_rootx()+preview.winfo_width(),preview.winfo_rooty()+preview.winfo_height())).save(QA/'cover-preview.png')
            preview.destroy()
            print('PASS: toolbar at top, dark settings after organizer, cover preview and resize')
            print('PASS: stop/restart and renamed organizer entry point')
    finally:
        player.close()


if __name__ == '__main__': run()
