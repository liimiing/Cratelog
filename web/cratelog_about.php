<?php $brand=json_decode(file_get_contents(__DIR__.'/cratelog-brand.json'),true); ?>
<dialog id="about-cratelog" aria-labelledby="about-heading" style="background:#202428;color:#e7e7e7;border:1px solid #454e56;border-radius:16px;padding:32px;text-align:center;max-width:400px">
<img src="assets/cratelog.svg?v=2" width="80" height="80" alt="Cratelog 唱片 C">
<h2 id="about-heading" style="color:#f59a38">Cratelog <?=esc($brand['version'])?></h2>
<p>音乐收藏 · 整理 · 聆听</p><p>开发者：<?=esc($brand['developer'])?></p>
<p><a href="<?=esc($brand['website'])?>" target="_blank" rel="noopener noreferrer">like-mix.com ↗</a></p>
<p class="muted"><?=esc($brand['copyright'])?></p>
<form method="dialog"><button>关闭</button></form>
</dialog>
