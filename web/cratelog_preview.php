<?php
declare(strict_types=1);
function preview_text(string $bytes,?string $charset=null): ?string {
    foreach (["\xEF\xBB\xBF"=>'UTF-8',"\xFF\xFE"=>'UTF-16LE',"\xFE\xFF"=>'UTF-16BE'] as $bom=>$encoding) {
        if (str_starts_with($bytes,$bom)) {$bytes=substr($bytes,strlen($bom));$charset=$encoding;break;}
    }
    if (!$charset && preg_match('//u',$bytes) && !str_contains($bytes,"\0")) return $bytes;
    foreach ($charset?[$charset]:['GB18030','Windows-1252'] as $encoding) {
        $text=function_exists('iconv')?@iconv($encoding,'UTF-8',$bytes):false;
        if ($text!==false && !preg_match('/[\x00-\x08\x0b\x0c\x0e-\x1f]/',$text)) return $text;
    }
    return null;
}
function preview_docx(string $bytes): ?string {
    if (!class_exists('ZipArchive') || !class_exists('DOMDocument')) return null;
    $tmp=tempnam(sys_get_temp_dir(),'cratelog-docx-');if (!$tmp)return null;
    $zip=new ZipArchive();$opened=false;
    try {
        file_put_contents($tmp,$bytes);$opened=$zip->open($tmp,ZipArchive::RDONLY)===true;
        if (!$opened)return null;
        $stat=$zip->statName('word/document.xml');if (!$stat || $stat['size']>20*1024*1024)return null;
        $xml=$zip->getFromName('word/document.xml');if (stripos($xml,'<!DOCTYPE')!==false)return null;
        $dom=new DOMDocument();if (!@$dom->loadXML($xml,LIBXML_NONET))return null;
        $render=function(DOMNode $node) use (&$render): string {
            if ($node->localName==='t')return esc($node->textContent);
            if (in_array($node->localName,['instrText','del','drawing','object'],true))return '';
            if ($node->localName==='tab')return ' &emsp; ';
            if ($node->localName==='br')return '<br>';
            $result='';foreach ($node->childNodes as $child)$result.=$render($child);
            $tags=['p'=>'p','tbl'=>'table','tr'=>'tr','tc'=>'td'];
            return isset($tags[$node->localName])?'<'.$tags[$node->localName].'>'.$result.'</'.$tags[$node->localName].'>':$result;
        };
        return $render($dom->documentElement);
    } finally {if ($opened)$zip->close();@unlink($tmp);}
}
function preview_rtf(string $bytes): ?string {
    if (!str_starts_with(ltrim($bytes),'{\\rtf'))return null;
    $out='';$buffer='';$stack=[];$skip=false;$uc=1;$fallback=0;$charset='Windows-1252';
    $flush=function() use (&$buffer,&$out,&$charset): void {$out.=preview_text($buffer,$charset) ?? ''; $buffer='';};
    for ($offset=0,$length=strlen($bytes);$offset<$length;) {
        if (!preg_match('/\G(\{|\}|\\\\\x27[0-9a-fA-F]{2}|\\\\[a-zA-Z]+-?\d* ?|\\\\[^a-zA-Z]|[^{}\\\\]+)/',$bytes,$m,0,$offset))break;
        $token=$m[0];$offset+=strlen($token);
        if ($token==='{') {$flush();$stack[]=[$skip,$uc];continue;}
        if ($token==='}') {$flush();[$skip,$uc]=array_pop($stack) ?? [false,1];continue;}
        if (preg_match('/^\\\\([a-zA-Z]+)(-?\d*) ?$/',$token,$control)) {
            $word=$control[1];$number=(int)$control[2];
            if (in_array($word,['fonttbl','colortbl','stylesheet','info','pict','object','header','footer','fldinst'],true)){$flush();$skip=true;}
            if ($word==='bin'){$offset+=max(0,$number);continue;}
            if ($skip)continue;
            if ($word==='ansicpg'){$flush();$charset='CP'.$number;}
            elseif ($word==='uc')$uc=max(0,min(16,$number));
            elseif ($word==='u'){$flush();$out.=html_entity_decode('&#'.($number<0?$number+65536:$number).';',ENT_NOQUOTES,'UTF-8');$fallback=$uc;}
            elseif (in_array($word,['par','line','row'],true)){$flush();$out.="\n";}
            elseif (in_array($word,['tab','cell'],true))$buffer.="\t";
            continue;
        }
        if ($token==='\\*'){$flush();$skip=true;continue;}
        if ($skip)continue;
        if (str_starts_with($token,"\\'"))$text=chr(hexdec(substr($token,2)));
        elseif ($token[0]==='\\')$text=match(substr($token,1)) {'~'=>' ','-'=>'','_'=>'-',default=>substr($token,1)};
        else $text=str_replace(["\r","\n"],'',$token);
        if ($fallback) {$cut=min($fallback,strlen($text));$text=substr($text,$cut);$fallback-=$cut;}
        $buffer.=$text;
    }
    $flush();return '<pre>'.esc($out).'</pre>';
}
function preview_mime(string $bytes,int $depth=0): ?string {
    if ($depth>8)return null;
    $parts=preg_split('/\r?\n\r?\n/',$bytes,2);if(count($parts)!==2)return null;
    [$header,$body]=$parts;$header=preg_replace('/\r?\n[ \t]+/',' ',$header);
    if (preg_match('/boundary\s*=\s*(?:"([^"]+)"|([^;\s]+))/i',$header,$m)) {
        $boundary=$m[1]?:($m[2] ?? '');$chunks=explode('--'.$boundary,$body);
        foreach (array_slice($chunks,1,200) as $chunk) { $html=preview_mime(ltrim($chunk,"\r\n"),$depth+1);if($html!==null)return $html; }
        return null;
    }
    if (!preg_match('/Content-Type:\s*text\/(html|plain)/i',$header,$m))return null;
    $type=strtolower($m[1]);
    if (preg_match('/Content-Transfer-Encoding:\s*base64/i',$header))$body=base64_decode(preg_replace('/\s/','',$body),true) ?: '';
    elseif (preg_match('/Content-Transfer-Encoding:\s*quoted-printable/i',$header))$body=quoted_printable_decode($body);
    $charset=preg_match('/charset\s*=\s*["\x27]?([\w-]+)/i',$header,$m)?$m[1]:null;
    $text=preview_text($body,$charset);return $text===null?null:($type==='html'?$text:'<pre>'.esc($text).'</pre>');
}
function preview_doc(string $bytes): ?string {
    if (str_starts_with(ltrim($bytes),'{\\rtf'))return preview_rtf($bytes);
    $tool=getenv('CRATELOG_ANTIWORD') ?: '';
    if (!$tool || !is_file($tool) || !function_exists('proc_open'))return null;
    $tmp=tempnam(sys_get_temp_dir(),'cratelog-doc-');if(!$tmp)return null;
    try {
        file_put_contents($tmp,$bytes);
        $process=proc_open([$tool,'-m','UTF-8.txt',$tmp],[0=>['pipe','r'],1=>['pipe','w'],2=>['file',PHP_OS_FAMILY==='Windows'?'NUL':'/dev/null','a']],$pipes,null,null,['bypass_shell'=>true,'create_no_window'=>true]);
        if (!is_resource($process))return null;
        fclose($pipes[0]);stream_set_blocking($pipes[1],false);$out='';$deadline=microtime(true)+8;
        do {$out.=stream_get_contents($pipes[1]);$status=proc_get_status($process);if (!$status['running'])break;usleep(20000);} while(microtime(true)<$deadline && strlen($out)<10*1024*1024);
        if ($status['running'])proc_terminate($process);
        $out.=stream_get_contents($pipes[1]);fclose($pipes[1]);proc_close($process);
        return !$status['running'] && $status['exitcode']===0 && trim($out)!==''?'<pre>'.esc($out).'</pre>':null;
    } finally {@unlink($tmp);}
}
function readable_preview(array $document): ?string {
    static $cache=[];$key=$document['sha256'].':'.$document['filename'];
    if (array_key_exists($key,$cache))return $cache[$key];
    $bytes=document_bytes($document);$ext=strtolower(pathinfo($document['filename'],PATHINFO_EXTENSION));
    try {$html=match($ext) {
        'docx'=>preview_docx($bytes),'rtf'=>preview_rtf($bytes),'doc'=>preview_doc($bytes),
        'mht','mhtml'=>preview_mime($bytes),
        'md','txt','htm','html'=>($text=preview_text($bytes))===null?null:match($ext){'md'=>markdown_document($text),'txt'=>'<pre>'.esc($text).'</pre>',default=>$text},
        default=>null,
    };} catch(Throwable $e){$html=null;}
    return $cache[$key]=$html;
}
