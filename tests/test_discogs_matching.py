import unittest
from unittest.mock import Mock
from cratelog import DiscogsAPI,album_similarity,folder_search_fields,rank_discogs_results
class MatchingTests(unittest.TestCase):
    def test_query_and_ranking(self):
        api=DiscogsAPI('test');api.session.get=Mock()
        api.session.get.return_value.json.return_value={'results':[
            {'id':1,'title':'Various - Album','year':2000},
            {'id':2,'title':'Various - Album','year':1987},
            {'id':3,'title':'ZZZZ - XXXX','year':1900}]}
        results=api.search('VA -1987- Album',minimum_score=0.4)
        self.assertEqual(api.session.get.call_args.kwargs['params']['q'],'Album')
        self.assertEqual([r['id'] for r in results],[2,1])
        self.assertEqual(results[0]['_match_score'],1)
    def test_parsing(self):
        self.assertEqual(folder_search_fields('Artist - 1987 - Album'),('Artist','Album','1987'))
        self.assertEqual(folder_search_fields('Artist - Album'),('Artist','Album',''))
        self.assertEqual(folder_search_fields('Album'),('','Album',''))
        self.assertEqual(album_similarity('Album','Different Artist','Album',1990),1)
        self.assertEqual(album_similarity('Artist - Album','Artist','Album',1990),1)
    def test_threshold(self):
        self.assertEqual(rank_discogs_results('abcde',[{'title':'A - abxyz'}])[0]['_match_score'],.4)
        self.assertEqual(rank_discogs_results('abcde',[{'title':'A - axxyz'}]),[])
    def test_field_weights(self):
        self.assertAlmostEqual(album_similarity('AAA -1987- BBB','AAA','BBB',2000),.9)
        self.assertAlmostEqual(album_similarity('AAA -1987- BBB','AAA','XXX',2000),.45)
        self.assertAlmostEqual(album_similarity('AAA -1987- BBB','XXX','BBB',2000),.45)
        self.assertAlmostEqual(album_similarity('AAA -1987- BBB','XXX','XXX',1987),.1)
        self.assertAlmostEqual(album_similarity('AAA - BBB','AAA','XXX'),.5)
        self.assertEqual(album_similarity('BBB','XXX','BBB'),1)
    def test_manual_query_keeps_low_scores(self):
        api=DiscogsAPI('test');api.session.get=Mock()
        api.session.get.return_value.json.return_value={'results':[{'id':1,'title':'A - zzzzz'},{'id':2,'title':'A - abcde'}]}
        self.assertEqual([r['id'] for r in api.search('abcde',minimum_score=0)],[2,1])
        self.assertEqual([r['id'] for r in api.search('abcde')],[2,1])
        self.assertEqual([r['id'] for r in api.search('abcde',minimum_score=0.4)],[2])
    def test_prefix_only(self):
        api=DiscogsAPI('test');api.session.get=Mock();api.session.get.return_value.json.return_value={'results':[]}
        for query,expected in [('VA - Album','Album'),('va - 1987 - Album','Album'),('VAST -1987- VA Album','VAST VA Album')]:
            api.search(query);self.assertEqual(api.session.get.call_args.kwargs['params']['q'],expected)
if __name__=='__main__':unittest.main()
