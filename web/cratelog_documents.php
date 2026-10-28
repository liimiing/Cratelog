<?php
declare(strict_types=1);
function docs_dir(): string { return data_dir().'/docs'; }
function document_path(string $hash): string {
    if (!preg_match('/^[a-f0-9]{64}$/D',$hash)) throw new RuntimeException('Invalid document hash');
    return docs_dir().'/'.$hash;
}
function stored_document_bytes(array $document): string {
    if (($document['storage'] ?? '')==='file') {
        $path=document_path($document['sha256']);
        if (is_link($path) || !is_file($path)) throw new RuntimeException('附件文件不存在');
        $bytes=file_get_contents($path);
        if ($bytes===false) throw new RuntimeException('附件读取失败');
        return $bytes;
    }
    $bytes=($document['encoding'] ?? '')==='base64'?base64_decode($document['content'] ?? '',true):($document['content'] ?? '');
    if ($bytes===false) throw new RuntimeException('Invalid document encoding');
    return $bytes;
}
function externalize_document(array $document): array {
    if (($document['storage'] ?? '')==='file') return $document;
    $bytes=stored_document_bytes($document);$hash=$document['sha256'];
    if (!hash_equals($hash,hash('sha256',$bytes))) throw new RuntimeException('Document checksum mismatch');
    $dir=docs_dir();
    if (!is_dir($dir) && !mkdir($dir,0700,true) && !is_dir($dir)) throw new RuntimeException('Cannot create docs directory');
    $path=document_path($hash);
    if (is_link($path)) throw new RuntimeException('Invalid document path');
    if (file_exists($path)) {
        if (!is_file($path) || hash_file('sha256',$path)!==$hash) throw new RuntimeException('Stored document checksum mismatch');
    } else {
        $tmp=tempnam($dir,'.upload-');if (!$tmp) throw new RuntimeException('Cannot create document');
        try {
            if (file_put_contents($tmp,$bytes)!==strlen($bytes) || hash_file('sha256',$tmp)!==$hash || !rename($tmp,$path)) throw new RuntimeException('Document save failed');
        } finally {if (is_file($tmp)) unlink($tmp);}
    }
    return ['filename'=>$document['filename'],'sha256'=>$hash,'storage'=>'file','size'=>strlen($bytes)];
}
function migrate_documents(PDO $db): void {
    // Caller holds the write transaction. A failed migration keeps inline data intact.
    $ids=$db->query('SELECT id FROM cratelog_albums')->fetchAll(PDO::FETCH_COLUMN);
    $read=$db->prepare('SELECT documents FROM cratelog_albums WHERE id=?');
    $write=$db->prepare('UPDATE cratelog_albums SET documents=? WHERE id=?');
    foreach ($ids as $id) {
        $read->execute([$id]);$docs=json_decode($read->fetchColumn(),true,512,JSON_THROW_ON_ERROR);$read->closeCursor();$changed=false;
        foreach ($docs as &$doc) if (array_key_exists('content',$doc)) {$doc=externalize_document($doc);$changed=true;}
        unset($doc);
        if ($changed) $write->execute([json_encode($docs,JSON_UNESCAPED_UNICODE|JSON_THROW_ON_ERROR),$id]);
    }
}
