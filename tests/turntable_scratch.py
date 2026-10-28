import sys
import tkinter as tk
from pathlib import Path
from unittest.mock import Mock,patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from cratelog_turntable import create_view,SPINDLE
root=tk.Tk();root.withdraw()
p=Mock();p.current_track_id=Path('track.wav');p.playback_state='playing';p.position.get.return_value=30.;p.duration=120.
v=create_view(root,p,lambda message:None);v.needle_ready=True;v.velocity=100/3
try:
    v.begin_scratch((SPINDLE[0]+1.,0.))
    assert v.scratch['velocity']>0
    v.after_cancel(v.scratch_job);v.scratch_job=None
    v.scratch['started']-=1.;v.scratch_tick()
    assert v.scratch['velocity']==0.
    p.control.assert_any_call('set_property','pause',True)
    with patch('cratelog_turntable.deck_point',return_value=(SPINDLE[0],-1.)):
        v.scratch_drag(Mock(x=0,y=0))
    assert v.scratch['velocity']<0 and v.scratch['position']<30.
    v.after_cancel(v.scratch_job);v.scratch_job=None;v.scratch_tick()
    p.control.assert_any_call('set_property','play-direction','backward')
    v.end_scratch()
    assert v.scratch is None and v.scratch_job is None
    p.control.assert_any_call('set_property','play-direction','forward')
    p.set_paused.assert_called_with(False)
    p.playback_state='paused';v.begin_scratch((SPINDLE[0]+1.,0.));v.end_scratch()
    p.set_paused.assert_called_with(True)
    v.begin_scratch((SPINDLE[0]+1.,0.));p.set_paused.reset_mock();v.end_scratch(False)
    p.set_paused.assert_not_called()
finally:
    v.close();root.destroy()
print('PASS: short brake, reverse drag, release restore, paused state and cancellation')
