<?php
require __DIR__.'/../web/cratelog_view.php';
function verify_math($ok) {if (!$ok) throw new RuntimeException('Markdown math regression');}
$source=<<<'MD'
3. 第三行五线谱（降音/Komal）：音符下方加下划线（如 $\underline{\text{Re}}, \underline{\text{Ga}}, \underline{\text{Dha}}, \underline{\text{Ni}}$），对应五线谱上的降号（$\flat$）。
4. 第四行五线谱（升音/Tivra）：音符上方加垂直短线（如 $\dot{\text{Ma}}$），对应五线谱上的升F（$\sharp$F）。
MD;
$html=markdown_document($source);
verify_math(substr_count($html,'class="markdown-math"')===4);
verify_math(str_contains($html,'<ol start="3"><li>'));
verify_math(substr_count($html,'<li>')===2 && str_ends_with($html,'</ol>'));
verify_math(str_contains($html,'\underline{\text{Ni}}'));
verify_math(!str_contains(markdown_document('`$\flat$`'),'markdown-math'));
verify_math(!str_contains(markdown_document("```\n\$\\flat\$\n```"),'markdown-math'));
verify_math(!str_contains(markdown_inline('cost \$5 and \$10'),'markdown-math'));
verify_math(str_contains(markdown_inline('$<script>alert(1)</script>$'),'&lt;script&gt;'));
verify_math(str_contains(markdown_inline('$a**b**c$'),'a**b**c'));
foreach (['$$x^2$$', '\[x^2\]'] as $math) verify_math(str_contains(markdown_inline($math),'data-display="true"'));
verify_math(str_contains(markdown_inline('\(x^2\)'),'data-display="false"'));
verify_math(markdown_inline('$unclosed')==='$unclosed');
echo "PASS: music formulas, ordered lists, math delimiters, code and HTML safety\n";
