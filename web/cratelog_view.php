<?php
declare(strict_types=1);
require_once __DIR__.'/cratelog_preview.php';
require_once __DIR__.'/cratelog_documents.php';
function esc($value): string { return htmlspecialchars((string)$value,ENT_QUOTES|ENT_SUBSTITUTE,'UTF-8'); }
function document_bytes(array $document): string {
    return stored_document_bytes($document);
}
function document_preview_type(array $document): string {
    $ext=strtolower(pathinfo($document['filename'],PATHINFO_EXTENSION));$bytes=document_bytes($document);
    if ($ext==='pdf' && str_starts_with($bytes,'%PDF-')) return 'pdf';
    if (readable_preview($document)!==null) return $ext;
    return '';
}
function display_value($value): string {
    return is_array($value) || is_object($value)
        ? json_encode($value,JSON_PRETTY_PRINT|JSON_UNESCAPED_UNICODE|JSON_UNESCAPED_SLASHES)
        : (string)$value;
}
function stars(float $rating,bool $onlyStars=false): string {
    $rating=max(0,min(5,$rating));
    return '<span class="stars" aria-label="'.esc($rating).' / 5"><span>★★★★★</span><span class="star-fill" style="width:'.($rating*20).'%">★★★★★</span></span>'.($onlyStars?'':' <span class="muted">'.($rating?esc($rating).' / 5':'未评分').'</span>');
}
function short_comment(string $text): string {
    preg_match_all('/\X/u',$text,$characters);
    return implode('',array_slice($characters[0],0,30));
}
function markdown_inline(string $text): string {
    $parts=preg_split('/(`[^`]+`)/u',$text,-1,PREG_SPLIT_DELIM_CAPTURE);
    return implode('',array_map(function($part) {
        if (str_starts_with($part,'`') && str_ends_with($part,'`')) return '<code>'.esc(substr($part,1,-1)).'</code>';
        $part=esc($part);
        $part=preg_replace('/&lt;br\s*\/?&gt;/i','<br>',$part);
        $part=preg_replace('/\*\*([^*]+)\*\*/u','<strong>$1</strong>',$part);
        return preg_replace_callback('/\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/u',function($m) {
            return '<a href="'.$m[2].'" target="_blank" rel="noopener noreferrer">'.$m[1].'</a>';
        },$part);
    },$parts));
}
function markdown_cells(string $line): array {
    $line=trim($line);
    if (str_starts_with($line,'|')) $line=substr($line,1);
    if (str_ends_with($line,'|') && !str_ends_with($line,'\\|')) $line=substr($line,0,-1);
    // Keep escaped pipes and pipes inside inline code in their original cell.
    preg_match_all('/`[^`]*`|\\\\.|[^|`\\\\]+|[|`\\\\]/u',$line,$tokens);
    $cells=[''];
    foreach ($tokens[0] as $token) {
        if ($token==='|') $cells[]='';
        else $cells[count($cells)-1].=$token==='\\|'?'|':$token;
    }
    return array_map('trim',$cells);
}
function markdown_table(array $headers,array $align,array $rows): string {
    $html='<div style="overflow-x:auto"><table style="width:100%;border-collapse:collapse"><thead><tr>';
    $cellStyle=fn($i)=>'border:1px solid #aaa;padding:8px;text-align:'.$align[$i].';vertical-align:top';
    foreach ($headers as $i=>$value) $html.='<th style="'.$cellStyle($i).'">'.markdown_inline($value).'</th>';
    $html.='</tr></thead><tbody>';$skipUntil=-1;
    foreach ($rows as $r=>$row) {
        $html.='<tr>';
        foreach ($headers as $i=>$_) {
            if ($i===0 && $r<$skipUntil) continue;
            $span=1;
            // A multiline chapter cell followed by empty chapter cells forms a group.
            if ($i===0 && preg_match('/<br\s*\/?>/i',$row[0])) {
                while (isset($rows[$r+$span]) && $rows[$r+$span][0]==='') $span++;
                $skipUntil=$r+$span;
            }
            $html.='<td'.($span>1?' rowspan="'.$span.'"':'').' style="'.$cellStyle($i).'">'.markdown_inline($row[$i]).'</td>';
        }
        $html.='</tr>';
    }
    return $html.'</tbody></table></div>';
}
function markdown_document(string $text): string {
    $text=preg_replace('/^\xEF\xBB\xBF/','',$text);
    $html='';$code=false;$lines=[];$paragraph=[];$list=false;
    $flush=function() use (&$html,&$paragraph) {
        if ($paragraph) {$html.='<p>'.markdown_inline(implode("\n",$paragraph)).'</p>'; $paragraph=[];}
    };
    $input=preg_split('/\r\n|\r|\n/',$text);
    for ($n=0;$n<count($input);$n++) {
        $line=$input[$n];
        if (preg_match('/^\s*```/',$line)) {
            $flush(); if ($list) {$html.='</ul>'; $list=false;}
            if ($code) {$html.='<pre><code>'.esc(implode("\n",$lines)).'</code></pre>'; $lines=[];}
            $code=!$code;continue;
        }
        if ($code) {$lines[]=$line;continue;}
        if (str_contains($line,'|') && isset($input[$n+1])) {
            $headers=markdown_cells($line);$separators=markdown_cells($input[$n+1]);
            if (count($headers)===count($separators) && count($headers)>1 &&
                count(array_filter($separators,fn($cell)=>preg_match('/^:?-{3,}:?$/',$cell)))===count($headers)) {
                $flush();if ($list) {$html.='</ul>';$list=false;}
                $align=array_map(fn($cell)=>str_starts_with($cell,':') && str_ends_with($cell,':')?'center':(str_ends_with($cell,':')?'right':'left'),$separators);
                $rows=[];$n++;
                while (isset($input[$n+1]) && str_contains($input[$n+1],'|')) {
                    $end=$n+1;$rowLine=$input[$end];$row=markdown_cells($rowLine);
                    // Repair only explicit <br> continuations, never swallow ordinary prose.
                    if (count($row)<count($headers) && preg_match('/<br\s*\/?>\s*$/i',$rowLine)) {
                        $next=$end+1;
                        while (isset($input[$next]) && trim($input[$next])==='') $next++;
                        if (isset($input[$next]) && preg_match('/^\s*<br\s*\/?>/i',$input[$next])) {
                            $rowLine.=$input[$next];$row=markdown_cells($rowLine);$end=$next;
                        }
                    }
                    if (count($row)!==count($headers)) break;
                    $rows[]=$row;$n=$end;
                }
                $html.=markdown_table($headers,$align,$rows);continue;
            }
        }

        if (preg_match('/^\s*[-*+]\s+(.+)$/u',$line,$m)) {
            $flush();if (!$list) {$html.='<ul>'; $list=true;}
            $html.='<li>'.markdown_inline($m[1]).'</li>';continue;
        }
        if ($list) {$html.='</ul>'; $list=false;}
        if (preg_match('/^(#{1,6})\s+(.+)$/u',$line,$m)) {
            $flush();$level=strlen($m[1]);$html.='<h'.$level.'>'.markdown_inline($m[2]).'</h'.$level.'>';
        } elseif (preg_match('/^>\s?(.*)$/u',$line,$m)) {
            $flush();$html.='<blockquote>'.markdown_inline($m[1]).'</blockquote>';
        } elseif (trim($line)==='') {$flush();}
        else {$paragraph[]=$line;}
    }
    $flush();if ($list) $html.='</ul>';
    if ($code) $html.='<pre><code>'.esc(implode("\n",$lines)).'</code></pre>';
    return $html;
}
