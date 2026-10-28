<?php
declare(strict_types=1);
function lock_album_writes(PDO $db): void {
    // Take SQLite's write lock before reading MAX, even when the table is empty.
    if ($db->getAttribute(PDO::ATTR_DRIVER_NAME)==='sqlite') $db->exec('UPDATE cratelog_albums SET revision=revision WHERE 1=0');
}
function next_album_number(PDO $db): int {
    $maximum=0;
    foreach ($db->query('SELECT metadata FROM cratelog_albums') as $row) {
        $metadata=json_decode($row['metadata'],true);
        $maximum=max($maximum,(int)($metadata['编号'] ?? 0));
    }
    return $maximum+1;
}
