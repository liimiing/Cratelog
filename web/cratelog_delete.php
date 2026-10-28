<?php
declare(strict_types=1);
function restore_album_images(array $backups): void {
    foreach ($backups as $path=>$stream) {
        rewind($stream);
        $output=@fopen($path,'wb');
        if (!$output) throw new RuntimeException('图片恢复失败，请检查目录写权限：'.$path);
        try {if (stream_copy_to_stream($stream,$output)===false) throw new RuntimeException('图片恢复失败：'.$path);}
        finally {fclose($output);}
    }
}
function remove_album_images(PDO $db,array $album): array {
    $used=[];$backups=[];
    $s=$db->prepare('SELECT images,documents FROM cratelog_albums WHERE id<>?');$s->execute([$album['id']]);
    foreach ($s as $row) foreach (['images'=>image_dir(),'documents'=>docs_dir()] as $field=>$dir) {
        foreach (json_decode($row[$field],true) ?: [] as $file) $used[$dir.'/'.$file['sha256']]=true;
    }
    try {
        foreach (['images'=>image_dir(),'documents'=>docs_dir()] as $field=>$dir) foreach ($album[$field] ?? [] as $image) {
            $hash=$image['sha256'];
            if (isset($used[$dir.'/'.$hash]) || isset($backups[$dir.'/'.$hash])) continue;
            if (!preg_match('/^[a-f0-9]{64}$/D',$hash)) throw new RuntimeException('图片记录中的哈希无效，未删除专辑。');
            $path=$dir.'/'.$hash;
            if (!file_exists($path)) continue;
            if (is_link($path) || !is_file($path)) throw new RuntimeException('图片路径异常，未删除专辑。');
            $backup=tmpfile();$input=@fopen($path,'rb');
            if (!$backup || !$input) throw new RuntimeException('无法读取图片或创建临时备份，未删除专辑。');
            try {$copied=stream_copy_to_stream($input,$backup);}
            finally {fclose($input);}
            if ($copied===false || $copied!==filesize($path)) {fclose($backup);throw new RuntimeException('图片备份失败，未删除专辑。');}
            if (!@unlink($path)) {fclose($backup);throw new RuntimeException('无法删除图片，请检查目录权限；专辑未删除。');}
            $backups[$path]=$backup;
        }
        return $backups;
    } catch (Throwable $e) {
        restore_album_images($backups);
        foreach ($backups as $stream) fclose($stream);
        throw $e;
    }
}
