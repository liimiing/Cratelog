<?php
require __DIR__.'/../web/cratelog_view.php';
function check($ok) {if (!$ok) throw new RuntimeException('Markdown regression');}
$md="| 篇章 | 序号 | 曲名 |\n| --- | --- | --- |\n| **I. Chapter**<br>\n\n<br>（章节一） | 1 | First |\n| | 2 | Second |\n| **II. Chapter**<br>\n\n<br>（章节二） | 3 | Third |\n| | 4 | Fourth |\n\nAfter";
$html=markdown_document($md);
check(substr_count($html,'rowspan="2"')===2);
check(str_contains($html,'<strong>I. Chapter</strong><br><br>（章节一）'));
check(substr_count($html,'<tr>')===5 && str_contains($html,'<p>After</p>'));
check(markdown_cells('| a\\|b | `x|y` |')===['a|b','`x|y`']);
check(markdown_inline('`<br>` <br/> <script>alert(1)</script>')==='<code>&lt;br&gt;</code> <br> &lt;script&gt;alert(1)&lt;/script&gt;');
check(!str_contains(markdown_document("```\n| A | B |\n| --- | --- |\n```"),'<table'));
check(!str_contains(markdown_document("| A | B |\n| --- | --- |\n| X | 1 |\n| | 2 |"),'rowspan'));
echo "PASS: tables, broken BR rows, chapter spans, escaped pipes and HTML/code safety\n";
