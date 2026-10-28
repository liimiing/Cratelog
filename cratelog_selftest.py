"""Packaged smoke check; isolated settings, real Tk and renderer subprocess."""
import json
import os
from pathlib import Path
import tempfile
import traceback

def run(output):
    report={};player=None;client=None;root=None
    previous=os.environ.get('CRATELOG_STATE_DIR')
    try:
        with tempfile.TemporaryDirectory(prefix='cratelog-check-') as temp:
            os.environ['CRATELOG_STATE_DIR']=temp
            from cratelog_player import tk,Player
            from cratelog_platform import executable
            from cratelog_turntable import RenderClient
            root=tk.Tk();root.withdraw();player=Player(root);root.update()
            assert player.settings_path.parent==Path(temp)
            report['ui']=True
            report['mpv']=executable('mpv')
            if not report['mpv']:raise RuntimeError('mpv missing')
            if os.environ.get('CRATELOG_SKIP_GL_TEST')=='1':
                report['renderer']='skipped explicitly (headless CI)'
            else:
                client=RenderClient()
                client.requests.put(dict(width=320,height=240,rotation=0,lamp=1,pitch=0,progress=0,arm=1,lift=0,cover='',power=True,room_light=False))
                w,h,data=client.results.get(timeout=30)
                if (w,h)!=(320,240):raise RuntimeError(data.decode('utf-8',errors='replace'))
                assert len(data)==w*h*3
                report['renderer']=True
                client.close();client=None
            player.close();player=None;root=None
        report['ok']=True
    except Exception:
        report['ok']=False;report['error']=traceback.format_exc()
    finally:
        if client:client.close()
        if player:
            try:player.close()
            except Exception:pass
        elif root:
            try:root.destroy()
            except Exception:pass
        if previous is None:os.environ.pop('CRATELOG_STATE_DIR',None)
        else:os.environ['CRATELOG_STATE_DIR']=previous
    Path(output).write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    return 0 if report['ok'] else 1
