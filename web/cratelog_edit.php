<?php
declare(strict_types=1);
function edit_album(PDO $db,array $album): never {
    $_SESSION['edit_csrf'] ??= bin2hex(random_bytes(32));$error='';
    if ($_SERVER['REQUEST_METHOD']==='POST') {
        $backups=[];
        try {
            if (!hash_equals($_SESSION['edit_csrf'],(string)($_POST['csrf'] ?? ''))) throw new RuntimeException('页面已过期，请刷新后重试。');
            $revision=filter_var($_POST['revision'] ?? '',FILTER_VALIDATE_INT);
            if ($revision!==$album['_revision']) throw new RuntimeException('资料已被其他页面或客户端修改，请重新打开编辑页面。');
            $db->beginTransaction();
            require_once __DIR__.'/cratelog_numbering.php';lock_album_writes($db);
            if (($_POST['action'] ?? '')==='delete') {
                require_once __DIR__.'/cratelog_delete.php';
                $current=album($db,$album['id'],true);
                if (!$current || $current['_revision']!==$revision) throw new RuntimeException('版本已变化，未删除数据。');
                $backups=remove_album_images($db,$current);
                // Associated files have been removed; clear manifests before deleting the row.
                $s=$db->prepare("UPDATE cratelog_albums SET documents='[]',images='[]' WHERE id=? AND revision=?");$s->execute([$album['id'],$revision]);
                $s=$db->prepare('DELETE FROM cratelog_albums WHERE id=? AND revision=?');$s->execute([$album['id'],$revision]);
            } else {
                $rating=filter_var($_POST['rating'] ?? '',FILTER_VALIDATE_FLOAT);
                if ($rating===false || $rating<0 || $rating>5 || fmod($rating*2,1)!==0.0) throw new RuntimeException('评分必须是 0–5，支持半星。');
                $comment=(string)($_POST['comment'] ?? '');$path=(string)($_POST['path'] ?? '');
                if (strlen($comment)>40000) throw new RuntimeException('评论最多 10000 字。');
                $metadata=(array)$album['metadata'];
                foreach ($metadata as $key=>$old) {
                    if (in_array($key,['导入来源','来源'],true)) continue;
                    $value=(string)($_POST['metadata'][$key] ?? '');
                    $metadata[$key]=(is_array($old) || is_object($old))?json_decode($value,true,512,JSON_THROW_ON_ERROR):$value;
                }
                $s=$db->prepare('UPDATE cratelog_albums SET metadata=?,rating=?,personal_comment=?,local_path=?,revision=revision+1,updated_at=CURRENT_TIMESTAMP WHERE id=? AND revision=?');
                $s->execute([json_encode($metadata,JSON_UNESCAPED_UNICODE),$rating,$comment,$path,$album['id'],$revision]);
                if ($s->rowCount()!==1) throw new RuntimeException('版本已变化，未覆盖数据。');
                $flags=$db->prepare('UPDATE cratelog_tracks SET selected=?,highlighted=? WHERE album_id=? AND position=?');
                foreach ($album['tracks'] as $i=>$track) $flags->execute([isset($_POST['selected'][$i])?1:0,isset($_POST['highlighted'][$i])?1:0,$album['id'],$i]);
            }
            if ($s->rowCount()!==1) throw new RuntimeException('版本已变化，未覆盖数据。');
            $db->commit();
            foreach ($backups as $stream) fclose($stream);$backups=[];
            header('Location: cratelog.php'.(($_POST['action'] ?? '')==='delete'?'':'?album='.rawurlencode($album['id'])),true,303);exit;
        } catch (Throwable $e) {
            if ($db->inTransaction()) $db->rollBack();
            if ($backups) {restore_album_images($backups);foreach ($backups as $stream) fclose($stream);}
            $error=$e instanceof JsonException?'曲目等结构化字段 JSON 格式不正确。':$e->getMessage();
        }
    }
    echo '<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover"><title>编辑专辑</title><link rel="stylesheet" href="cratelog_detail.css?v=3"><link rel="stylesheet" href="cratelog_mobile.css?v=3"><main class="editor"><h1>编辑专辑</h1><p><a href="?album='.esc($album['id']).'">返回详情</a></p><p role="alert">'.esc($error).'</p><form method="post"><input type="hidden" name="csrf" value="'.esc($_SESSION['edit_csrf']).'"><input type="hidden" name="revision" value="'.$album['_revision'].'">';
    echo '<label>评分<select name="rating">';for ($r=0;$r<=5;$r+=.5) echo '<option value="'.$r.'"'.($r==$album['rating']?' selected':'').'>'.($r?:'未评分').'</option>';echo '</select></label>';
    echo '<label>个人评论<textarea name="comment">'.esc($_POST['comment'] ?? $album['personal_comment']).'</textarea></label><label>本地路径<input name="path" value="'.esc($_POST['path'] ?? $album['local_path']).'"></label>';
    foreach ((array)$album['metadata'] as $key=>$value) {
        if (in_array($key,['来源','导入来源'],true)) continue;
        echo '<label>'.esc($key).'<textarea name="metadata['.esc($key).']">'.esc($_POST['metadata'][$key] ?? display_value($value)).'</textarea></label>';
    }
    foreach ($album['tracks'] as $i=>$track) echo '<p>'.esc($track['display_name'] ?? $track['filename']).' <label>入选 <input type="checkbox" name="selected['.$i.']"'.($track['selected']?' checked':'').'></label><label>重点 <input type="checkbox" name="highlighted['.$i.']"'.($track['highlighted']?' checked':'').'></label></p>';
    echo '<button name="action" value="save">保存修改</button><details class="danger"><summary>删除这张专辑</summary><p>先清理专属图片及文档，再删除专辑与曲目标记；其他专辑共用的图片保留。本地音乐文件不会删除。再次主动同步会重新创建远端记录。</p><button name="action" value="delete">确认删除专辑</button></details></form></main></html>';exit;
}
