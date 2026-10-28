<?php
declare(strict_types=1);
require_once __DIR__.'/cratelog_documents.php';
require_once __DIR__.'/cratelog_metadata.php';
// Optional local configuration; environment variables take precedence.
$configFile=__DIR__.'/cratelog_config.php';
if (is_file($configFile)) {
    $config=require $configFile;
    foreach (['CRATELOG_ANTIWORD','CRATELOG_API_TOKEN','CRATELOG_DATA_DIR','CRATELOG_IMAGE_DIR','CRATELOG_DSN','CRATELOG_DB_USER','CRATELOG_DB_PASSWORD'] as $key) {
        if (!getenv($key) && isset($config[$key])) putenv($key.'='.$config[$key]);
    }
}
function db(): PDO {
    $dsn = getenv('CRATELOG_DSN') ?: 'sqlite:'.data_dir().'/cratelog.sqlite';
    $db = new PDO($dsn,
        getenv('CRATELOG_DB_USER') ?: '', getenv('CRATELOG_DB_PASSWORD') ?: '',
        [PDO::ATTR_ERRMODE => PDO::ERRMODE_EXCEPTION, PDO::ATTR_EMULATE_PREPARES => false]);
    if ($db->getAttribute(PDO::ATTR_DRIVER_NAME) === 'sqlite') {
        $db->exec('PRAGMA busy_timeout=15000');
        $db->exec('PRAGMA foreign_keys=ON');
        $db->exec('PRAGMA journal_mode=WAL');
        if ((int)$db->query('PRAGMA user_version')->fetchColumn() < 2) {
            $db->beginTransaction();
            try {
                $db->exec(file_get_contents(__DIR__.'/cratelog_sqlite.sql'));
                $columns=$db->query('PRAGMA table_info(cratelog_albums)')->fetchAll(PDO::FETCH_COLUMN,1);
                foreach (['personal_comment'=>"TEXT NOT NULL DEFAULT ''",'documents'=>"TEXT NOT NULL DEFAULT '[]'"] as $name=>$type) {
                    if (!in_array($name,$columns,true)) $db->exec("ALTER TABLE cratelog_albums ADD COLUMN $name $type");
                }
                $db->exec('PRAGMA user_version=2');
                $db->commit();
            } catch (Throwable $e) { $db->rollBack(); throw $e; }
        }
    }
    if ($db->getAttribute(PDO::ATTR_DRIVER_NAME)==='sqlite' && (int)$db->query('PRAGMA user_version')->fetchColumn()<3) {
        $db->beginTransaction();
        try {
            $db->exec('UPDATE cratelog_albums SET revision=revision WHERE 0');
            migrate_documents($db);
            $db->exec('PRAGMA user_version=3');$db->commit();
        } catch (Throwable $e) {$db->rollBack();throw $e;}
    }
    if ($db->getAttribute(PDO::ATTR_DRIVER_NAME)==='sqlite') {
        $columns=$db->query('PRAGMA table_info(cratelog_tracks)')->fetchAll(PDO::FETCH_COLUMN,1);
    } else {
        $columns=$db->query('SHOW COLUMNS FROM cratelog_tracks')->fetchAll(PDO::FETCH_COLUMN,0);
    }
    if (!in_array('display_name',$columns,true)) $db->exec("ALTER TABLE cratelog_tracks ADD COLUMN display_name VARCHAR(1024) NOT NULL DEFAULT ''");
    return $db;
}
function data_dir(): string {
    // Outside the public PHP directory, including on servers that ignore .htaccess.
    $path=getenv('CRATELOG_DATA_DIR') ?: dirname(__DIR__).'/cratelog-data';
    if (!is_dir($path) && !mkdir($path,0700,true) && !is_dir($path)) throw new RuntimeException('Cannot create Cratelog data directory');
    return rtrim($path,'/\\');
}
function authorized(string $token): bool {
    $expected = getenv('CRATELOG_API_TOKEN') ?: '';
    return strlen($expected) >= 32 && hash_equals($expected, $token);
}
function album(PDO $db, string $id, bool $includeDocuments = false): ?array {
    $s = $db->prepare('SELECT * FROM cratelog_albums WHERE id=?'); $s->execute([$id]);
    $a = $s->fetch(PDO::FETCH_ASSOC);
    if (!$a) return null;
    $s = $db->prepare('SELECT filename,selected,highlighted,display_name FROM cratelog_tracks WHERE album_id=? ORDER BY position');
    $s->execute([$id]); $tracks = $s->fetchAll(PDO::FETCH_ASSOC);
    foreach ($tracks as &$t) { if ($t['display_name']==='') unset($t['display_name']); $t['selected'] = (bool)$t['selected']; $t['highlighted'] = (bool)$t['highlighted']; }
    $documents = json_decode($a['documents'] ?? '[]',true) ?: [];
    if (!$includeDocuments) $documents = array_map(fn($d)=>['filename'=>$d['filename'],'sha256'=>$d['sha256']],$documents);
    return ['id'=>$id,'rating'=>(float)$a['rating'],'personal_comment'=>$a['personal_comment'] ?? '',
        'documents'=>$documents,'local_path'=>$a['local_path'],
        'metadata'=>(object)normalize_metadata(json_decode($a['metadata'],true)),'images'=>json_decode($a['images'],true),
        'tracks'=>$tracks,'_revision'=>(int)$a['revision'],'_updated_at'=>$a['updated_at']];
}
function image_dir(): string {
    $path = getenv('CRATELOG_IMAGE_DIR');
    if (!$path) $path=data_dir().'/images';
    return rtrim($path, '/\\');
}
