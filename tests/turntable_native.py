"""Exercise native view routing with a real Tk canvas and a mocked Cocoa bridge."""
import sys
import tkinter as tk
from pathlib import Path
from unittest.mock import Mock,patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from cratelog_turntable import create_view
root=tk.Tk();root.withdraw()
p=Mock();p.album={'tracks':[]};p.current_track_id=None
view=create_view(root,p,lambda error:(_ for _ in ()).throw(AssertionError(error)))
view.winfo_viewable=lambda:True
view.winfo_width=lambda:960;view.winfo_height=lambda:640
view.state=lambda:{}
bridge=Mock();bridge.render.return_value=True
try:
    with patch('cratelog_turntable.sys.platform','darwin'),patch('cratelog_turntable_native.NativeTurntable',return_value=bridge),patch('cratelog_turntable.RenderClient') as compatibility:
        view.show()
        assert view.native is bridge
        compatibility.assert_not_called()
        bridge.hud.assert_called_once()
        for _ in range(3):
            view.after_cancel(view.job);view.job=None;view.tick()
        assert bridge.render.call_count==4
        bridge.hud.assert_called_once() # No per-frame RGBA upload.
        view.pad_visible=True;view.paint_overlay()
        entries=bridge.hud.call_args.args[1]
        assert any('×' in entry[2] for entry in entries)
        assert {'‹','⌃','↺','›','⌄'} <= {entry[2] for entry in entries}
        bridge.hud.reset_mock()
        view.room_light=False;view.paint_overlay()
        assert bridge.hud.call_count==1
        view.resume_pending=True;view.needle_ready=True
        view.after_cancel(view.job);view.job=None;view.tick()
        p.set_paused.assert_called_with(False)
        view.hide();bridge.geometry.assert_called_with(False)
        view.show();assert view.native is bridge
        bridge.render.side_effect=RuntimeError('simulated GPU failure')
        view.after_cancel(view.job);view.job=None;view.tick()
        assert view.native is None and view.native_failed
        bridge.close.assert_called_once();compatibility.assert_called_once()
finally:
    view.close();root.destroy()
print('PASS: native routing, cached HUD, landing gate, hide/show, GPU failure fallback')
