"""Exercise real review controls with isolated settings."""
import sys
import tempfile
import tkinter as tk
from pathlib import Path
from unittest.mock import patch
from PIL import ImageGrab
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from cratelog_player import Player
from cratelog_widgets import HalfStarPicker
from cratelog_library import atomic_json, load_album

def descendants(widget):
    for child in widget.winfo_children():
        yield child
        yield from descendants(child)

with tempfile.TemporaryDirectory() as directory:
    folder=Path(directory)
    atomic_json(folder/'album_info.json',{'音乐人':'Carl Stone','专辑名':'Himalaya','出版年份':'2019','唱片厂牌':'Unseen\r\nWorlds'})
    root=tk.Tk()
    with patch('cratelog_player.read_json',return_value={}):player=Player(root)
    player.settings_path=folder/'settings.json'
    player.folder=folder;player.album=load_album(folder);player.render();root.update()
    assert player.album_subtitle.cget('text')=='2019 · Unseen Worlds'
    assert player.album_subtitle.cget('fg')=='#89939b'
    player.show_review();root.update()
    win=player.review_window
    picker=next(w for w in descendants(win) if isinstance(w,HalfStarPicker))
    picker.event_generate('<Button-1>',x=145,y=22);root.update()
    assert picker.variable.get()==3.5
    comment=next(w for w in descendants(win) if isinstance(w,tk.Text))
    comment.insert('1.0','音色细腻，值得重听。\n第三首是重点曲目。')
    root.update();win.lift();root.update()
    if '--screenshot' in sys.argv:
        ImageGrab.grab(bbox=(win.winfo_rootx(),win.winfo_rooty(),win.winfo_rootx()+win.winfo_width(),win.winfo_rooty()+win.winfo_height())).save(Path(__file__).resolve().parents[1]/'.qa/review-dialog.png')
    next(w for w in descendants(win) if isinstance(w,tk.Button) and w.cget('text')=='保存').invoke()
    saved=load_album(folder)
    assert saved['rating']==3.5 and saved['personal_comment'].startswith('音色细腻')
    player.show_review();root.update();win=player.review_window
    picker=next(w for w in descendants(win) if isinstance(w,HalfStarPicker))
    assert picker.variable.get()==3.5
    picker.step(10);assert picker.variable.get()==5
    picker.step(-10);assert picker.variable.get()==0
    next(w for w in descendants(win) if isinstance(w,tk.Button) and w.cget('text')=='取消').invoke()
    assert load_album(folder)['rating']==3.5
    player.close()
print('PASS: muted subtitle, half-star click, review save/reopen/cancel and bounds')
