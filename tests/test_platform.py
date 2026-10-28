import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock,patch
from cratelog_platform import SocketStream
from cratelog_player import MPV,parse_subtitle_form,preferred_subtitle,subtitle_candidates,subtitle_style
import cratelog_macos


class PlatformTests(unittest.TestCase):
    def test_macos_renderer_uses_same_core_graph_without_subprocess(self):
        process=Mock();process.poll.return_value=None;host=Mock()
        with patch('cratelog_player.sys.platform','darwin'),patch('cratelog_player.tempfile.mkdtemp',return_value='/tmp/cl-test'),patch('cratelog_player.subprocess.Popen') as popen,patch('cratelog_macos.NativeProcess',return_value=process) as native,patch('cratelog_player.threading.Thread.start'),patch('cratelog_player.shutil.rmtree'):
            engine=MPV('/opt/homebrew/bin/mpv',Mock(),host)
            target,options=native.call_args.args
            self.assertIs(target,host)
            self.assertEqual(options['vo'],'libmpv')
            self.assertIn('[aid1]asplit[ao]',options['lavfi-complex'])
            self.assertNotIn('wid',options)
            self.assertNotIn('no-video',options)
            self.assertNotIn('script',options)
            self.assertNotIn('scripts-append',options)
            self.assertIsInstance(options['scripts'],list)
            self.assertTrue(options['scripts'][0].endswith('cratelog_spectrum.lua'))
            self.assertEqual(options['video-timing-offset'],'0')
            self.assertEqual(options['sub-font'],'sans-serif')
            self.assertEqual(options['sub-font-size'],'55')
            self.assertEqual(options['sub-color'],'#FFFFFF')
            self.assertEqual(options['sub-auto'],'no')
            self.assertEqual(options['sid'],'no')
            popen.assert_not_called()
            engine.close();process.terminate.assert_called_once()

    def test_native_geometry_is_relative_and_cleanup_is_idempotent(self):
        lib=Mock();lib.cratelog_create.return_value=123
        tk_lib=Mock();tk_lib.TkMacOSXGetRootControl.return_value=456
        root=Mock();root.winfo_id.return_value=789
        root.winfo_rootx.return_value=100;root.winfo_rooty.return_value=200
        host=Mock();host.winfo_toplevel.return_value=root
        host.winfo_rootx.return_value=400;host.winfo_rooty.return_value=220
        host.winfo_width.return_value=600;host.winfo_height.return_value=100
        host.winfo_viewable.return_value=True
        with patch.object(cratelog_macos.ctypes,'CDLL',side_effect=[lib,tk_lib]),patch('cratelog_macos.Path.is_file',return_value=True),patch('cratelog_macos.check_bridge'):
            native=cratelog_macos.NativeProcess(host,{})
            lib.cratelog_geometry.assert_called_once_with(123,300,20,600,100,1)
            native.reposition();self.assertEqual(lib.cratelog_geometry.call_count,1)
            # Fullscreen/titlebar changes parent height while the top plot's
            # x/y/width/height remain unchanged (917 -> 949 in the Mac trace).
            root.winfo_height.return_value=949
            native.reposition()
            self.assertEqual(lib.cratelog_geometry.call_count,2)
            lib.cratelog_geometry.assert_called_with(123,300,20,600,100,1)
            host.winfo_width.return_value=800;native.reposition()
            lib.cratelog_geometry.assert_called_with(123,300,20,800,100,1)
            native.terminate();native.terminate()
            lib.cratelog_destroy.assert_called_once_with(123)
            self.assertEqual(native.poll(),0)

    def test_bridge_rejects_old_or_stale_binary(self):
        import hashlib
        source=Mock();source.read_bytes.return_value=b'current source'
        with self.assertRaisesRegex(RuntimeError,'缺少版本标识'):
            cratelog_macos.check_bridge(object(),'library',source)
        lib=Mock();lib.cratelog_bridge_version.return_value=2
        lib.cratelog_source_sha256.return_value=b'old source'
        with self.assertRaisesRegex(RuntimeError,'当前源码'):
            cratelog_macos.check_bridge(lib,'library',source)
        lib.cratelog_source_sha256.return_value=hashlib.sha256(b'current source').hexdigest().encode()
        cratelog_macos.check_bridge(lib,'library',source)

    def test_socket_stream_sends_complete_commands(self):
        client=Mock();client.makefile.return_value=io.BytesIO(b'{"event":"file-loaded"}\n')
        stream=SocketStream(client);command=b'x'*100000
        stream.write(command);client.sendall.assert_called_once_with(command)
        self.assertEqual(stream.readline(),b'{"event":"file-loaded"}\n')
        stream.close();client.close.assert_called_once()
    def test_macos_uses_socket_without_native_window_embedding(self):
        process=Mock();process.poll.return_value=None;events=Mock();client=Mock()
        client.makefile.return_value=io.BytesIO()
        with patch('cratelog_player.os.name','posix'),patch('cratelog_player.sys.platform','darwin'),patch('cratelog_player.tempfile.mkdtemp',return_value='/tmp/cl-test'),patch('cratelog_player.subprocess.Popen',return_value=process) as popen,patch('cratelog_player.threading.Thread.start'),patch('cratelog_player.socket.socket',return_value=client),patch('cratelog_player.socket.AF_UNIX',1,create=True),patch('cratelog_player.shutil.rmtree'):
            engine=MPV('/opt/homebrew/bin/mpv',events)
            args=popen.call_args.args[0]
            self.assertIn('--input-ipc-server=/tmp/cl-test/mpv.sock',args)
            self.assertIn('--no-video',args)
            self.assertFalse(any(arg.startswith('--wid=') for arg in args))
            stream=engine.open_pipe();client.connect.assert_called_once_with('/tmp/cl-test/mpv.sock')
            stream.close();engine.close()

    def test_subtitle_style_reaches_mpv_and_rejects_bad_input(self):
        self.assertEqual(subtitle_style({'font':'  Consolas\n','size':'96','color':'ffcc00'}),
                         {'font':'Consolas','size':96,'color':'#FFCC00'})
        self.assertEqual(subtitle_style({'size':'nope','color':'blue'})['color'],'#FFFFFF')
        self.assertEqual(parse_subtitle_form('Arial', '80', '#112233')['size'],80)
        with self.assertRaisesRegex(ValueError,'字高'):parse_subtitle_form('', '7', '#FFFFFF')
        with self.assertRaisesRegex(ValueError,'#RRGGBB'):parse_subtitle_form('', '40', 'red')
        process=Mock();process.poll.return_value=None
        with patch('cratelog_player.sys.platform','win32'),patch('cratelog_player.os.name','nt'),patch('cratelog_player.subprocess.Popen',return_value=process) as popen,patch('cratelog_player.threading.Thread.start'):
            engine=MPV('mpv',Mock(),42,{'font':'Consolas','size':96,'color':'#FFCC00'})
            args=popen.call_args.args[0]
            self.assertIn('--sub-auto=no',args)
            self.assertIn('--sid=no',args)
            self.assertIn('--sub-font=Consolas',args)
            self.assertIn('--sub-font-size=96',args)
            self.assertIn('--sub-color=#FFCC00',args)
            self.assertIn('--wid=42',args)
            engine.close()

    def test_exact_subtitle_is_preferred_and_menu_can_select_another(self):
        import tkinter as tk
        from cratelog_player import Player
        root=tk.Tk(); player=None
        with tempfile.TemporaryDirectory() as folder:
            folder=Path(folder)
            (folder/'song.en.srt').write_text('en',encoding='utf-8')
            (folder/'song.SRT').write_text('zh',encoding='utf-8')
            (folder/'song.ass').write_text('ass',encoding='utf-8')
            (folder/'other.srt').write_text('no',encoding='utf-8')
            (folder/'notes.txt').write_text('x',encoding='utf-8')
            audio=folder/'song.flac'
            self.assertEqual(preferred_subtitle(audio).name.casefold(),'song.srt')
            self.assertEqual([path.name.casefold() for path in subtitle_candidates(audio)],
                             ['song.srt','song.ass','song.en.srt'])
            try:
                with patch('cratelog_player.read_json', return_value={'language':'zh_CN'}):
                    player=Player(root)
                player.settings_path=folder/'settings.json'
                player.current_file=audio
                player.playback_state='playing'
                player.engine=Mock(); player.engine.process.poll.return_value=None
                player.attach_preferred_subtitle()
                player.engine.command.assert_called_once_with('sub-add', str(preferred_subtitle(audio)), 'select')
                with patch('cratelog_player.tk.Menu.tk_popup'):
                    player.show_subtitle_menu(10,10)
                menu=player.subtitle_menu
                self.assertEqual([menu.entrycget(i,'label').casefold() for i in range(menu.index('end')+1)],
                                 ['song.srt','song.ass','song.en.srt'])
                menu.invoke(2)
                player.engine.command.assert_called_with('sub-add', str(folder/'song.en.srt'), 'select')
                player.remember_subtitles([{'id':3,'type':'sub','external-filename':str(folder/'song.en.srt')}])
                player.subtitle_sid=3
                player.engine.command.reset_mock()
                menu.invoke(2)
                player.engine.command.assert_called_once_with('set_property','sid',3)
                preferred_subtitle(audio).unlink(); (folder/'song.ass').unlink()
                self.assertIsNone(preferred_subtitle(audio))
                player.engine.command.reset_mock()
                player.attach_preferred_subtitle()
                player.engine.command.assert_not_called()
                player.current_file=None
                with patch('cratelog_player.tk.Menu.tk_popup'):
                    player.show_subtitle_menu(10,10)
                self.assertEqual(player.subtitle_menu.entrycget(0,'label'),'没有匹配的字幕')
                self.assertEqual(player.subtitle_menu.entrycget(0,'state'),'disabled')
            finally:
                if player:
                    player.engine=None
                    player.close()
                else: root.destroy()

if __name__=='__main__':unittest.main()
