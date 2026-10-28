<?php
require __DIR__.'/../web/cratelog_common.php';
require __DIR__.'/../web/cratelog_match.php';
function verify($condition): void {if (!$condition) throw new RuntimeException('Catalog alias regression');}
$cases=[
    [['唱片编号'=>'OLD'],['唱片编号'=>'OLD']],
    [['厂牌编号'=>'NEW'],['唱片编号'=>'NEW']],
    [['唱片编号'=>'','厂牌编号'=>'NEW'],['唱片编号'=>'NEW']],
    [['唱片编号'=>'SAME','厂牌编号'=>'SAME'],['唱片编号'=>'SAME']],
    [['唱片编号'=>'OLD','厂牌编号'=>'NEW'],['唱片编号'=>'OLD','厂牌编号'=>'NEW']],
];
$db=new PDO('sqlite::memory:');$db->setAttribute(PDO::ATTR_ERRMODE,PDO::ERRMODE_EXCEPTION);
$db->exec(file_get_contents(__DIR__.'/../web/cratelog_sqlite.sql'));
foreach ($cases as $i=>[$input,$expected]) {
    verify(normalize_metadata($input)===$expected);
    $raw=json_encode($input,JSON_UNESCAPED_UNICODE);
    $db->prepare('INSERT INTO cratelog_albums(id,local_path,metadata,images) VALUES(?,?,?,?)')->execute([(string)$i,'',$raw,'[]']);
    verify((array)album($db,(string)$i)['metadata']===$expected);
    verify($db->query("SELECT metadata FROM cratelog_albums WHERE id='$i'")->fetchColumn()===$raw);
}
try {
    fill_album(['metadata'=>['唱片编号'=>'OLD']],['metadata'=>['厂牌编号'=>'NEW']]);
    throw new RuntimeException('Conflicting values were silently merged');
} catch (UnexpectedValueException $e) {}
echo "PASS: alias compatibility, conflicting values preserved, existing SQLite JSON unchanged\n";
