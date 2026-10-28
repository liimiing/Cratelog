<?php
require __DIR__.'/../web/cratelog_import.php';
$db=new PDO('sqlite::memory:',null,null,[PDO::ATTR_ERRMODE=>PDO::ERRMODE_EXCEPTION]);
$db->exec(file_get_contents(__DIR__.'/../web/cratelog_sqlite.sql'));
$rows=xlsx_records(__DIR__.'/../web/Records.xlsx');
if (count($rows)!==7482 || $rows[0][1]!=='Beatles') throw new RuntimeException('Unexpected workbook content');
[$added,$skipped]=import_records($db,$rows);
if ($added+$skipped!==count($rows) || $added<7000) throw new RuntimeException('Import count mismatch');
$db->exec("UPDATE cratelog_albums SET rating=4.5,personal_comment='keep'");
[$again,$duplicates]=import_records($db,array_reverse($rows));
if ($again!==0 || $duplicates!==count($rows)) throw new RuntimeException('Repeated import duplicated rows');
if ((int)$db->query("SELECT COUNT(*) FROM cratelog_albums WHERE personal_comment='keep' AND rating=4.5")->fetchColumn()!==$added) throw new RuntimeException('Review overwritten');
$row=['999999','New Artist','New Album','2026','','','','',''];
import_records($db,[$row]);
$new=json_decode($db->query("SELECT metadata FROM cratelog_albums WHERE json_extract(metadata,'$.专辑名')='New Album'")->fetchColumn(),true);
if ((int)$new['编号']!==$added+1 || $new['Excel 原始编号']!=='999999') throw new RuntimeException('Sequential number assignment failed');
echo "PASS: $added imported, $skipped duplicate rows skipped; reordered reimport preserves reviews\n";
