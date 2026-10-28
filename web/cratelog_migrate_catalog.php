<?php
declare(strict_types=1);
require __DIR__.'/cratelog_common.php';

// One-time catalog-number migration; operate on raw JSON to preserve original values.
function catalog_rows(PDO $db): array {
    $rows=[];
    foreach ($db->query('SELECT id,metadata,revision FROM cratelog_albums') as $row) {
        $metadata=json_decode($row['metadata'],true,512,JSON_THROW_ON_ERROR);
        if (!is_array($metadata)) throw new RuntimeException('Invalid metadata JSON for '.$row['id']);
        if (!array_key_exists('厂牌编号',$metadata)) continue;
        $original=$metadata;
        $value=$metadata['厂牌编号'];
        $empty=$value===null || $value===[] || (is_string($value) && trim($value)==='');
        if (!$empty) $metadata['唱片编号']=$value;
        unset($metadata['厂牌编号']);
        $rows[]=['id'=>$row['id'],'revision'=>(int)$row['revision'],
            'metadata'=>$metadata,'original_metadata'=>$original];
    }
    return $rows;
}

function migrate_catalog(PDO $db): array {
    if ($db->getAttribute(PDO::ATTR_DRIVER_NAME)!=='sqlite')
        throw new RuntimeException('This cleanup script only runs on SQLite.');
    $db->beginTransaction();
    try {
        require_once __DIR__.'/cratelog_numbering.php';
        lock_album_writes($db);
        $rows=catalog_rows($db);
        if (!$rows) {$db->commit();return [0,''];}

        $dir=data_dir().'/backups';
        if (!is_dir($dir) && !mkdir($dir,0700,true) && !is_dir($dir))
            throw new RuntimeException('Cannot create backup directory');
        $path=$dir.'/catalog-number-'.gmdate('Ymd-His').'-'.bin2hex(random_bytes(4)).'.json';
        $backup=[];
        foreach ($rows as $row) $backup[]=['id'=>$row['id'],'revision'=>$row['revision'],'original_metadata'=>$row['original_metadata']];
        $json=json_encode($backup,JSON_UNESCAPED_UNICODE|JSON_PRETTY_PRINT|JSON_THROW_ON_ERROR);
        $stream=fopen($path,'xb');
        if (!$stream) throw new RuntimeException('Cannot create backup file');
        try {
            if (fwrite($stream,$json)!==strlen($json)) throw new RuntimeException('Cannot write complete backup');
        } finally {fclose($stream);}
        @chmod($path,0600);

        $update=$db->prepare('UPDATE cratelog_albums SET metadata=?,revision=revision+1,updated_at=CURRENT_TIMESTAMP WHERE id=? AND revision=?');
        foreach ($rows as $row) {
            $metadata=json_encode($row['metadata'],JSON_UNESCAPED_UNICODE|JSON_THROW_ON_ERROR);
            $update->execute([$metadata,$row['id'],$row['revision']]);
            if ($update->rowCount()!==1) throw new RuntimeException('Album changed while cleaning: '.$row['id']);
        }
        $db->commit();
        return [count($rows),$path];
    } catch (Throwable $e) {
        if ($db->inTransaction()) $db->rollBack();
        throw $e;
    }
}

if (PHP_SAPI==='cli') {
    try {
        [$count,$backup]=migrate_catalog(db());
        echo "已调整 {$count} 条专辑记录。".($backup!==''?"\n备份：{$backup}":'')."\n";
    } catch (Throwable $e) {
        fwrite(STDERR,$e->getMessage()."\n");exit(1);
    }
    exit;
}

if (session_status()===PHP_SESSION_NONE) {
    session_set_cookie_params(['httponly'=>true,'samesite'=>'Strict','secure'=>!empty($_SERVER['HTTPS']) && $_SERVER['HTTPS']!=='off']);
    session_start();
}
header('Content-Type: text/html; charset=utf-8');
header('Cache-Control: no-store');
header("Content-Security-Policy: default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; base-uri 'none'; frame-ancestors 'none'");
function clean_html(string $value): string {return htmlspecialchars($value,ENT_QUOTES|ENT_SUBSTITUTE,'UTF-8');}
$_SESSION['migrate_catalog_csrf'] ??= bin2hex(random_bytes(32));
$authorized=authorized((string)($_SESSION['cratelog_token'] ?? '')) ||
    ($_SERVER['REQUEST_METHOD']==='POST' && authorized(trim((string)($_POST['token'] ?? ''))));
$message='';$count=null;
try {
    if ($_SERVER['REQUEST_METHOD']==='POST') {
        if (!$authorized) throw new RuntimeException('同步令牌不正确。');
        if (!hash_equals($_SESSION['migrate_catalog_csrf'],(string)($_POST['csrf'] ?? '')))
            throw new RuntimeException('页面已过期，请刷新重试。');
        [$changed,$backup]=migrate_catalog(db());
        $message="已调整 {$changed} 条专辑记录。".($backup!==''?" 备份：{$backup}":'');
        $_SESSION['migrate_catalog_csrf']=bin2hex(random_bytes(32));
    }
    if ($authorized) $count=count(catalog_rows(db()));
} catch (Throwable $e) {$message=$e->getMessage();}
echo '<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Cratelog 统一唱片编号</title>';
echo '<style>body{background:#151719;color:#e7e7e7;font:16px/1.6 system-ui;max-width:720px;margin:40px auto;padding:20px}a{color:#eda456}button,input{font:inherit;padding:10px;background:#30363c;color:white;border:1px solid #666}button{cursor:pointer}p{overflow-wrap:anywhere}</style>';
echo '<h1>统一 SQLite 唱片编号</h1><p><a href="cratelog.php">返回资料库</a></p>';
if ($message!=='') echo '<p role="status">'.clean_html($message).'</p>';
if ($count!==null) echo '<p>当前仍有 '.(int)$count.' 条记录包含「厂牌编号」。</p>';
echo '<p>有值的「厂牌编号」将覆盖「唱片编号」（即使原唱片编号已有值）；空值不覆盖。随后移除「厂牌编号」。其他字段保留。修改前会备份受影响记录的完整原始 metadata；任何写入失败会回滚本次数据库修改。重复执行不会再次修改已处理记录。</p>';
echo '<form method="post"><input type="hidden" name="csrf" value="'.clean_html($_SESSION['migrate_catalog_csrf']).'">';
if (!$authorized) echo '<p>同步令牌：<input type="password" name="token" autocomplete="current-password" required></p>';
echo '<button type="submit">备份并执行调整</button></form></html>';
