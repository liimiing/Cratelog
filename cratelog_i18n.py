"""Player UI translations. Storage keys and playback modes stay language-neutral.

Existing organizer translations are reused for all supported languages. New
player phrases fall back to English explicitly until a locale supplies them.
"""
from cratelog_language import LanguageManager
from translations import TRANSLATIONS

language=LanguageManager()
EN={
 '服务端已确认附件：':'Attachments confirmed by server:',
 '读取冲突资料失败':'Could not load conflict data',
 '无法确定远端专辑':'Could not identify remote album',
 '目录中没有可安全关联的远端记录。请先在网页核对艺术家与专辑名。':'No safely matching remote record was found. Check the artist and album title on the website.',
 'Cratelog · 本地与远端资料对比':'Cratelog · Compare local and remote data',
 '选择要更新的远端记录，再逐项选择最终采用的值。编号由服务器保留；附件在服务器取两端合集。':'Choose the remote record, then select each final value. The server retains its number; attachments are combined.',
 '字段':'Field','本地':'Local','远端':'Remote','采用':'Use',
 '选择行后可批量指定来源；双击行切换来源。下方可查看完整内容。':'Select rows to set their source. Double-click a row to switch. Full values appear below.',
 '请等待冲突资料提交完成':'Wait for reconciliation to finish',
 '本地：':'Local:','远端：':'Remote:',
 '提交后文件夹：':'Folder after submission: ',
 '文件夹名称需要调整：':'Folder name needs adjustment: ',
 '采用本地':'Use local','采用远端':'Use remote','提交并统一两端':'Apply to both sides',
 '读取远端记录失败':'Could not load remote record',
 '远端记录不存在':'Remote record not found',
 '请选择其他远端记录。':'Choose another remote record.',
 '专辑评分':'Album rating','入选':'Selected','重点':'Highlight','封面':'Cover','附件':'Attachment',
 '无法提交':'Cannot apply changes','正在取得远端独有的封面与附件…':'Fetching remote-only covers and attachments…',
 '查看远端记录':'View remote record',
 '获取远端附件失败':'Could not fetch remote attachment','本地更新失败':'Local update failed',
 '正在提交统一后的专辑资料…':'Submitting reconciled album…',
 '远端提交失败；本地已保留合并资料和备份：':'Remote submission failed; local changes and backups remain: ',
 '远端提交失败':'Remote submission failed','两端资料已统一':'Both sides are synchronized',
 '复制曲名':'Copy track information',
 '；从下一曲开始记录':'; Scrobbling starts with the next track','已断开；需要时可重新授权':'Disconnected; you can authorize again later',
 '正在读取本地资料…':'Reading local metadata…','暂无封面':'No cover',
 '启用 Last.fm（发送曲目资料，不上传音频）':'Enable Last.fm (metadata only; no audio uploads)',
 '超过 30 秒的曲目，实际聆听达到一半或 4 分钟后录入。\n缺少可靠艺术家或曲名时不提交；网络失败的记录保留并重试。':'Tracks longer than 30 seconds are scrobbled after listening to half or 4 minutes.\nTracks without an artist or title are not submitted. Failed requests are queued for retry.',
 '音乐收藏 · 整理 · 聆听\n\n开发者：':'Collect · Organize · Listen\n\nDeveloper: ',
 '正在申请授权令牌…':'Requesting authorization token…',
 '请在浏览器允许授权，然后点击“完成授权并启用”':'Authorize in your browser, then click Complete authorization',
 '请先点击“浏览器授权”':'Click Authorize in browser first',
 '请先完成浏览器授权':'Complete browser authorization first',
 'Cratelog · 音乐资料库与播放器':'Cratelog · Music Library & Player',
 'Cratelog · 专辑整理':'Cratelog · Album Organizer',
 '选择音乐根目录开始浏览':'Choose a music folder to start browsing',
 'CRATELOG  /  尚未播放':'CRATELOG  /  Not playing', 'CRATELOG / 已停止':'CRATELOG / Stopped',
 '本地播放 · Discogs 整理 · 资料同步':'Playback · Discogs organizer · Library sync',
 '音乐根目录':'Music folder','刷新目录':'Refresh folders','Discogs 文件整理':'Discogs organizer',
 '同步当前专辑':'Sync album','批量同步根目录':'Sync library','取消同步':'Cancel sync',
 '远端版本处理':'Resolve remote changes','设置':'Settings','关于':'About',
 '选择左侧专辑目录':'Select an album folder on the left','未评价':'Not reviewed','未评分':'Not rated',
 '评价':'Review','专辑整理菜单':'Album actions','复制艺术家 - 专辑名（发行年份）':'Copy artist - album (year)',
 '在豆瓣音乐搜索当前专辑':'Search this album on Douban','打开服务端专辑详情':'Open album on server',
 '切换入选':'Toggle selected track','切换重点':'Toggle highlighted track',
 '本地音频文件名':'Audio filename','ID3曲名':'Tag title','时长':'Duration','入选':'Selected','重点':'Highlight',
 '上一曲':'Previous track','下一曲':'Next track','播放 / 继续':'Play / Resume','暂停':'Pause','停止':'Stop','继续':'Resume',
 '顺序播放':'Sequential','列表循环':'Repeat playlist','单曲循环':'Repeat track',' · 点击切换':' · Click to change',
 '音量 · 点击或拖动调整，滚轮微调':'Volume · Click or drag; scroll to adjust',
 '查看完整状态信息':'Show full status','Cratelog · 完整状态信息':'Cratelog · Full status',
 '关闭':'Close','保存':'Save','取消':'Cancel','复制':'Copy',
 'Cratelog 设置':'Cratelog Settings','界面语言':'Interface language',
 '语言设置将在重启后应用':'Language changes apply after restarting Cratelog',
 '同步 API（HTTPS）':'Sync API (HTTPS)','同步令牌（保存后长期有效）':'Sync token (saved permanently)',
 'mpv 路径（可留空自动检测）':'mpv path (blank for auto-detection)',
 '字幕':'Subtitles','字幕字体':'Subtitle font','字高':'Font height','字幕颜色':'Subtitle color','选择颜色':'Choose color',
 '字体留空使用无衬线默认字体。字高以高度为 720 的画面为基准，频谱窗口较矮时会按比例缩小。':'Leave the font blank for the default sans-serif. Height is scaled from a 720-pixel-high frame, so a shorter spectrum window draws it smaller.',
 '字幕设置':'Subtitle settings','字幕字体名称过长。':'The subtitle font name is too long.',
 '字高须为 8 到 300 的整数。':'Font height must be an integer from 8 to 300.',
 '字幕颜色须为 #RRGGBB。':'Subtitle color must be #RRGGBB.',
 '没有匹配的字幕':'No matching subtitles',
 'Last.fm · 正在播放与聆听记录':'Last.fm · Now playing & scrobbling',
 '启用 Last.fm（仅提交曲目信息，不上传音频）':'Enable Last.fm (track metadata only; no audio uploads)',
 '申请 API Key ↗':'Get API Key ↗','浏览器授权':'Authorize in browser','完成授权并启用':'Complete authorization',
 '断开':'Disconnect','尚未授权':'Not authorized','已授权：':'Authorized: ',
 '从下一首开始记录':'Scrobbling starts with the next track',
 'Last.fm 凭据不可用，请重新授权':'Last.fm credentials unavailable; please authorize again',
 '密钥已改变，请重新开始授权':'The key has changed; restart authorization',
 '已断开，需要时可重新授权':'Disconnected; you can authorize again later',
 '正在申请授权令牌。':'Requesting authorization token…',
 '正在完成授权':'Completing authorization…','请先点击浏览器授权。':'Click Authorize in browser first.',
 '请在浏览器完成授权，然后点击完成授权并启用。':'Authorize in your browser, then click Complete authorization.',
 '请重新发起浏览器授权':'Please restart browser authorization',
 '图片读取失败':'Cannot read image','封面读取失败':'Cannot read cover',
 '缩放窗口可调整预览大小 · Esc 关闭':'Resize to zoom · Esc to close',
 'Cratelog · 评价':'Cratelog · Review','专辑评分 · 点击星星左半或右半，支持半星':'Album rating · Click either half of a star',
 '个人评论':'Personal comment','清除评分':'Clear rating','评论过长':'Comment too long',
 '个人评论最多 10000 字。':'Comments may contain at most 10,000 characters.',
 '评价保存失败':'Cannot save review','评价已保存本地；点击同步当前专辑上传':'Review saved locally; sync the album to upload',
 ' · 已写评论':' · Has comment','已保存到本地；等待同步':'Saved locally; awaiting sync',
 '保存失败':'Save failed','同步设置':'Sync settings','同步进行中':'Sync in progress',
 '正在同步；资料仍可在本地编辑…':'Syncing; local editing remains available…',
 '同步已取消':'Sync cancelled','同步完成':'Sync complete','同步进度：成功 ':'Sync progress: succeeded ',
 '：成功 ':': succeeded ','，失败 ':', failed ','已跳过超过 5 MB 的附件':'Attachments over 5 MB skipped',
 '未同步项目（可重试）':'Unsynced items (retry available)',
 '请等待同步完成或取消同步后再处理远端版本':'Wait for sync to finish or cancel it before resolving remote changes',
 '远端暂无此专辑，请同步当前专辑':'Album not found on server; sync the current album',
 '远端版本 ':'Remote revision ','，评分 ':', rating ',
 '请等待当前同步结束再退出。':'Wait for the current sync to finish before exiting.',
 '保存窗口状态失败':'Cannot save window state','正在读取：':'Reading: ',
 '正在读取远端资料。':'Reading remote metadata…','本地资料已加载':'Local metadata loaded',
 '播放失败':'Playback failed','播放控制失败：':'Playback control failed: ',
 '播放文件已移动，请刷新目录：':'Audio file moved; refresh folders: ',
 '正在预缓冲音频，请稍候…':'Buffering audio; please wait…','音频缓冲就绪':'Audio buffer ready',
 '解码失败：':'Decoding failed: ','未知错误':'Unknown error','码率 —':'Bitrate —',
 '已复制：':'Copied: ','暂无简介':'No description',
 '整理器正在批量处理，请等待完成后操作当前专辑':'The organizer is processing albums; wait before editing this album',
 '编辑音频标签（ID3）':'Edit audio tags (ID3)','编辑音频标签':'Edit audio tags',
 'CUE 分轨':'CUE tracks','该曲目由 CUE 定义，修改音频标签会影响整张碟。请编辑 CUE 文件中的曲名和艺术家。':'This track is defined by a CUE sheet. Editing the audio tags affects the entire disc. Edit the title and artist in the CUE sheet instead.',
 '读取标签失败':'Cannot read tags','音频正在使用':'Audio file in use',
 '请先停止该文件的播放，再保存标签。':'Stop playback of this file before saving its tags.',
 '保存标签失败':'Cannot save tags','音频标签已保存：':'Audio tags saved: ',
 '曲名':'Title','艺术家':'Artist','专辑':'Album','专辑艺术家':'Album artist','发行年份 / 日期':'Year / Date',
 '音轨编号':'Track number','碟号':'Disc number','流派':'Genre','作曲者':'Composer','备注':'Comment',
 '关于 Cratelog':'About Cratelog',
 'mpv IPC 连接超时':'mpv IPC connection timed out','mpv 事件连接已关闭':'mpv event connection closed',
 'mpv 控制连接已关闭':'mpv control connection closed','mpv 启动失败':'mpv failed to start',
 '未找到 mpv。macOS 请执行 brew install mpv；Windows 可放入 runtime/mpv/mpv.exe。':'mpv not found. On macOS run brew install mpv; on Windows place it in runtime/mpv/mpv.exe.',
 '\n是：采用远端评分、资料和标记（备份本地）\n否：保留本地，以此远端版本为基础重新同步\n取消：暂不处理':'\nYes: use remote ratings, metadata and marks (back up local data)\nNo: keep local data and sync against this remote revision\nCancel: do nothing',
}
# Reuse complete organizer translations whenever the source wording matches.
REVERSE={value:key for key,value in TRANSLATIONS['zh_CN'].items()}

