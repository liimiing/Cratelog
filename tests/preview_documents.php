<?php
require __DIR__.'/../web/cratelog_view.php';
function check_preview(string $name,string $bytes,string $expected): void {
    $doc=['filename'=>$name,'sha256'=>hash('sha256',$bytes),'content'=>base64_encode($bytes),'encoding'=>'base64'];
    $html=readable_preview($doc);
    if ($html===null || !str_contains($html,$expected) || document_preview_type($doc)==='') throw new RuntimeException('Preview failed: '.$name.' '.($html ?? 'NULL'));
}
check_preview('gbk.txt',iconv('UTF-8','GB18030','中文评论'), '中文评论');
check_preview('utf16.txt',"\xFF\xFE".iconv('UTF-8','UTF-16LE','中文评论'),'中文评论');
check_preview('notes.rtf','{\rtf1\ansi{\fonttbl hidden}\u20013?\u25991?\par second line}','中文');
check_preview('disguised.doc','{\rtf1 readable text}','readable text');
check_preview('archive.mht',"MIME-Version: 1.0\r\nContent-Type: multipart/related; boundary=\"part\"\r\n\r\n--part\r\nContent-Type: text/html; charset=utf-8\r\nContent-Transfer-Encoding: base64\r\n\r\n".base64_encode('<h1>网页正文</h1>')."\r\n--part--\r\n",'<h1>网页正文</h1>');
$tmp=tempnam(sys_get_temp_dir(),'test-docx-');$zip=new ZipArchive();$zip->open($tmp,ZipArchive::OVERWRITE);
$zip->addFromString('word/document.xml','<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>正文</w:t></w:r></w:p><w:tbl><w:tr><w:tc><w:p><w:r><w:t>表格</w:t></w:r></w:p></w:tc></w:tr></w:tbl></w:body></w:document>');$zip->close();
check_preview('test.docx',file_get_contents($tmp),'<table><tr><td><p>表格</p></td></tr></table>');unlink($tmp);
$bad=['filename'=>'bad.docx','sha256'=>'bad','content'=>'not a zip'];if(document_preview_type($bad)!=='')throw new RuntimeException('Invalid DOCX exposed preview');
echo "PASS: GBK/UTF-16 text, RTF Unicode, RTF-in-DOC, MHT MIME decoding, DOCX paragraphs/tables, unsupported-file filtering\n";
