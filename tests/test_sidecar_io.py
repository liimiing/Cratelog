"""Portable state stays on disk; browsing never writes it."""
import json
import sys
import tempfile
import unittest
import wave
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from cratelog_library import load_album, save_album, direct_json, SCAN_CACHE, SESSION_IDS

class SidecarTests(unittest.TestCase):
    def test_readonly_load_and_portable_edits(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp)/'Album';folder.mkdir()
            with wave.open(str(folder/'track.wav'),'wb') as audio:
                audio.setparams((1,2,8000,0,'NONE','not compressed'))
                audio.writeframes(b'\0\0'*8000)
            with patch('cratelog_library.atomic_json',side_effect=AssertionError('browse wrote JSON')):
                first=load_album(folder);second=load_album(folder)
            self.assertEqual(first['id'],second['id'])
            self.assertFalse((folder/'.cratelog.json').exists())
            first['rating']=4.5;first['personal_comment']='portable review'
            first['tracks'][0]['highlighted']=True
            with patch('cratelog_library.os.replace',side_effect=AssertionError('rename used')):
                save_album(folder,first)
            path=folder/'.cratelog.json';before=path.read_bytes();stamp=path.stat().st_mtime_ns
            loaded=load_album(folder);save_album(folder,loaded)
            self.assertEqual(path.read_bytes(),before)
            self.assertEqual(path.stat().st_mtime_ns,stamp)
            self.assertNotIn('_durations',json.loads(before))
            moved=folder.with_name('Moved');folder.rename(moved)
            SCAN_CACHE.clear();SESSION_IDS.clear()
            loaded=load_album(moved)
            self.assertEqual(loaded['id'],first['id'])
            self.assertEqual(loaded['rating'],4.5)
            self.assertEqual(loaded['personal_comment'],'portable review')
            self.assertTrue(loaded['tracks'][0]['highlighted'])
            self.assertEqual((moved/'.cratelog.json').read_bytes(),before)

    def test_local_album_info_enables_recursive_tracks(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp)
            for name in ('CD10','CD2','CD1','.hidden'):
                sub=folder/name;sub.mkdir()
                with wave.open(str(sub/'disc.wav'),'wb') as audio:
                    audio.setparams((1,2,8000,0,'NONE','not compressed'))
                    audio.writeframes(b'\0\0'*16000)
            self.assertEqual(load_album(folder)['tracks'],[])
            info=folder/'album_info.json';info.write_text('{}',encoding='utf-8')
            (folder/'CD1'/'disc.cue').write_text('FILE "disc.wav" WAVE\n TRACK 01 AUDIO\n TITLE "One"\n INDEX 01 00:00:00\n TRACK 02 AUDIO\n TITLE "Two"\n INDEX 01 00:01:00\n',encoding='utf-8')
            album=load_album(folder)
            self.assertEqual([t['filename'] for t in album['tracks']],
                             ['CD1/disc.cue#track=01','CD1/disc.cue#track=02','CD2/disc.wav','CD10/disc.wav'])
            self.assertFalse((folder/'.cratelog.json').exists())
            self.assertEqual(info.read_text(encoding='utf-8'),'{}')
            album['tracks'][1]['highlighted']=True;save_album(folder,album)
            self.assertTrue(load_album(folder)['tracks'][1]['highlighted'])

    def test_failed_write_retains_local_recovery(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);path=root/'album.json';path.write_text('{"rating": 1}')
            recovery=root/'local-recovery';recovery.mkdir()
            original=Path.open
            def open_file(file,mode='r',*args,**kwargs):
                if file==path and mode=='r+b':raise OSError('simulated drive failure')
                return original(file,mode,*args,**kwargs)
            with patch('cratelog_library.tempfile.mkdtemp',return_value=str(recovery)),patch.object(Path,'open',open_file):
                with self.assertRaisesRegex(OSError,'local-recovery'):
                    direct_json(path,{'rating':5})
            self.assertEqual(json.loads((recovery/'previous.json').read_bytes()),{'rating':1})
            self.assertEqual(json.loads((recovery/'pending.json').read_bytes()),{'rating':5})
            self.assertEqual(json.loads(path.read_bytes()),{'rating':1})

if __name__=='__main__':unittest.main()
