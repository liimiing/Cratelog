"""Delayed window geometry must not freeze the initial tiny image scale."""
import sys
import unittest
from pathlib import Path
from PIL import Image
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from cratelog_picture import PictureCanvas,tk

class PictureFitTests(unittest.TestCase):
    def test_delayed_geometry_and_explicit_zoom(self):
        root=tk.Tk()
        try:
            root.geometry('200x150')
            canvas=PictureCanvas(root,Image.new('RGB',(6000,4000)),None)
            canvas.pack(fill='both',expand=True);root.update()
            small=canvas.dimensions()[2]
            root.geometry('1000x700');root.update()
            w,h,fit=canvas.dimensions()
            self.assertGreater(fit,small*3)
            self.assertAlmostEqual(fit,min(1,(w-24)/6000,(h-24)/4000))
            canvas.scale(1.5)
            zoomed=canvas.dimensions()[2]
            root.geometry('1100x800');root.update()
            self.assertAlmostEqual(canvas.dimensions()[2],zoomed)
            # A new image resets fitting even after the preceding image was zoomed.
            root.geometry('220x180');root.update()
            canvas.set_image(Image.new('RGB',(5000,7000)))
            canvas.dimensions()  # Paint before the requested larger geometry arrives.
            root.geometry('800x900');root.update()
            w,h,fit=canvas.dimensions()
            self.assertAlmostEqual(fit,min(1,(w-24)/5000,(h-24)/7000))
            self.assertFalse(canvas.fit_locked)
        finally:root.destroy()

if __name__=='__main__':unittest.main()