# Core player controls in every language already offered by the organizer.
CORE=('音乐根目录','刷新目录','Discogs 文件整理','同步当前专辑','批量同步根目录','取消同步','远端版本处理','设置','关于','评价','界面语言','语言设置将在重启后应用','本地音频文件名','ID3曲名','时长','入选','重点','未评分','未评价','上一曲','下一曲','暂停','停止','播放 / 继续','顺序播放','列表循环','单曲循环','编辑音频标签','个人评论','清除评分')
CORE_ROWS={
 'zh_TW':'音樂根目錄|重新整理目錄|Discogs 檔案整理|同步目前專輯|批次同步根目錄|取消同步|遠端版本處理|設定|關於|評價|介面語言|語言設定將於重新啟動後套用|本機音訊檔名|ID3 曲名|時長|入選|重點|未評分|未評價|上一首|下一首|暫停|停止|播放 / 繼續|依序播放|清單循環|單曲循環|編輯音訊標籤|個人評論|清除評分',
 'es_ES':'Carpeta de música|Actualizar carpetas|Organizador Discogs|Sincronizar álbum|Sincronizar biblioteca|Cancelar sincronización|Resolver cambios remotos|Ajustes|Acerca de|Reseña|Idioma de interfaz|El idioma se aplicará al reiniciar|Archivo de audio|Título de etiqueta|Duración|Selección|Destacado|Sin puntuación|Sin reseña|Anterior|Siguiente|Pausa|Detener|Reproducir / Continuar|Secuencial|Repetir lista|Repetir pista|Editar etiquetas|Comentario personal|Borrar puntuación',
 'pt_BR':'Pasta de música|Atualizar pastas|Organizador Discogs|Sincronizar álbum|Sincronizar biblioteca|Cancelar sincronização|Resolver alterações remotas|Configurações|Sobre|Avaliação|Idioma da interface|O idioma será aplicado ao reiniciar|Arquivo de áudio|Título da etiqueta|Duração|Selecionada|Destaque|Sem nota|Sem avaliação|Anterior|Próxima|Pausar|Parar|Reproduzir / Continuar|Sequencial|Repetir lista|Repetir faixa|Editar etiquetas|Comentário pessoal|Limpar nota',
 'fr_FR':'Dossier musical|Actualiser les dossiers|Gestion Discogs|Synchroniser cet album|Synchroniser la bibliothèque|Annuler la synchronisation|Résoudre les conflits|Paramètres|À propos|Avis|Langue de l’interface|La langue sera appliquée au redémarrage|Fichier audio|Titre de la balise|Durée|Sélection|À retenir|Non noté|Aucun avis|Précédent|Suivant|Pause|Arrêter|Lire / Reprendre|Lecture séquentielle|Répéter la liste|Répéter le titre|Modifier les balises|Commentaire personnel|Effacer la note',
 'de_DE':'Musikordner|Ordner aktualisieren|Discogs-Verwaltung|Album synchronisieren|Bibliothek synchronisieren|Synchronisierung abbrechen|Remote-Konflikte lösen|Einstellungen|Über|Bewertung|Oberflächensprache|Sprache wird nach Neustart übernommen|Audiodatei|Tag-Titel|Dauer|Auswahl|Hervorhebung|Unbewertet|Keine Bewertung|Vorheriger Titel|Nächster Titel|Pause|Stopp|Wiedergabe / Fortsetzen|Der Reihe nach|Liste wiederholen|Titel wiederholen|Tags bearbeiten|Persönlicher Kommentar|Bewertung löschen',
 'ja_JP':'音楽フォルダー|フォルダーを更新|Discogs 整理|アルバムを同期|ライブラリを同期|同期を中止|リモートの変更を解決|設定|このアプリについて|評価|表示言語|言語設定は再起動後に反映されます|音声ファイル名|タグの曲名|再生時間|選出|注目|未採点|未評価|前の曲|次の曲|一時停止|停止|再生 / 再開|順番に再生|リストを繰り返す|一曲を繰り返す|音声タグを編集|個人コメント|評価を消去',
 'ko_KR':'음악 폴더|폴더 새로 고침|Discogs 정리|앨범 동기화|라이브러리 동기화|동기화 취소|원격 변경 해결|설정|정보|평가|인터페이스 언어|언어는 다시 시작한 후 적용됩니다|오디오 파일명|태그 곡명|재생 시간|선정|주요 곡|별점 없음|평가 없음|이전 곡|다음 곡|일시 정지|정지|재생 / 계속|순차 재생|목록 반복|한 곡 반복|오디오 태그 편집|개인 의견|별점 지우기',
 'ru_RU':'Папка музыки|Обновить папки|Органайзер Discogs|Синхронизировать альбом|Синхронизировать библиотеку|Отменить синхронизацию|Разрешить конфликты|Настройки|О программе|Оценка|Язык интерфейса|Язык изменится после перезапуска|Аудиофайл|Название из тегов|Длительность|Избранное|Важное|Без оценки|Без отзыва|Предыдущий|Следующий|Пауза|Стоп|Играть / Продолжить|По порядку|Повтор списка|Повтор трека|Изменить теги|Личный комментарий|Сбросить оценку',
 'ar_SA':'مجلد الموسيقى|تحديث المجلدات|منظم Discogs|مزامنة الألبوم|مزامنة المكتبة|إلغاء المزامنة|حل التعارضات|الإعدادات|حول|تقييم|لغة الواجهة|تُطبق اللغة بعد إعادة التشغيل|ملف الصوت|عنوان الوسم|المدة|مختارة|مميزة|بلا نجوم|بلا تقييم|السابق|التالي|إيقاف مؤقت|إيقاف|تشغيل / متابعة|تشغيل متسلسل|تكرار القائمة|تكرار المقطع|تحرير الوسوم|تعليق شخصي|مسح التقييم',
 'hi_IN':'संगीत फ़ोल्डर|फ़ोल्डर रीफ़्रेश करें|Discogs आयोजक|एल्बम सिंक करें|लाइब्रेरी सिंक करें|सिंक रद्द करें|दूरस्थ बदलाव सुलझाएँ|सेटिंग्स|परिचय|समीक्षा|इंटरफ़ेस भाषा|भाषा पुनः आरंभ करने पर लागू होगी|ऑडियो फ़ाइल|टैग शीर्षक|अवधि|चयनित|प्रमुख|रेटिंग नहीं|समीक्षा नहीं|पिछला|अगला|विराम|रोकें|चलाएँ / जारी रखें|क्रम से चलाएँ|सूची दोहराएँ|ट्रैक दोहराएँ|ऑडियो टैग संपादित करें|निजी टिप्पणी|रेटिंग हटाएँ',
}
LOCAL={code:dict(zip(CORE,row.split('|'),strict=True)) for code,row in CORE_ROWS.items()}

# Translator-editable catalogs; absent phrases explicitly fall back to English.
import json
from pathlib import Path
CATALOGS={}
for path in (Path(__file__).resolve().parent/'locales').glob('*.json'):
    values=json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(values,dict) or not all(isinstance(k,str) and isinstance(v,str) for k,v in values.items()):
        raise ValueError('Invalid translation catalog: '+path.name)
    CATALOGS[path.stem]=values
EN.update(CATALOGS.get('en_US',{}))

def tr(text):
    if not isinstance(text,str):return text
    lang=language.get_current_lang()
    if lang=='zh_CN':return text
    if text in CATALOGS.get(lang,{}):return CATALOGS[lang][text]
    if text in LOCAL.get(lang,{}):return LOCAL[lang][text]
    key=REVERSE.get(text)
    if key and key in TRANSLATIONS.get(lang,{}):return TRANSLATIONS[lang][key]
    if text in EN:return EN[text]
    # Dynamic status strings: translate fixed phrases, preserving filenames,
    # numbers and metadata. Only callers explicitly rendering UI use this.
    for source in sorted(EN,key=len,reverse=True):
        if len(source)>=4 and text.startswith(source):
            return tr(source)+text[len(source):]
    return text
