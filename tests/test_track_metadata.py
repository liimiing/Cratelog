"""M4A tag roundtrip/cache upgrade and query-free playback selection."""
import sys
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from cratelog_library import load_album
from cratelog_tags import read_tags,save_tags,stamp
from cratelog_player import Player

class TrackMetadataTests(unittest.TestCase):
    def test_m4a_tags_and_old_cache(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);file=root/'test.m4a'
            subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','sine=duration=1','-metadata','title=M4A Title','-metadata','artist=M4A Artist',str(file)],check=True,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            original=read_tags(file)
            self.assertEqual(original['title'],'M4A Title')
            self.assertEqual(original['artist'],'M4A Artist')
            values={**original,'title':'Edited Title','tracknumber':'2/12','discnumber':'1/2','comment':'Review'}
            save_tags(file,values,original,stamp(file))
            self.assertEqual(read_tags(file),values)
            album=load_album(root)
            info=album['_durations']['test.m4a']
            self.assertEqual(info['title'],'Edited Title')
            self.assertEqual(info['artist'],'M4A Artist')
            self.assertGreater(info['seconds'],0)
            import json
            cache=root/'.cratelog.json'
            data=album.copy()
            data['_durations']['test.m4a'].update(reader=3,title='stale')
            data['_durations']['test.m4a'].pop('artist',None)
            cache.write_text(json.dumps(data),encoding='utf-8')
            refreshed=load_album(root)['_durations']['test.m4a']
            self.assertEqual(refreshed['artist'],'M4A Artist')
            self.assertEqual(refreshed['title'],'Edited Title')

    def test_no_lookup_for_large_playlist(self):
        for count in (1,1000):
            tracks=[{'filename':f'{i}.flac'} for i in range(count)]
            player=SimpleNamespace(album={'tracks':tracks,'_track_sources':{t['filename']:{'file':t['filename']} for t in tracks}},folder=Path('music'),tracks=SimpleNamespace(selection=lambda:(str(count-1),)),display_metadata=Mock(return_value={'artist':'test'}),play=Mock())
            Player.prepare_album_playlist(player,{'artist':'test'})
            prepared=player.album_playlist_sources
            Player.play_selected(player)
            player.display_metadata.assert_not_called()
            self.assertIs(player.playlist_sources,prepared)
            self.assertIs(player.playlist,player.album_playlist)
            self.assertEqual(player.play_index,count-1)
            self.assertEqual(len(player.playlist_sources),count)
            player.play.assert_called_once()

if __name__=='__main__':unittest.main()
