import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from cratelog_platform import state_dir
from cratelog_language import LanguageManager
from cratelog_i18n import language,tr

class ReleaseTests(unittest.TestCase):
    def test_isolated_state_directory(self):
        with tempfile.TemporaryDirectory() as folder,patch.dict(os.environ,{'CRATELOG_STATE_DIR':folder}):
            self.assertEqual(state_dir(),Path(folder))
    def test_language_env_and_fallback(self):
        with patch.dict(os.environ,{'CRATELOG_LANGUAGE':'zh-Hant-TW'}):
            self.assertEqual(LanguageManager().get_current_lang(),'zh_TW')
        manager=LanguageManager();manager.set_language('es_ES')
        missing=next(k for k in manager.translations['en_US'] if k not in manager.translations['es_ES'])
        self.assertEqual(manager.t(missing),manager.translations['en_US'][missing])
    def test_turntable_menu_translation(self):
        before=language.current_lang
        try:
            language.set_language('en_US')
            self.assertEqual(tr('曲目  ·  滚轮翻页'),'Tracks · Scroll to browse')
            language.set_language('ja_JP')
            self.assertIn('スクロール',tr('曲目  ·  滚轮翻页'))
        finally:language.set_language(before)
