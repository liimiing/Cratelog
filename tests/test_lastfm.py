import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch,Mock
from types import SimpleNamespace
from cratelog_lastfm import LastfmAPI,LastfmError,LastfmService,Listening,stored_config


class LastfmTests(unittest.TestCase):
    def test_batched_mpv_events_count_media_progress(self):
        item=Listening();item.sample(0,0)
        # Ten position events are drained almost simultaneously per UI tick.
        for batch in range(1,31):
            for event in range(10):item.sample((batch-1)+.1*(event+1),batch+event*.00001)
        self.assertAlmostEqual(item.listened,30)
        self.assertTrue(item.eligible(60))
        item.sample(58,31);self.assertAlmostEqual(item.listened,30)
    def test_player_uses_metadata_and_records_once(self):
        from cratelog_player import Player
        service=Mock();service.enabled.return_value=True
        state=SimpleNamespace(lastfm_listening=Listening(),lastfm_loaded=True,lastfm=service,
            lastfm_tags={},lastfm_source={'_album':{'音乐人':'Artist','专辑名':'Album'}},cue_title='',paused=False,duration=100)
        Player.lastfm_sample(state,0);service.now.assert_not_called()
        state.lastfm_tags={'title':'Tagged title','artist':'Tagged artist'}
        state.lastfm_listening.listened=60
        Player.lastfm_sample(state,1);Player.lastfm_sample(state,2)
        self.assertEqual(service.now.call_count,1);self.assertEqual(service.enqueue.call_count,1)
        self.assertEqual(service.enqueue.call_args.args[0]['artist'],'Tagged artist')
        self.assertEqual(service.enqueue.call_args.args[0]['timestamp'],state.lastfm_listening.timestamp)
        service.reset_mock();state.lastfm_listening=Listening();state.lastfm_source={'id':'disc.cue#track=02','performer':'Cue artist'};state.cue_title='Cue song'
        Player.lastfm_sample(state,0)
        self.assertEqual(service.now.call_args.args[0]['track'],'Cue song')
        self.assertEqual(service.now.call_args.args[0]['artist'],'Cue artist')
    def test_signature_and_errors(self):
        response=Mock(status_code=200);response.json.return_value={'token':'test'}
        with patch('cratelog_lastfm.requests.post',return_value=response) as post:
            LastfmAPI('key','secret').call('auth.getToken')
            data=post.call_args.kwargs['data']
            self.assertEqual(data['api_sig'],hashlib.md5(b'api_keykeymethodauth.getTokensecret').hexdigest())
            self.assertEqual(post.call_args.args[0],'https://ws.audioscrobbler.com/2.0/')
            response.json.return_value={'error':9,'message':'bad session'}
            with self.assertRaises(LastfmError) as e:LastfmAPI('key','secret').call('track.scrobble')
            self.assertEqual(e.exception.code,9)
    def test_listening_excludes_seek_pause_and_short_tracks(self):
        item=Listening();item.sample(0,0)
        for i in range(1,21):item.sample(i,i)
        self.assertEqual(item.listened,20)
        item.sample(100,21);self.assertEqual(item.listened,20)
        item.sample(100,22,True);item.sample(100,100);self.assertEqual(item.listened,20)
        for i in range(1,31):item.sample(100+i,100+i)
        self.assertTrue(item.eligible(100));self.assertFalse(item.eligible(30))
        item.sent=True;self.assertFalse(item.eligible(100))
        item.sent=False;item.listened=240;self.assertTrue(item.eligible(900))
    def test_credentials_roundtrip(self):
        config={'secret':'shared-test','session':'session-test','key':'key','enabled':True}
        self.assertEqual(stored_config(stored_config(config),decode=True),config)
    def test_offline_queue_survives_restart_and_account_isolation(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'queue.sqlite';messages=[]
            config=dict(enabled=True,key='key',secret='secret',session='session',username='alice')
            service=LastfmService(path,messages.append);service.configure(config)
            with patch.object(LastfmAPI,'call',side_effect=LastfmError('offline')):
                service.enqueue({'artist':'Artist','track':'Title','timestamp':123,'duration':100})
                service.pool.submit(lambda:None).result()
            service.close()
            service=LastfmService(path,messages.append);service.configure({**config,'username':'bob'})
            with patch.object(LastfmAPI,'call',return_value={'scrobbles':{'scrobble':{'ignoredMessage':{'code':'0'}}}}) as call:
                service.flush();service.pool.submit(lambda:None).result();call.assert_not_called()
                service.configure(config);service.flush();service.pool.submit(lambda:None).result();self.assertEqual(call.call_count,1)
                service.flush();service.pool.submit(lambda:None).result();self.assertEqual(call.call_count,1)
            service.close()

if __name__=='__main__':unittest.main()
