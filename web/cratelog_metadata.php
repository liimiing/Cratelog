<?php
declare(strict_types=1);
function normalize_metadata(array $metadata): array {
    if (!array_key_exists('厂牌编号',$metadata)) return $metadata;
    $old=$metadata['厂牌编号'];$current=$metadata['唱片编号'] ?? null;
    $empty=fn($value)=>$value===null || $value===[] || (is_string($value) && trim($value)==='');
    if ($empty($current)) {
        if (!$empty($old)) $metadata['唱片编号']=$old;
        unset($metadata['厂牌编号']);
    } elseif ($empty($old) || $old===$current || (is_string($old) && is_string($current) && trim($old)===trim($current))) {
        unset($metadata['厂牌编号']);
    }
    return $metadata;
}
