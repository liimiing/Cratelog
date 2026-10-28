<?php
require __DIR__.'/../web/cratelog_match.php';
function album(PDO $db,string $id,bool $full=false): array {return ['id'=>$id];}
$db=new PDO('sqlite::memory:');$db->exec('CREATE TABLE cratelog_albums(id TEXT,metadata TEXT)');
$insert=$db->prepare('INSERT INTO cratelog_albums VALUES(?,?)');
$add=function($id,$title,$year='2009')use($insert){$insert->execute([$id,json_encode(['音乐人'=>'Luc Ferrari','专辑名'=>$title,'出版年份'=>$year])]);};
$find=fn($title,$year='2009')=>match_album($db,['音乐人'=>'Luc Ferrari','专辑名'=>$title,'出版年份'=>$year]);
$check=function($ok){if(!$ok)throw new RuntimeException('Match assertion failed');};
$add('1','Labyrinthe de Violence DANCE');$add('2','Dialogue Ordinaire Avec La Machine / Sexolidad');
$check($find('Labyrinthe de Violence _ DANCE')['id']==='1');
$check($find('Dialogue Ordinaire Avec La Machine _ Sexolidad')['id']==='2');
$check(album_match_key('A:B',true)===album_match_key('A_B',true));
$check(album_match_key('A\\B',true)===album_match_key('A_B',true));
$add('3','Dialogue Ordinaire Avec La Machine : Sexolidad');
$check($find('Dialogue Ordinaire Avec La Machine / Sexolidad')['id']==='2');
try {$find('Dialogue Ordinaire Avec La Machine _ Sexolidad');throw new RuntimeException('Ambiguity ignored');}catch(DomainException $e){}
$check($find('Different title')===null);
$check(album_match_key('A-B',true)!==album_match_key('A B',true));
echo "PASS: Windows filename equivalence, exact precedence, ambiguity rejection, unrelated titles\n";
