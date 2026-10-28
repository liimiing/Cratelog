"""Shared language selection for the player and organizer."""
import locale
import os
from translations import TRANSLATIONS

class LanguageManager:
    """多语言管理器"""
    
    def __init__(self):
        self.current_lang = 'auto'
        self.translations = TRANSLATIONS
    
    def detect_system_language(self):
        """检测系统语言"""
        try:
            lang=os.environ.get('CRATELOG_LANGUAGE') or os.environ.get('LC_ALL') or os.environ.get('LC_MESSAGES')
            if not lang:lang=locale.getlocale()[0]
            if lang:
                lang_lower = lang.lower().replace('-', '_')
                if lang_lower.startswith('chinese'):
                    return 'zh_TW' if 'traditional' in lang_lower else 'zh_CN'
                if lang_lower.startswith('zh_tw') or lang_lower.startswith('zh_hant'):
                    return 'zh_TW'
                elif lang_lower.startswith('zh'):
                    return 'zh_CN'
                elif lang_lower.startswith('es'):
                    return 'es_ES'
                elif lang_lower.startswith('pt'):
                    return 'pt_BR'
                elif lang_lower.startswith('fr'):
                    return 'fr_FR'
                elif lang_lower.startswith('de'):
                    return 'de_DE'
                elif lang_lower.startswith('ja'):
                    return 'ja_JP'
                elif lang_lower.startswith('ko'):
                    return 'ko_KR'
                elif lang_lower.startswith('ru'):
                    return 'ru_RU'
                elif lang_lower.startswith('ar'):
                    return 'ar_SA'
                elif lang_lower.startswith('hi'):
                    return 'hi_IN'
                else:
                    return 'en_US'
        except:
            pass
        return 'en_US'  # 默认英文
    
    def set_language(self, lang_code):
        """设置语言"""
        self.current_lang = lang_code if lang_code in ('auto',*TRANSLATIONS) else 'auto'
    
    def get_current_lang(self):
        """获取当前语言代码"""
        if self.current_lang == 'auto':
            return self.detect_system_language()
        return self.current_lang
    
    def t(self, key, **kwargs):
        """翻译文本"""
        lang = self.get_current_lang()
        text = self.translations.get(lang, self.translations['en_US']).get(key, self.translations['en_US'].get(key,key))
        # 支持格式化字符串
        if kwargs:
            try:
                text = text.format(**kwargs)
            except:
                pass
        return text
    
    def get_available_languages(self):
        """获取可用语言列表"""
        return [
            ('auto', self.t('auto')),
            ('zh_CN', '简体中文'),
            ('zh_TW', '繁體中文'),
            ('en_US', 'English'),
            ('es_ES', 'Español'),
            ('pt_BR', 'Português'),
            ('fr_FR', 'Français'),
            ('de_DE', 'Deutsch'),
            ('ja_JP', '日本語'),
            ('ko_KR', '한국어'),
            ('ru_RU', 'Русский'),
            ('ar_SA', 'العربية'),
            ('hi_IN', 'हिन्दी'),
        ]

