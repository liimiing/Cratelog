"""Build a Finder launcher beside the project, using its existing virtualenv."""
import plistlib
from PIL import Image
from pathlib import Path

LAUNCHER = r'''#!/bin/bash
set -u
cd "$(dirname "$0")/../../.." || exit 1
export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"
log_dir="$HOME/Library/Logs/Cratelog"
mkdir -p "$log_dir" || exit 1
exec >>"$log_dir/startup.log" 2>&1
if [[ ! -x .venv-macos/bin/python ]]; then
    /usr/bin/osascript -e 'display alert "Cratelog" message "请先在项目目录运行 bash install_macos.sh，建立 Mac Python 环境。" as critical'
    exit 1
fi
.venv-macos/bin/python cratelog.py
status=$?
if [[ $status -ne 0 ]]; then
    /usr/bin/osascript -e 'display alert "Cratelog 启动失败" message "错误记录：~/Library/Logs/Cratelog/startup.log" as critical'
fi
exit "$status"
'''


def build(project):
    project=Path(project)
    app=project/'Cratelog.app'
    contents=app/'Contents'
    executable=contents/'MacOS'/'Cratelog'
    executable.parent.mkdir(parents=True,exist_ok=True)
    executable.write_bytes(LAUNCHER.encode('utf-8'))
    executable.chmod(0o755)
    resources=contents/'Resources'
    resources.mkdir(parents=True,exist_ok=True)
    with Image.open(project/'web'/'assets'/'cratelog.png') as source:
        icon=source.convert('RGBA').resize((1024,1024),Image.Resampling.LANCZOS)
        icon.save(resources/'Cratelog.icns',format='ICNS')
    info={'CFBundleExecutable':'Cratelog','CFBundleName':'Cratelog',
          'CFBundleDisplayName':'Cratelog','CFBundleIdentifier':'com.hitlike.cratelog',
          'CFBundlePackageType':'APPL','CFBundleInfoDictionaryVersion':'6.0',
          'NSHighResolutionCapable':True,'CFBundleIconFile':'Cratelog.icns'}
    (contents/'Info.plist').write_bytes(plistlib.dumps(info))
    return app


if __name__=='__main__':
    print(build(Path(__file__).resolve().parents[1]))
