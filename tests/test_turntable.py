import math
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from cratelog_turntable import album_progress,deck_point,tonearm_geometry,SPINDLE,PIVOT,strobe_rates,STROBE_REFERENCES

class TurntableTests(unittest.TestCase):
    def test_duration_weighted_position_and_cue_identity(self):
        album={'tracks':[{'filename':'CD1/disc.cue#track=01'},{'filename':'CD1/disc.cue#track=02'}],
               '_durations':{'CD1/disc.cue#track=01':{'seconds':60},'CD1/disc.cue#track=02':{'seconds':180}}}
        self.assertEqual(album_progress(album,'CD1/disc.cue#track=02',60),(.5,True))
        self.assertEqual(album_progress(album,'elsewhere.mp3',60),(0.,False))
        self.assertEqual(album_progress(album,'CD1/disc.cue#track=02',999),(1.,True))
        album['_durations']={}
        self.assertEqual(album_progress(album,'CD1/disc.cue#track=02',0),(.5,True))
    def test_rigid_tonearm_and_tracking_error(self):
        self.assertAlmostEqual(math.dist(PIVOT,SPINDLE),2.15)
        for i in range(101):
            progress=i/100
            tip,direction,head=tonearm_geometry(progress)
            radius=math.dist(tip,SPINDLE)
            self.assertAlmostEqual(math.dist(tip,PIVOT),2.30)
            self.assertAlmostEqual(radius,1.46-.86*progress)
            offset=math.degrees(math.acos(min(1,sum(a*b for a,b in zip(direction,head)))))
            self.assertAlmostEqual(offset,22.)
            tangent=(-(tip[1]-SPINDLE[1])/radius,(tip[0]-SPINDLE[0])/radius)
            error=math.degrees(math.acos(min(1,sum(a*b for a,b in zip(tangent,head)))))
            self.assertLess(error,2.7)
        for i in range(101):
            tip,_,_=tonearm_geometry(.5,i/100)
            self.assertAlmostEqual(math.dist(tip,PIVOT),2.30)

    def test_strobe_stationary_rows_at_both_speeds(self):
        for nominal in (100/3,45.):
            rates=strobe_rates(nominal,nominal)
            self.assertLess(rates[0],rates[1]);self.assertLess(rates[1],0)
            self.assertEqual(rates[2],0);self.assertGreater(rates[3],0)
            for row,reference in enumerate(STROBE_REFERENCES):
                self.assertAlmostEqual(strobe_rates(nominal*(1+reference),nominal)[row],0.)

    def test_projection_center(self):
        x,z=deck_point(450,300,900,600)
        self.assertLess(abs(x),.3);self.assertLess(abs(z),.3)

if __name__=='__main__':unittest.main()
