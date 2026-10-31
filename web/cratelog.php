<?php
declare(strict_types=1);
require __DIR__.'/cratelog_common.php';
require __DIR__.'/cratelog_view.php';
// Reuse a session already started by Slim middleware or session.auto_start.
if (session_status() === PHP_SESSION_NONE) {
    session_set_cookie_params(['httponly'=>true,'samesite'=>'Strict','secure'=>!empty($_SERVER['HTTPS']) && $_SERVER['HTTPS']!=='off']);
    session_start();
}
header('Cache-Control: no-store');
header("Content-Security-Policy: default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self'; frame-ancestors 'none'; base-uri 'none'");
$loginError='';
$expected=getenv('CRATELOG_API_TOKEN') ?: '';
if (strlen($expected)<32) {
    $loginError='服务端同步令牌尚未正确配置：请在 cratelog_config.php 中设置至少 32 字符的 CRATELOG_API_TOKEN。仅填写网页输入框不会设置服务器令牌。';
} elseif ($_SERVER['REQUEST_METHOD']==='POST' && isset($_POST['token'])) {
    $submitted=trim((string)($_POST['token'] ?? ''));
    if (!authorized($submitted)) {
        $loginError='同步令牌不匹配，请输入与服务端配置一致的令牌。如果设置了 CRATELOG_API_TOKEN 环境变量，它会优先于配置文件。';
    } elseif (session_status()!==PHP_SESSION_ACTIVE || !session_regenerate_id(true)) {
        $loginError='无法创建登录会话，请检查 PHP session.save_path 是否存在且可写。';
    } else {
        $_SESSION['cratelog_token']=$submitted;
        if (session_write_close()) {
            // Verify persistence on the next request instead of hiding a broken session.
            header('Location: cratelog.php?login_check=1'.(($_GET['import'] ?? '')==='xlsx'?'&import=xlsx':''),true,303); exit;
        }
        unset($_SESSION['cratelog_token']);
        $loginError='登录会话保存失败，请检查 PHP session.save_path 权限与磁盘空间。';
    }
} elseif (isset($_GET['login_check']) && !authorized((string)($_SESSION['cratelog_token'] ?? ''))) {
    $loginError='令牌已验证，但登录状态未能保留。请允许此站点的 Cookie，并检查 PHP Session 存储、Cookie 路径和 HTTPS 配置。';
}
$isAdmin=authorized((string)($_SESSION['cratelog_token'] ?? ''));
$needsLogin=isset($_GET['login']) || isset($_GET['login_check']) || isset($_GET['edit']) || isset($_GET['import']) || $_SERVER['REQUEST_METHOD']==='POST';
if (!$isAdmin && $needsLogin) {
    echo '<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover"><title>Cratelog 登录</title><style>body{background:#151719;color:#e5e5e5;font:15px system-ui;max-width:520px;margin:80px auto;padding:20px}input,button{background:#292d32;color:white;border:1px solid #555;padding:12px;margin:8px 0}input{width:90%}.error{color:#ffbd96;line-height:1.7}</style><form method="post" action="cratelog.php'.(($_GET['import'] ?? '')==='xlsx'?'?import=xlsx':'').'"><h1>Cratelog</h1><p>输入服务器配置的同步令牌登录资料库。</p>';
    if ($loginError!=='') echo '<p class="error" role="alert">'.esc($loginError).'</p>';
    echo '<input type="password" name="token" placeholder="同步令牌" autocomplete="current-password" required><br><button>登录</button></form></html>'; exit;
}
try {
    $db=db();
    if (($_GET['import'] ?? '')==='xlsx') {require __DIR__.'/cratelog_import.php';import_page($db);}
    if (isset($_GET['image'])) {
        $hash=(string)$_GET['image'];
        if (!preg_match('/^[a-f0-9]{64}$/D',$hash)) { http_response_code(404); exit; }
        $path=image_dir().'/'.$hash;
        if (!is_file($path)) { http_response_code(404); exit; }
        header('Content-Type: '.(new finfo(FILEINFO_MIME_TYPE))->file($path)); header('X-Content-Type-Options: nosniff'); readfile($path); exit;
    }
    $id=(string)($_GET['album'] ?? ''); $detail=null; $albums=[];
    if ($id!=='') {
        $detail=album($db,$id,true);
        if (!$detail) {http_response_code(404);exit('未找到该专辑。');}
        if (isset($_GET['edit'])) {require __DIR__.'/cratelog_edit.php';edit_album($db,$detail);}
        if (isset($_GET['document'])) {
            foreach ($detail['documents'] as $document) {
                if (hash_equals($document['sha256'],(string)$_GET['document'])) {
                    if (isset($_GET['preview'])) {
                        $type=document_preview_type($document);
                        if (!$type) {http_response_code(415);exit('此附件暂不支持在线预览，请下载查看。');}
                        header('X-Content-Type-Options: nosniff');
                        header("Content-Security-Policy: default-src 'none'; style-src 'unsafe-inline'; frame-ancestors 'self'; base-uri 'none'");
                        if ($type==='pdf') {
                            header('Content-Type: application/pdf');
                            header("Content-Disposition: inline; filename=\"preview.pdf\"; filename*=UTF-8''".rawurlencode($document['filename']));
                            echo document_bytes($document);exit;
                        }
                        header('Content-Type: text/html; charset=utf-8');
                        header("Content-Security-Policy: sandbox; default-src 'none'; style-src 'unsafe-inline'; img-src data:; frame-ancestors 'self'; base-uri 'none'; form-action 'none'");
                        echo '<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>'.esc($document['filename']).'</title><style>body{background:#202428;color:#e5e5e5;font:16px/1.8 system-ui;padding:24px;overflow-wrap:anywhere}pre,p{white-space:pre-wrap}pre,code{background:#151719;padding:8px}a{color:#e9a65d}table{border-collapse:collapse;width:100%}td{border:1px solid #555;padding:8px}blockquote{border-left:3px solid #997046;padding-left:16px}</style>';
                        if ($type==='md') {
                            // Only our escaped Markdown output may run the local math renderer.
                            header("Content-Security-Policy: sandbox allow-scripts; default-src 'none'; script-src 'self'; style-src 'self' 'unsafe-inline'; font-src data:; img-src data:; frame-ancestors 'self'; base-uri 'none'; form-action 'none'");
                            echo '<link rel="stylesheet" href="assets/katex/katex.min.css"><script defer src="assets/katex/katex.min.js"></script><script defer src="assets/markdown-math.js"></script>';
                        }
                        echo readable_preview($document);
                        echo '<style>html,body{background:#fff!important;color:#222!important;color-scheme:light}body pre,body code{background:#f5f5f5;color:#222}body a{color:#175ca4}body td{border-color:#ccc}</style>';exit;
                    }
                    header('Content-Type: application/octet-stream');
                    header('X-Content-Type-Options: nosniff');
                    header('X-Content-Type-Options: nosniff');
                    header("Content-Disposition: attachment; filename=\"attachment\"; filename*=UTF-8''".rawurlencode($document['filename']));
                    echo document_bytes($document);exit;
                }
            }
            http_response_code(404);exit('未找到该文档。');
        }
        $related=[];
        $artist=trim(display_value(((array)$detail['metadata'])['音乐人'] ?? ''));
        if ($artist!=='') {
            $artistField=$db->getAttribute(PDO::ATTR_DRIVER_NAME)==='sqlite'
                ? "json_extract(metadata, '$.音乐人')"
                : "JSON_UNQUOTE(JSON_EXTRACT(metadata, '$.音乐人'))";
            $yearField=$db->getAttribute(PDO::ATTR_DRIVER_NAME)==='sqlite'
                ? "CAST(json_extract(metadata, '$.出版年份') AS INTEGER)"
                : "CAST(JSON_UNQUOTE(JSON_EXTRACT(metadata, '$.出版年份')) AS SIGNED)";
            $s=$db->prepare('SELECT id,metadata,images FROM cratelog_albums WHERE id<>? AND TRIM('.$artistField.')=? ORDER BY '.$yearField.' DESC,updated_at DESC,id LIMIT 5');
            $s->execute([$id,$artist]);
            $related=$s->fetchAll(PDO::FETCH_ASSOC);
        }
    } else {
        $q=(string)($_GET['q'] ?? ''); $page=max(0,(int)($_GET['page'] ?? 0));
        $count=$db->prepare('SELECT COUNT(*) FROM cratelog_albums WHERE CAST(metadata AS CHAR) LIKE ? OR personal_comment LIKE ?');
        $count->execute(['%'.$q.'%','%'.$q.'%']);
        $total=(int)$count->fetchColumn();$pageCount=max(1,(int)ceil($total/30));
        $page=min($page,$pageCount-1);
        $originalId=$db->getAttribute(PDO::ATTR_DRIVER_NAME)==='sqlite'
            ? "CAST(json_extract(metadata, '$.编号') AS INTEGER)"
            : "CAST(JSON_UNQUOTE(JSON_EXTRACT(metadata, '$.编号')) AS SIGNED)";
        $s=$db->prepare('SELECT id FROM cratelog_albums WHERE CAST(metadata AS CHAR) LIKE ? OR personal_comment LIKE ? ORDER BY '.$originalId.' DESC,updated_at DESC,id LIMIT 30 OFFSET '.($page*30));
        $s->execute(['%'.$q.'%','%'.$q.'%']);
        foreach ($s->fetchAll(PDO::FETCH_COLUMN) as $albumId) $albums[]=album($db,$albumId);
    }
} catch (Throwable $e) { error_log('Cratelog: '.$e->getMessage()); http_response_code(503); exit('Cratelog 数据库未就绪，请检查部署配置及数据库迁移。'); }
?>
<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover"><title>Cratelog · <?= $detail?esc(((array)$detail['metadata'])['专辑名'] ?? '专辑详情'):'音乐资料库' ?></title>
<style>
body{background:#151719;color:#e5e5e5;font:15px system-ui;margin:32px auto;max-width:1180px;padding:0 20px}a{color:#f6ad64}input,button,.action{padding:10px;background:#292d32;color:white;border:1px solid #555}.action{display:inline-block;text-decoration:none;margin-right:10px;border-radius:5px}article{padding:24px;margin:20px 0;background:#22262a;border-radius:10px}table{width:100%;border-collapse:collapse}td,th{text-align:left;padding:12px;border-bottom:1px solid #383d42;vertical-align:top}td{overflow-wrap:anywhere}.muted{color:#919ba3;font-size:13px}.marks{color:#ffb568}pre{white-space:pre-wrap;overflow-wrap:anywhere}summary{cursor:pointer}h1{letter-spacing:3px}.stars{display:inline-block;position:relative;color:#5d6369;white-space:nowrap;font:20px/1.2 Arial;vertical-align:middle}.star-fill{position:absolute;left:0;top:0;overflow:hidden;color:#f3b562}.album-row{cursor:pointer}.album-row:hover,.album-row:focus{background:#292f34}.thumb{width:62px;height:62px;object-fit:contain}.scroll{overflow-x:auto}.gallery{display:flex;gap:16px;flex-wrap:wrap}.gallery img{width:200px;height:200px;object-fit:contain;background:#151719}.gallery figure{margin:0}.gallery figcaption{max-width:200px;overflow-wrap:anywhere}.fields th{width:170px;color:#9ba5ac;font-weight:normal}.fields pre{margin:0}.comment{white-space:pre-wrap;overflow-wrap:anywhere}.markdown p{white-space:pre-wrap}.markdown pre{background:#151719;padding:16px}.markdown blockquote{border-left:3px solid #9b764b;margin-left:0;padding-left:14px;color:#b4bec5}.markdown h1{letter-spacing:0;font-size:26px}.markdown code{background:#30363c;padding:2px 4px}.list-comment{max-width:240px;white-space:pre-wrap} @media(max-width:640px){body{padding:0 12px}.gallery img{width:140px;height:140px}article{padding:16px}.fields th{width:95px}}

.list-page{padding-bottom:var(--pagination-height,150px)}.album-list{overflow:visible;margin-top:20px}.album-list table{table-layout:fixed;border-collapse:separate;border-spacing:0}.album-list th{position:sticky;top:0;z-index:10;background:#292d32;box-shadow:0 1px 0 #495057;overflow-wrap:anywhere}.album-list th:first-child{width:65px}.album-list th:nth-child(2){width:66px}.pagination-footer{position:fixed;bottom:0;left:0;right:0;z-index:30;background:#1d2125;border-top:1px solid #454b51;padding:12px 16px calc(10px + env(safe-area-inset-bottom));box-shadow:0 -6px 24px #0004}.pagination-buttons{display:flex;align-items:center;justify-content:center;gap:6px;flex-wrap:wrap;margin:0 auto;max-width:1180px}.pagination-buttons button{min-width:36px;padding:7px 10px;border-radius:5px;cursor:pointer}.pagination-buttons button:hover:not(:disabled){background:#4b3b2d;border-color:#b98656}.pagination-buttons button:disabled{opacity:.4;cursor:default}.pagination-buttons button[aria-current]{opacity:1;background:#704a2c;border-color:#c09060;color:#fff}.database-credit{margin:8px 0 0;text-align:center;font-size:12px;color:#969fa7;letter-spacing:.5px}@media(max-width:640px){.album-list td,.album-list th{padding:7px 4px;font-size:12px}.album-list th:first-child{width:32px}.album-list th:nth-child(2){width:40px}.album-list .thumb{width:36px;height:36px}.pagination-buttons .muted{width:100%;text-align:center}}
</style><link rel="stylesheet" href="cratelog_detail.css?v=6"><link rel="icon" href="assets/cratelog.svg?v=2" type="image/svg+xml"><link rel="alternate icon" href="assets/cratelog.ico?v=2"><link rel="stylesheet" href="cratelog_mobile.css?v=3"><script src="cratelog.js?v=7" defer></script></head><body class="<?=$detail?'detail-page':'list-page'?>">
<h1 style="display:flex;align-items:center;gap:14px"><img src="assets/cratelog.svg?v=2" width="48" height="48" alt="">CRATELOG</h1><p>专辑、曲目与聆听记录 · <a href="cratelog.php">专辑资料库</a> · <?php if ($isAdmin): ?><a href="?import=xlsx">导入 XLSX</a> · <a href="legacy_excel.php">原 Excel 检索</a><?php else: ?><a href="?login=1">管理员登录</a><?php endif ?> · <a href="#about-cratelog" data-about>关于</a></p>
<form action="cratelog.php" method="get" class="search-form" style="display:flex;gap:8px;flex-wrap:wrap"><input name="q" value="<?=esc($q ?? '')?>" placeholder="搜索专辑资料或个人评论" aria-label="搜索专辑资料或个人评论" style="flex:1;min-width:200px"><input type="hidden" name="page" value="0"><button type="submit">搜索</button><button type="submit" form="clear-search">清空</button></form>
<form id="clear-search" action="cratelog.php" method="get"><input type="hidden" name="q" value=""><input type="hidden" name="page" value="0"></form>
<?php if ($detail): $a=$detail; $m=(array)$a['metadata'];
    $search=trim(display_value($m['音乐人'] ?? '').' '.display_value($m['专辑名'] ?? ''));
    $douban='https://search.douban.com/music/subject_search?search_text='.rawurlencode($search);
?>
<?php require __DIR__.'/cratelog_detail.php'; ?>
<?php else: ?>
<div id="list-state" data-page="<?=$page?>" data-query="<?=esc($q)?>"></div>

<div class="scroll album-list"><table><thead><tr><th>编号</th><th>封面</th><th>音乐人 / 专辑</th><th>专辑路径</th><th>年代 / 厂牌</th><th>评价</th><th>个人评论</th></tr></thead><tbody>
<?php foreach ($albums as $a): $m=(array)$a['metadata']; $href='?album='.rawurlencode($a['id']); ?>
<tr class="album-row" tabindex="0" data-album-url="<?=esc($href)?>"><td><?=esc($m['编号'] ?? '—')?></td><td><?php if ($a['images']): ?><img class="thumb" loading="lazy" decoding="async" alt="专辑封面" src="?image=<?=esc($a['images'][0]['sha256'])?>"><?php endif ?></td><td><a href="<?=esc($href)?>"><?=esc($m['专辑名'] ?? basename($a['local_path']))?></a><div class="muted"><?=esc($m['音乐人'] ?? '')?></div></td><td class="muted" style="max-width:260px;word-break:break-all"><?=esc($a['local_path'] ?: '未关联本地目录')?></td><td class="muted"><?=esc($m['出版年份'] ?? '')?><br><?=esc(preg_replace('/\s+/u',' ',display_value($m['唱片厂牌'] ?? '')))?></td><td><?=stars($a['rating'],true)?></td><td class="list-comment"><?=esc(short_comment($a['personal_comment']))?></td></tr>
<?php endforeach ?></tbody></table></div>
<?php if (!$albums) echo '<p>暂无记录</p>'; ?>
<footer class="pagination-footer"><nav aria-label="专辑分页"><form method="get" class="pagination-buttons"><input type="hidden" name="q" value="<?=esc($q)?>">
<span class="muted">共 <?=$total?> 条 · 第 <?=$page+1?> / <?=$pageCount?> 页</span>
<button name="page" value="<?=max(0,$page-1)?>" <?=$page===0?'disabled':''?>>上一页</button>
<?php
$pages=array_unique(array_merge([0],range(max(0,$page-5),min($pageCount-1,$page+5)),[$pageCount-1]));
sort($pages);$previous=-1;
foreach ($pages as $number):
    if ($previous>=0 && $number>$previous+1) echo '<span class="muted">…</span>';
    $previous=$number;
    if ($number===$page): ?><button type="button" aria-current="page" disabled><?=$number+1?></button>
    <?php else: ?><button aria-label="第 <?=$number+1?> 页" name="page" value="<?=$number?>"><?=$number+1?></button><?php endif ?>
<?php endforeach ?>
<button name="page" value="<?=min($pageCount-1,$page+1)?>" <?=$page===$pageCount-1?'disabled':''?>>下一页</button>
</form></nav><p class="database-credit">专辑聆听数据库 by HITLIKE</p></footer>
<?php endif ?><?php require __DIR__.'/cratelog_about.php'; ?></body></html>
