<?php
declare(strict_types=1);
require __DIR__.'/cratelog_common.php';
header('Content-Type: application/json; charset=utf-8');
header('Cache-Control: no-store');
function reply(int $status, array $data): never { http_response_code($status); echo json_encode($data,JSON_UNESCAPED_UNICODE); exit; }
function valid_track_path(string $path): bool {
    if ($path==='' || preg_match('~[\\\\:\x00-\x1f]|^/~',$path)) return false;
    foreach (explode('/',$path) as $part) if (in_array($part,['','.','..'],true)) return false;
    return true;
}
function upload_error_message(int $error,string $name): string {
    $reasons=[UPLOAD_ERR_INI_SIZE=>'超过 PHP upload_max_filesize='.ini_get('upload_max_filesize'),UPLOAD_ERR_FORM_SIZE=>'超过表单上传限制',UPLOAD_ERR_PARTIAL=>'上传不完整',UPLOAD_ERR_NO_FILE=>'未收到文件',UPLOAD_ERR_NO_TMP_DIR=>'PHP 临时目录不存在',UPLOAD_ERR_CANT_WRITE=>'PHP 临时目录不可写',UPLOAD_ERR_EXTENSION=>'被 PHP 扩展阻止'];
    return $name.'：'.($reasons[$error] ?? '无效上传文件');
}
$authorization=$_SERVER['HTTP_AUTHORIZATION'] ?? $_SERVER['REDIRECT_HTTP_AUTHORIZATION'] ?? '';
$fallback=$_SERVER['HTTP_X_CRATELOG_TOKEN'] ?? '';
if (function_exists('getallheaders')) {
    foreach (getallheaders() as $name=>$value) {
        if (!$authorization && strcasecmp($name,'Authorization')===0) $authorization=$value;
        if (!$fallback && strcasecmp($name,'X-Cratelog-Token')===0) $fallback=$value;
    }
}
$token=preg_match('/^Bearer\s+(.+)$/i',trim($authorization),$match) ? trim($match[1]) : trim($fallback);
if (!authorized($token)) {
    $code=strlen(getenv('CRATELOG_API_TOKEN') ?: '')<32 ? 'auth_not_configured' : ($token===''?'auth_header_missing':'auth_token_mismatch');
    reply(401,['error'=>'Unauthorized','code'=>$code]);
}
try {
    $db = db();
    if ($_SERVER['REQUEST_METHOD'] === 'GET') {
        if (isset($_GET['catalog'])) {
            $catalog=[];
            foreach ($db->query('SELECT id,local_path,metadata FROM cratelog_albums') as $row) {
                $m=json_decode($row['metadata'],true);
                $catalog[]=['id'=>$row['id'],'number'=>$m['编号'] ?? '', 'path'=>$row['local_path'],'artist'=>$m['音乐人'] ?? '', 'album'=>$m['专辑名'] ?? '', 'year'=>$m['出版年份'] ?? '', 'label'=>$m['唱片厂牌'] ?? ''];
            }
            reply(200,['catalog'=>$catalog,'schema_version'=>5]);
        }
        reply(200,['album'=>album($db,(string)($_GET['id'] ?? '')),'schema_version'=>5]);
    }
    if ($_SERVER['REQUEST_METHOD'] !== 'POST') reply(405,['error'=>'Method not allowed']);
    if (!isset($_POST['album'])) reply(413,['error'=>'服务器未收到专辑数据，请检查 PHP post_max_size='.ini_get('post_max_size').' 和 Web 服务器请求体上限']);
    if (strlen($_POST['album'] ?? '') > 2*1024*1024) reply(413,['error'=>'Metadata too large']);
    try { $a = json_decode($_POST['album'] ?? '',true,512,JSON_THROW_ON_ERROR); }
    catch (JsonException $e) { reply(422,['error'=>'Invalid JSON']); }
    $rev = filter_var($_POST['revision'] ?? null,FILTER_VALIDATE_INT);
    if (!is_array($a) || !preg_match('/^[a-f0-9-]{36}$/D',$a['id'] ?? '') || $rev === false || $rev < 0 ||
        !(is_int($a['rating'] ?? null) || is_float($a['rating'] ?? null)) || $a['rating'] < 0 || $a['rating'] > 5 || fmod($a['rating']*2,1.0) != 0 ||
        !is_string($a['local_path'] ?? null) || !is_array($a['metadata'] ?? null) ||
        !is_array($a['tracks'] ?? null) || count($a['tracks']) > 5000 || !is_array($a['images'] ?? null))
        reply(422,['error'=>'Invalid album']);
    if (count($a['images'])>100) reply(422,['error'=>'每张专辑最多同步 100 张图片，本次为 '.count($a['images']).' 张。']);
    $a['metadata']=normalize_metadata($a['metadata']);
    $expectedFiles=count($a['images'])+(is_array($a['documents'] ?? null)?count($a['documents']):0);
    $uploadLimit=(int)ini_get('max_file_uploads');
    if ($uploadLimit>0 && $expectedFiles>$uploadLimit)
        reply(422,['error'=>'本次同步共 '.$expectedFiles.' 个文件（图片与文档合计），超过 PHP max_file_uploads='.$uploadLimit.'。请将服务端 php.ini 的 max_file_uploads 调至至少 '.max(30,$expectedFiles).'，重启 PHP 服务后重试。','code'=>'upload_file_limit']);
    $comment = $a['personal_comment'] ?? null;
    if ($comment !== null && (!is_string($comment) || strlen($comment)>40000)) reply(422,['error'=>'Invalid personal comment']);
    $documents = null;
    if (array_key_exists('documents',$a)) {
        if (!is_array($a['documents']) || count($a['documents'])>10) reply(422,['error'=>'Invalid documents']);
        $documentUploads=$_FILES['documents'] ?? ['name'=>[]]; $documents=[]; $documentNames=[];
        if (count($documentUploads['name']) !== count($a['documents'])) reply(422,['error'=>'文档上传不完整：应收 '.count($a['documents']).' 个，实收 '.count($documentUploads['name']).' 个；PHP max_file_uploads='.ini_get('max_file_uploads').'（图片和文档合计）。']);
        foreach ($a['documents'] as $i=>$document) {
            $name=$document['filename'] ?? '';
            if (!is_string($name) || strlen($name)>512 || preg_match('/[\\\\\/\x00-\x1f]/',$name) || !in_array(strtolower(pathinfo($name,PATHINFO_EXTENSION)),['md','txt','doc','docx','pdf','rtf','htm','html','mht','mhtml'],true) || isset($documentNames[$name])) reply(422,['error'=>'Invalid attachment filename']);
            $documentNames[$name]=true; $tmp=$documentUploads['tmp_name'][$i] ?? '';
            if (($documentUploads['error'][$i] ?? -1)!==UPLOAD_ERR_OK) reply(422,['error'=>upload_error_message($documentUploads['error'][$i] ?? -1,$name)]);
            if (($documentUploads['size'][$i] ?? 0)>10*1024*1024 || !is_uploaded_file($tmp)) reply(422,['error'=>$name.'：附件超过 10 MB 或上传无效']);
            $content=file_get_contents($tmp); $hash=hash('sha256',$content);
            if ($hash !== ($document['sha256'] ?? '') || ($documentUploads['name'][$i] ?? '') !== $name) reply(422,['error'=>'Document filename or checksum mismatch']);
            $text=in_array(strtolower(pathinfo($name,PATHINFO_EXTENSION)),['md','txt'],true) && preg_match('//u',$content) && !str_contains($content,"\0");
            $documents[]=['filename'=>$name,'sha256'=>$hash,'content'=>$text?$content:base64_encode($content),'encoding'=>$text?'utf-8':'base64'];
        }
    }
    $names=[];
    foreach ($a['tracks'] as $t) {
        if (!is_string($t['filename'] ?? null) || strlen($t['filename']) > 512 || !valid_track_path($t['filename']) ||
            !is_bool($t['selected'] ?? null) || !is_bool($t['highlighted'] ?? null) || isset($names[$t['filename']])) reply(422,['error'=>'Invalid track']);
        if (isset($t['display_name']) && (!is_string($t['display_name']) || strlen($t['display_name'])>1024)) reply(422,['error'=>'Invalid track display name']);
        $names[$t['filename']]=true;
    }
    $db->beginTransaction();
    require_once __DIR__.'/cratelog_numbering.php';
    lock_album_writes($db);
    if ($documents!==null) $documents=array_map('externalize_document',$documents);
    $uploads=$_FILES['images'] ?? ['name'=>[]]; $images=[];
    if (count($uploads['name']) !== count($a['images'])) reply(422,['error'=>'Incomplete image upload']);
    $dir=image_dir(); if (!is_dir($dir) && !mkdir($dir,0700,true)) throw new RuntimeException('Image directory unavailable');
    foreach ($a['images'] as $i=>$pic) {
        $tmp=$uploads['tmp_name'][$i] ?? '';
        if (($uploads['error'][$i] ?? -1)!==UPLOAD_ERR_OK) reply(422,['error'=>upload_error_message($uploads['error'][$i] ?? -1,$pic['filename'] ?? '图片')]);
        if (($uploads['size'][$i] ?? 0)>10*1024*1024 || !is_uploaded_file($tmp)) reply(422,['error'=>($pic['filename'] ?? '图片').'：图片超过 10 MB 或上传无效']);
        $mime=(new finfo(FILEINFO_MIME_TYPE))->file($tmp);
        if (!in_array($mime,['image/jpeg','image/png','image/webp','image/gif'],true) || !getimagesize($tmp)) reply(422,['error'=>'Unsupported image']);
        $hash=hash_file('sha256',$tmp);
        if ($hash !== ($pic['sha256'] ?? '') || ($uploads['name'][$i] ?? '') !== ($pic['filename'] ?? '')) reply(422,['error'=>'Image changed during upload']);
        if (!file_exists($dir.'/'.$hash) && !move_uploaded_file($tmp,$dir.'/'.$hash)) throw new RuntimeException('Image save failed');
        $images[]=['filename'=>$pic['filename'],'sha256'=>$hash];
    }
    require_once __DIR__.'/cratelog_match.php';
    if (($_POST['match_folder'] ?? '')==='1' && !album($db,$a['id'])) {
        $existing=match_album($db,$a['metadata']);
        if ($existing) {
            $a=fill_album($existing,$a);$rev=$existing['_revision'];
            $comment=$a['personal_comment'];
            $images=merge_files($existing['images'],$images);
            $documents=merge_files($existing['documents'],$documents ?? []);
        }
    }
    unset($a['metadata']['来源'],$a['metadata']['导入来源']);
    $a['local_path']=preg_replace('/^[A-Za-z]:/','',$a['local_path']);
    $a['local_path']=preg_replace('~^.*?/\.mounty(?=/|$)~','',$a['local_path']);
    // A deleted remote record is a new insert, even when the local sidecar
    // still carries its previous revision. Check under the SQLite write lock.
    if ($rev === 0 || !album($db,$a['id'])) {
        try {
            $a['metadata']['编号']=(string)next_album_number($db);
            $s=$db->prepare('INSERT INTO cratelog_albums(id,rating,local_path,metadata,images,personal_comment,documents,revision) VALUES(?,?,?,?,?,?,?,?)');
            $s->execute([$a['id'],$a['rating'],$a['local_path'],json_encode($a['metadata'],JSON_UNESCAPED_UNICODE),json_encode($images),$comment ?? '',json_encode($documents ?? []),$rev+1]);
        } catch (PDOException $e) { if ($e->getCode()==='23000') { $db->rollBack(); reply(409,['error'=>'Version conflict']); } throw $e; }
    } else {
        $stored=album($db,$a['id'],($_POST['reconcile'] ?? '')==='1');
        if ($stored) {
            if (($_POST['reconcile'] ?? '')==='1') {
                // Keep server-only attachments while replacing same-named ones
                // with the files explicitly uploaded in this reconciliation.
                $images=merge_files($images,$stored['images']);
                $documents=merge_files($documents ?? [],$stored['documents']);
            }
            $number=((array)$stored['metadata'])['编号'] ?? '';
            $a['metadata']['编号']=$number!=='' ? $number : (string)next_album_number($db);
        }
        $s=$db->prepare('UPDATE cratelog_albums SET rating=?,local_path=?,metadata=?,images=?,personal_comment=COALESCE(?,personal_comment),documents=COALESCE(?,documents),revision=revision+1,updated_at=CURRENT_TIMESTAMP WHERE id=? AND revision=?');
        $s->execute([$a['rating'],$a['local_path'],json_encode($a['metadata'],JSON_UNESCAPED_UNICODE),json_encode($images),$comment,$documents===null?null:json_encode($documents),$a['id'],$rev]);
        if ($s->rowCount() !== 1) { $db->rollBack(); reply(409,['error'=>'Version conflict']); }
    }
    $s=$db->prepare('DELETE FROM cratelog_tracks WHERE album_id=?'); $s->execute([$a['id']]);
    $s=$db->prepare('INSERT INTO cratelog_tracks(album_id,position,filename,selected,highlighted,display_name) VALUES(?,?,?,?,?,?)');
    foreach ($a['tracks'] as $i=>$t) $s->execute([$a['id'],$i,$t['filename'],(int)$t['selected'],(int)$t['highlighted'],$t['display_name'] ?? '']);
    $saved=album($db,$a['id']);
    $db->commit(); reply(200,['revision'=>$rev+1,'schema_version'=>5,'album'=>$saved]);
} catch (Throwable $e) {
    if (isset($db) && $db->inTransaction()) $db->rollBack();
    if ($e instanceof DomainException) reply(409,['error'=>$e->getMessage(),'code'=>'ambiguous_match']);
    if ($e instanceof UnexpectedValueException) reply(409,['error'=>$e->getMessage(),'code'=>'field_conflict']);
    error_log('Cratelog: '.$e->getMessage()); reply(500,['error'=>'Server error; check server log']);
}
