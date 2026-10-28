"""Run the actual Tk windows and capture the player for visual inspection."""
import sys
import time
from pathlib import Path
import tkinter as tk
from PIL import ImageGrab
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from cratelog_player import Player

base=Path(__file__).resolve().parents[1]
root=tk.Tk()
player=Player(root)
player.settings_path=base/'.qa/ui-settings.json'
fixture=sorted((base/'.qa').glob('album-*'))[-1]
player.set_root(fixture.parent)
player.load_folder(fixture)
deadline=time.monotonic()+10
while player.album is None and time.monotonic()<deadline:
    root.update();time.sleep(.05)
assert player.album is not None
player.tracks.selection_set('0')
player.album['tracks'][0].update(selected=False,highlighted=False)
player.mark('selected');player.mark('highlighted')
player.rating.set('4');player.save_rating()
root.update()
root.lift()
root.update()
ImageGrab.grab(bbox=(root.winfo_rootx(),root.winfo_rooty(),root.winfo_rootx()+root.winfo_width(),root.winfo_rooty()+root.winfo_height())).save(base/'.qa/player.png')
player.open_organizer();root.update()
assert player.organizer.root.winfo_exists()
player.organizer.root.destroy()
player.close()
print('PASS: player layout, album load, marks, rating and original organizer window')
