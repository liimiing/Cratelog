<?php
declare(strict_types=1);
// Direct visits use the authenticated page; this file is also its import module.
if (realpath($_SERVER['SCRIPT_FILENAME'] ?? '') === __FILE__) {
    header('Location: cratelog.php?import=xlsx',true,303);
    exit;
}
// Loaded only after authentication by cratelog.php.
function xlsx_records(string $path): array {
    if (!class_exists('ZipArchive') || !function_exists('simplexml_load_string')) throw new RuntimeException('请启用 PHP zip 和 simplexml 扩展。');
    $searched=[$path];
    // The legacy page opens Records.xlsx relative to PHP's working directory.
    // Slim/front controllers can make that different from this module's directory.
    if (!is_file($path) && realpath(dirname($path))===realpath(__DIR__)) {
        $candidates=[getcwd().'/'.basename($path)];
        if (!empty($_SERVER['SCRIPT_FILENAME'])) $candidates[]=dirname($_SERVER['SCRIPT_FILENAME']).'/'.basename($path);
        foreach (array_unique($candidates) as $candidate) {
            $searched[]=$candidate;
            if (is_file($candidate)) {$path=$candidate;break;}
            foreach (@scandir(dirname($candidate)) ?: [] as $name) {
                if (strcasecmp($name,basename($candidate))===0 && is_file(dirname($candidate).'/'.$name)) {
                    $path=dirname($candidate).'/'.$name;break 2;
                }
            }
        }
    }
    if (!is_file($path)) {
        $matches=[];
        foreach (@scandir(dirname($path)) ?: [] as $name) {
            if (strcasecmp($name,basename($path))===0 && is_file(dirname($path).'/'.$name)) $matches[]=dirname($path).'/'.$name;
        }
        if (count($matches)===1) $path=$matches[0];
    }
    if (!is_file($path)) throw new RuntimeException('PHP 未找到文件。已检查：'.implode('；',array_unique($searched)).'。旧主页的相对路径也已检查；请核对 PHP 运行账号读取权限及 open_basedir 设置。');
    if (!is_readable($path)) throw new RuntimeException('文件存在，但 PHP 无读取权限：'.$path.'。请检查 PHP 运行账号权限和 open_basedir 限制。');
    if (filesize($path)===0) throw new RuntimeException('文件为空（0 字节）：'.$path.'。请重新上传完整文件。');
    $zip=new ZipArchive();
    $temporary=null;
    // Read-only access avoids requiring write permission on the source workbook.
    $result=@$zip->open($path,ZipArchive::RDONLY);
    if ($result!==true) {
        $originalError=$result;
        $temporary=@tempnam(sys_get_temp_dir(),'cratelog-xlsx-');
        if ($temporary!==false && @copy($path,$temporary)) $result=@$zip->open($temporary,ZipArchive::RDONLY);
        if ($result!==true) {
            if ($temporary!==false && is_file($temporary)) @unlink($temporary);
            $reasons=[ZipArchive::ER_NOZIP=>'不是有效的 XLSX/ZIP 文件（可能是旧 XLS、加密文件或上传不完整）',ZipArchive::ER_INCONS=>'压缩包结构损坏',ZipArchive::ER_OPEN=>'系统拒绝打开文件',ZipArchive::ER_READ=>'读取文件失败',ZipArchive::ER_NOENT=>'ZIP 库找不到文件'];
            throw new RuntimeException('文件存在，但 ZIP 读取失败：'.($reasons[$originalError] ?? 'ZIP 错误').'；错误码 '.(string)$originalError.'；大小 '.filesize($path).' 字节；路径 '.$path.'。已尝试只读方式和临时副本。可在 Excel 中另存为不加密的“Excel 工作簿 (*.xlsx)”后重新上传。');
        }
    }
    try {
        $xml=function(string $name) use ($zip): SimpleXMLElement {
            $stat=$zip->statName($name);
            if (!$stat || $stat['size']>64*1024*1024) throw new RuntimeException('工作表缺失或超过 64 MB 限制。');
            $source=$zip->getFromName($name);
            if (stripos($source,'<!DOCTYPE')!==false) throw new RuntimeException('不支持含 DOCTYPE 的工作表。');
            $node=simplexml_load_string($source,SimpleXMLElement::class,LIBXML_NONET);
            if (!$node) throw new RuntimeException('工作表 XML 无法解析。');
            return $node;
        };
        $strings=[];
        if ($zip->locateName('xl/sharedStrings.xml')!==false) {
            foreach ($xml('xl/sharedStrings.xml')->si as $si) {
                $text='';foreach ($si->xpath('.//*[local-name()="t"]') as $t) $text.=(string)$t;
                $strings[]=$text;
            }
        }
        $rows=[];
        foreach ($xml('xl/worksheets/sheet1.xml')->sheetData->row as $row) {
            $values=array_fill(0,9,'');
            foreach ($row->c as $c) {
                preg_match('/^([A-Z]+)/',(string)$c['r'],$match);$column=0;
                foreach (str_split($match[1] ?? 'A') as $letter) $column=$column*26+ord($letter)-64;
                if ($column<1 || $column>9) continue;
                $value=(string)$c->v;
                if ((string)$c['t']==='s') $value=$strings[(int)$value] ?? '';
                elseif ((string)$c['t']==='inlineStr') {
                    $value='';foreach ($c->xpath('.//*[local-name()="t"]') as $t) $value.=(string)$t;
                }
                $values[$column-1]=trim($value);
            }
            if (implode('',$values)==='') continue;
            if (in_array($values[1],['作者','音乐人','Artist'],true) && in_array($values[2],['专辑','专辑名','Album'],true)) continue;
            $rows[]=$values;
        }
        return $rows;
    } finally {$zip->close();if (is_string($temporary) && is_file($temporary)) @unlink($temporary);}
}
function import_records(PDO $db,array $rows): array {
    if ($db->getAttribute(PDO::ATTR_DRIVER_NAME)!=='sqlite') throw new RuntimeException('此导入入口仅用于 SQLite。');
    $inserted=0;$skipped=0;
    $db->beginTransaction();
    try {
        require_once __DIR__.'/cratelog_numbering.php';
        lock_album_writes($db);
        $next=next_album_number($db);
        $query=$db->prepare('SELECT 1 FROM cratelog_albums WHERE id=?');
        $insert=$db->prepare('INSERT INTO cratelog_albums(id,metadata,local_path,images,documents) VALUES(?,?,?, ?,?)');
        foreach ($rows as $row) {
            // Include all edition fields; never merge different pressings by album title alone.
            $hash=hash('sha256','cratelog-xlsx-v1:'.json_encode($row,JSON_UNESCAPED_UNICODE));
            $id=substr($hash,0,8).'-'.substr($hash,8,4).'-5'.substr($hash,13,3).'-a'.substr($hash,17,3).'-'.substr($hash,20,12);
            $query->execute([$id]);if ($query->fetchColumn()) {$skipped++;continue;}
            $metadata=array_combine(['编号','音乐人','专辑名','出版年份','唱片厂牌','唱片编号','音乐风格','载存','备注'],$row);
            $metadata['Excel 原始编号']=$row[0];
            $metadata['编号']=(string)$next++;
            if ($metadata['专辑名']==='') {$metadata['原始专辑名']='';$metadata['专辑名']='（未填写专辑名）';}
            $insert->execute([$id,json_encode($metadata,JSON_UNESCAPED_UNICODE),'','[]','[]']);$inserted++;
        }
        $db->commit();return [$inserted,$skipped];
    } catch (Throwable $e) {$db->rollBack();throw $e;}
}
function import_page(PDO $db): never {
    $_SESSION['import_csrf'] ??= bin2hex(random_bytes(32));
    $message='';$rows=[];
    try {
        $rows=xlsx_records(__DIR__.'/Records.xlsx');
        if ($_SERVER['REQUEST_METHOD']==='POST') {
            if (!hash_equals($_SESSION['import_csrf'],(string)($_POST['csrf'] ?? ''))) throw new RuntimeException('页面已过期，请刷新重试。');
            if (!hash_equals(hash('sha256',json_encode($rows)),(string)($_POST['source_hash'] ?? ''))) throw new RuntimeException('表格已变化，请重新预览后导入。');
            [$added,$skipped]=import_records($db,$rows);
            $message="导入完成：新增 $added 条，跳过已有 $skipped 条。";
        }
    } catch (Throwable $e) {$message=$e->getMessage();}
    echo '<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>导入 XLSX</title><style>body{background:#151719;color:#ddd;font:15px system-ui;margin:40px}a{color:#f6ad64}td,th{padding:10px;border-bottom:1px solid #555}button{padding:12px}</style><h1>导入 Records.xlsx</h1><p><a href="cratelog.php">返回资料库</a></p><p>'.esc($message).'</p>';
    echo '<p>读取 PHP 目录中的 Records.xlsx，共 '.count($rows).' 条，预览前 10 条。重复导入相同记录会跳过，不覆盖已有评价。原 XLSX 保留。</p><p>Excel 没有本地专辑 UUID、封面或曲目文件名；这些不会自动补齐，也不会按同名专辑强行合并播放器记录。修改 Excel 行后再次导入会作为新记录。</p><table><tr>';
    foreach (['编号','作者','专辑','年代','厂牌','版号','风格','载存','备注'] as $h) echo '<th>'.esc($h).'</th>';
    echo '</tr>';foreach (array_slice($rows,0,10) as $row) {echo '<tr>';foreach ($row as $v) echo '<td>'.esc($v).'</td>';echo '</tr>';}
    echo '</table><form method="post" action="?import=xlsx"><input type="hidden" name="csrf" value="'.esc($_SESSION['import_csrf']).'"><input type="hidden" name="source_hash" value="'.hash('sha256',json_encode($rows)).'"><button'.(!$rows?' disabled':'').'>导入 SQLite</button></form></html>';exit;
}
