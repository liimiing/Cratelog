import unittest
from unittest.mock import patch
from cratelog_language import LanguageManager
from cratelog_i18n import language,tr,CORE,LOCAL


class LanguageTests(unittest.TestCase):
    def setUp(self):self.before=language.current_lang
    def tearDown(self):language.set_language(self.before)

    def test_auto_remains_auto(self):
        manager=LanguageManager();manager.set_language('auto')
        with patch.object(manager,'detect_system_language',return_value='ja_JP'):
            self.assertEqual(manager.get_current_lang(),'ja_JP')
        self.assertEqual(manager.current_lang,'auto')

    def test_core_languages_and_explicit_fallback(self):
        for code,phrases in LOCAL.items():
            language.set_language(code)
            self.assertEqual(set(phrases),set(CORE))
            for source,target in phrases.items():self.assertEqual(tr(source),target)
        language.set_language('en_US')
        self.assertEqual(tr('音乐根目录'),'Music folder')
        self.assertEqual(tr('专辑艺术家'),'Album artist')

    def test_metadata_and_filenames_are_not_rewritten(self):
        language.set_language('en_US')
        self.assertEqual(tr('Artist - 设置 - Album.flac'),'Artist - 设置 - Album.flac')
        self.assertEqual(tr('自定义专辑名称'),'自定义专辑名称')


if __name__=='__main__':unittest.main()
