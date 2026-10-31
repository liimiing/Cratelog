import sys
from pathlib import Path
from unittest.mock import Mock
import tkinter as tk
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from cratelog_turntable import create_view
root=tk.Tk();root.withdraw()
p=Mock();p.folder=Path('/album');p.current_track_id=p.folder/'b.wav';p.playback_state='playing'
p.album={'tracks':[{'filename':'a.wav'},{'filename':'b.wav'}],'_durations':{'a.wav':{'seconds':60},'b.wav':{'seconds':180}}}
p.position.get.return_value=90.;p.duration=180.
v=create_view(root,p,lambda error:None)
try:
    v.power=False;v.motion_lift=1.;v.lift=1.;v.transition=1.;v.resume_pending=True
    old=Mock();v.client=old;v.pending=True
    v.sync_playing_view()
    assert v.arm==1. and v.groove==.625 and v.identity=='b.wav'
    assert v.lift==v.motion_lift==v.transition==0.
    assert v.needle_ready and v.power and not v.resume_pending
    old.close.assert_called_once();assert v.client is None and not v.pending
    p.stop.assert_not_called();p.set_paused.assert_not_called();p.control.assert_not_called()
    frame=v.state();assert frame['arm']==1. and frame['lift']==0.
    p.playback_state='stopped';v.arm=0.;v.sync_playing_view();assert v.arm==0.
finally:v.close();root.destroy()
print('PASS: entering during playback positions the needle immediately without audio commands or stale frames')
