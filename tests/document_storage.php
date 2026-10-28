<?php
declare(strict_types=1);
$dir=__DIR__.'/../.qa/docs-'.bin2hex(random_bytes(6));mkdir($dir,0700,true);
putenv('CRATELOG_DATA_DIR='.$dir);putenv('CRATELOG_DSN=sqlite:'.$dir.'/cratelog.sqlite');putenv('CRATELOG_IMAGE_DIR='.$dir.'/images');
require __DIR__.'/../web/cratelog_common.php';
require __DIR__.'/../web/cratelog_view.php';
require __DIR__.'/../web/cratelog_delete.php';
function verify(bool $ok): void {if (!$ok) throw new RuntimeException('Storage assertion failed');}
$db=db();$bytes="中文正文\n";$doc=['filename'=>'test.txt','sha256'=>hash('sha256',$bytes),'content'=>base64_encode($bytes),'encoding'=>'base64'];
$s=$db->prepare("INSERT INTO cratelog_albums(id,rating,local_path,metadata,images,documents,revision) VALUES(?,0,'','{}','[]',?,1)");
$s->execute(['test',json_encode([$doc])]);$db->exec('PRAGMA user_version=2');$db=null;
$db=db();$stored=album($db,'test',true)['documents'][0];
verify(!isset($stored['content']) && $stored['storage']==='file' && document_bytes($stored)===$bytes);
verify(str_contains(readable_preview($stored),'中文正文'));
$s=$db->prepare("INSERT INTO cratelog_albums(id,rating,local_path,metadata,images,documents,revision) VALUES(?,0,'','{}','[]',?,1)");$s->execute(['shared',json_encode([$stored])]);
verify(remove_album_images($db,album($db,'test',true))===[]);
$db->exec("DELETE FROM cratelog_albums WHERE id='shared'");
$db->beginTransaction();$backups=remove_album_images($db,album($db,'test',true));verify(!file_exists(document_path($doc['sha256'])));$db->rollBack();restore_album_images($backups);foreach($backups as $stream)fclose($stream);
verify(document_bytes($stored)===$bytes);
$bad=$doc;$bad['sha256']=str_repeat('0',64);$db->prepare('UPDATE cratelog_albums SET documents=?')->execute([json_encode([$bad])]);
$db->beginTransaction();try {migrate_documents($db);throw new LogicException('Corrupt document accepted');}catch(RuntimeException $e){$db->rollBack();}
verify(isset(json_decode($db->query('SELECT documents FROM cratelog_albums')->fetchColumn(),true)[0]['content']));
echo "PASS: inline migration, file preview, shared retention, deletion rollback, checksum failure preserves inline data\n";
