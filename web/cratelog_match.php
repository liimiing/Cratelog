<?php
declare(strict_types=1);
require_once __DIR__.'/cratelog_metadata.php';
function album_match_key($value,bool $filename=false): string {
    $value=(string)$value;
    if ($filename) $value=preg_replace('~[_<>:"/\\\\|?*＜＞：＂／＼｜？＊]+~u',' ',$value);
    $value=trim(preg_replace('/\s+/u',' ',$value));
    return function_exists('mb_strtolower')?mb_strtolower($value,'UTF-8'):strtolower($value);
}
function match_album(PDO $db,array $metadata): ?array {
    $normal=fn($v)=>album_match_key($v);
    $artist=$normal($metadata['音乐人'] ?? '');$title=$normal($metadata['专辑名'] ?? '');
    if ($artist==='' || $title==='') return null;
    $matches=[];$fallback=[];
    $safeArtist=album_match_key($artist,true);$safeTitle=album_match_key($title,true);
    foreach ($db->query('SELECT id,metadata FROM cratelog_albums') as $row) {
        $m=json_decode($row['metadata'],true);
        if ($normal($m['音乐人'] ?? '')===$artist && $normal($m['专辑名'] ?? '')===$title) $matches[]=$row;
        elseif ($safeArtist!=='' && $safeTitle!=='' && album_match_key($m['音乐人'] ?? '',true)===$safeArtist && album_match_key($m['专辑名'] ?? '',true)===$safeTitle) $fallback[]=$row;
    }
    if (!$matches) $matches=$fallback;
    if (count($matches)>1) {
        $year=(string)($metadata['出版年份'] ?? '');
        $sameYear=array_values(array_filter($matches,fn($r)=>(string)(json_decode($r['metadata'],true)['出版年份'] ?? '')===$year));
        if (count($sameYear)===1) $matches=$sameYear;
        else throw new DomainException('存在多个同名专辑，无法安全自动合并，请先在网页核对重复记录。');
    }
    return $matches?album($db,$matches[0]['id'],true):null;
}
function fill_album(array $existing,array $incoming): array {
    $empty=fn($v)=>$v===null || $v==='' || $v===[] || (is_string($v) && trim($v)==='');
    $metadata=normalize_metadata((array)$existing['metadata']);
    $incoming['metadata']=normalize_metadata($incoming['metadata']);
    foreach (['唱片编号','厂牌编号'] as $key) {
        $left=$metadata[$key] ?? null;$right=$incoming['metadata'][$key] ?? null;
        if (!$empty($left) && !$empty($right) && $left!==$right &&
            (!is_string($left) || !is_string($right) || trim($left)!==trim($right)))
            throw new UnexpectedValueException('本地与远端的'.$key.'不同，请在冲突面板核对后选择。');
    }
    foreach ($incoming['metadata'] as $k=>$v) if (!array_key_exists($k,$metadata) || $empty($metadata[$k])) $metadata[$k]=$v;
    $incoming['id']=$existing['id'];$incoming['metadata']=$metadata;
    foreach (['local_path','personal_comment','tracks'] as $key) if (!$empty($existing[$key])) $incoming[$key]=$existing[$key];
    if ($existing['rating']>0) $incoming['rating']=$existing['rating'];
    return $incoming;
}
function merge_files(array $existing,array $incoming): array {
    $names=array_column($existing,'filename');
    foreach ($incoming as $file) if (!in_array($file['filename'],$names,true)) {$existing[]=$file;$names[]=$file['filename'];}
    return $existing;
}
