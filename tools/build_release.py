"""Build on the target OS and architecture; no cross-compilation."""
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
def run(args):subprocess.run(args,cwd=ROOT,check=True)
def build():
    if sys.platform not in ('win32','darwin'):raise SystemExit('Build on Windows or macOS.')
    sep=os.pathsep
    common=[sys.executable,'-m','PyInstaller','--noconfirm','--clean','--onedir','--paths',str(ROOT),'--specpath',str(ROOT/'build/specs')]
    data=['cratelog_turntable.frag','cratelog_spectrum.lua','web/cratelog-brand.json','web/assets','native','locales']
    args=common+['--name','Cratelog','--windowed']
    for name in data:args+=['--add-data',str(ROOT/name)+sep+str(Path(name).parent if Path(name).suffix else name)]
    args+=['--collect-all','pyglet']
    if sys.platform=='win32':args+=['--icon',str(ROOT/'web/assets/cratelog.ico')]
    else:
        from cratelog_platform import executable
        mpv=executable('mpv')
        if not mpv:raise SystemExit('Install mpv with Homebrew first.')
        args+=['--add-binary',str(Path(mpv).resolve())+sep+'runtime/mpv']
        native=ROOT/'runtime/macos'
        if not all((native/name).exists() for name in ('libcratelog.dylib','libcratelog_turntable.dylib','libcratelog_gestures.dylib')):raise SystemExit('Run bash tools/build_macos.sh first.')
        for lib in native.glob('*.dylib'):args+=['--add-binary',str(lib)+sep+'runtime/macos']
    run(args+[str(ROOT/'cratelog.py')])
    run(common+['--name','CratelogRender','--console','--collect-all','pyglet','--add-data',str(ROOT/'cratelog_turntable.frag')+sep+'.','--add-data',str(ROOT/'web/assets/cratelog.png')+sep+'web/assets',str(ROOT/'tools/turntable_worker.py')])
    if sys.platform=='darwin':
        output=ROOT/'dist/Cratelog.app';resources=output/'Contents/Resources'
    else:output=ROOT/'dist/Cratelog';resources=output/'_internal'
    shutil.copytree(ROOT/'dist/CratelogRender',resources/'worker',dirs_exist_ok=True)
    # Windows runtime is the installer's verified mpv archive, including its DLLs.
    if sys.platform=='win32':
        runtime=ROOT/'runtime/mpv'
        if not (runtime/'mpv.exe').exists():raise SystemExit('Run install_windows.bat first (mpv runtime missing).')
        shutil.copytree(runtime,resources/'runtime/mpv',dirs_exist_ok=True)
    for name in ['LICENSE','THIRD_PARTY_NOTICES.md','README.md','README.zh-CN.md','INSTALL.md','LANGUAGES.md','CONTRIBUTING.md','SECURITY.md']:
        shutil.copy2(ROOT/name,resources/name)
    shutil.copytree(ROOT/'docs',resources/'docs',dirs_exist_ok=True)
    # Preserve license texts from the actual installed wheels used in this build.
    import importlib.metadata
    for distribution in importlib.metadata.distributions():
        for file in distribution.files or []:
            if any(word in file.name.lower() for word in ('license','copying','notice')) and '.dist-info' in str(file):
                source=distribution.locate_file(file)
                if source.is_file():
                    dest=resources/'licenses'/distribution.metadata['Name']/str(file)
                    dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,dest)
    if sys.platform=='darwin':run(['codesign','--force','--deep','--sign','-',str(output)])
    (ROOT/'dist/build-environment.txt').write_text(subprocess.check_output([sys.executable,'-m','pip','freeze'],text=True),encoding='utf-8')
    if sys.platform=='win32':
        shutil.make_archive(str(ROOT/'dist/Cratelog-Windows'), 'zip', ROOT/'dist', 'Cratelog')
    else:
        run(['ditto','-c','-k','--sequesterRsrc','--keepParent',str(output),str(ROOT/'dist/Cratelog-macOS.zip')])
    print('Built:',output,'Architecture:',platform.machine())
    print('Unsigned build. Test playback and the turntable on the target machine before distributing.')
if __name__=='__main__':build()
