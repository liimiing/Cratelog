import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from cratelog_player import Player

class AudioGateTests(unittest.TestCase):
    def player(self):
        p=Mock()
        p.engine=Mock();p.turntable_visible=True
        p.turntable=Mock(needle_ready=False)
        p.playback_state='paused';p.lastfm_listening=None
        return p

    def test_resume_waits_for_needle_and_user_pause_cancels(self):
        p=self.player()
        Player.set_paused(p,False)
        p.turntable.defer_audio.assert_called_once()
        p.control.assert_called_with('set_property','pause',True)
        self.assertEqual(p.playback_state,'paused')
        p.turntable.needle_ready=True
        Player.set_paused(p,False)
        p.control.assert_called_with('set_property','pause',False)
        Player.set_paused(p,True)
        p.turntable.cancel_audio.assert_called_once()

    def test_load_is_paused_before_it_can_emit_audio(self):
        with tempfile.TemporaryDirectory() as folder:
            file=Path(folder)/'test.wav';file.touch()
            for continuous,ready,expected in ((False,False,True),(False,True,True),(True,True,False)):
                p=self.player();p.turntable.needle_ready=ready
                p.playlist=[file];p.play_index=0;p.playlist_sources={}
                p.lastfm.enabled.return_value=False
                with patch('cratelog_player.messagebox.showerror') as error:
                    Player.play(p,continuous=continuous)
                    error.assert_not_called()
                commands=[c.args for c in p.engine.command.call_args_list]
                load=next(i for i,c in enumerate(commands) if c[0]=='loadfile')
                self.assertEqual(commands[load+1],('set_property','pause',expected))
                if expected:
                    self.assertEqual(commands[load-1],('set_property','pause',True))
                    self.assertEqual(commands[load][-1]['pause'],'yes')

    def test_stop_cancels_pending_resume(self):
        p=self.player();Player.stop(p)
        p.turntable.cancel_audio.assert_called_once()
        p.control.assert_called_once_with('stop')

if __name__=='__main__':unittest.main()
