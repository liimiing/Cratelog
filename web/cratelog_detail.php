<?php
$tracklist=$m['曲目表'] ?? [];
if (is_string($tracklist)) $tracklist=json_decode($tracklist,true) ?: [];
if (!is_array($tracklist)) $tracklist=[];
?>
<?php if (array_key_exists('厂牌编号',$m)): ?><p class="muted">此专辑的「唱片编号」与旧字段「厂牌编号」内容不同，已保留两份原值，请编辑核对。</p><?php endif ?>
<section class="album-hero">
<?php if ($a['images']): ?><button class="cover-button" data-cover="?image=<?=esc($a['images'][0]['sha256'])?>" aria-label="查看封面大图"><img src="?image=<?=esc($a['images'][0]['sha256'])?>" alt="专辑封面"></button><?php endif ?>
<div><div class="eyebrow">ALBUM · <?=esc($m['编号'] ?? '')?></div><h2><?=esc($m['专辑名'] ?? '未命名专辑')?></h2><p><a href="cratelog.php?q=<?=esc(rawurlencode(display_value($m['音乐人'] ?? '')))?>&amp;page=0"><?=esc(display_value($m['音乐人'] ?? ''))?></a></p><p class="muted"><?=esc($m['出版年份'] ?? '')?> · <?=esc(preg_replace('/\s+/u',' ',display_value($m['唱片厂牌'] ?? '')))?></p><p><?=stars($a['rating'])?></p><?php if ($isAdmin): ?><a class="action" href="?album=<?=esc($a['id'])?>&amp;edit=1">编辑 / 删除</a><?php endif ?><a class="action" href="<?=esc($douban)?>" target="_blank" rel="noopener noreferrer">豆瓣音乐搜索 ↗</a></div>
</section><p><a href="cratelog.php">← 返回列表</a></p>
<div class="detail-grid"><div>
<article><h3>曲目</h3>
<?php if ($tracklist): ?><table class="track-table"><?php foreach ($tracklist as $t): if (!is_array($t)) continue; ?><tr><td><?=esc($t['位置'] ?? $t['position'] ?? '')?></td><td><?=esc($t['标题'] ?? $t['title'] ?? '')?></td><td><?=esc($t['时长'] ?? $t['duration'] ?? '')?></td></tr><?php endforeach ?></table><?php else: ?><p class="muted">暂无曲目资料</p><?php endif ?>
</article>
<article><h3>专辑资料</h3><dl class="facts">
<?php foreach ($m as $key=>$value): if (in_array($key,['来源','导入来源','曲目表','专辑名','音乐人','匹配相似度','原始文件夹名'],true)) continue; ?><dt><?=esc($key)?></dt><dd><?php if ($key==='Discogs ID' && preg_match('/^[1-9][0-9]*$/D',trim(display_value($value)))): ?><a href="https://www.discogs.com/release/<?=esc(trim(display_value($value)))?>" target="_blank" rel="noopener noreferrer"><?=esc(display_value($value))?></a><?php else: ?><?=esc(display_value($value))?><?php endif ?></dd><?php endforeach ?>
</dl></article><article><h3>封面与内页</h3><div class="gallery"><?php foreach ($a['images'] as $pic): ?><button class="cover-button" data-cover="?image=<?=esc($pic['sha256'])?>" aria-label="<?=esc($pic['filename'])?>"><img src="?image=<?=esc($pic['sha256'])?>" alt="<?=esc($pic['filename'])?>"></button><?php endforeach ?></div></article></div><aside><article><h3>音频文件</h3><?php if ($a['tracks']): ?><table><?php foreach ($a['tracks'] as $t): ?><tr><td><?=esc($t['display_name'] ?? $t['filename'])?></td><td class="marks"><?=$t['highlighted']?'★ ':''?><?=$t['selected']?'✓':''?></td></tr><?php endforeach ?></table><?php else: ?><p class="muted">暂无音频文件</p><?php endif ?></article>
<article><h3>收藏信息</h3><dl class="facts"><dt>本地目录</dt><dd><?=esc($a['local_path'] ?: '未关联本地目录')?></dd><dt>更新时间</dt><dd><?=esc($a['_updated_at'])?></dd></dl></article>
<article><h3>个人评论</h3><div class="comment"><?=esc($a['personal_comment'] ?: '尚未填写个人评论')?></div></article>
<article><h3>文档与附件</h3><?php if (!$a['documents']): ?><p class="muted">暂无附件</p><?php endif ?>
<?php foreach ($a['documents'] as $doc): $ext=strtolower(pathinfo($doc['filename'],PATHINFO_EXTENSION)); ?>
<section class="attachment"><a href="?album=<?=esc($a['id'])?>&amp;document=<?=esc($doc['sha256'])?>"><?=esc($doc['filename'])?> ↓ 下载</a>
<?php if (document_preview_type($doc)): ?><a class="preview-link" href="?album=<?=esc($a['id'])?>&amp;document=<?=esc($doc['sha256'])?>&amp;preview=1" data-preview data-title="<?=esc($doc['filename'])?>">预览</a><?php endif ?></section><?php endforeach ?></article>
<article><h3>相关专辑</h3>
<?php if (!$related): ?><p class="muted">暂无该作者的其他专辑</p><?php endif ?>
<div class="related-albums"><?php foreach ($related as $other): $om=json_decode($other['metadata'],true) ?: []; $oi=json_decode($other['images'],true) ?: []; ?>
<a class="related-album" href="?album=<?=esc(rawurlencode($other['id']))?>">
<?php if ($oi): ?><img loading="lazy" src="?image=<?=esc($oi[0]['sha256'])?>" alt="<?=esc(display_value($om['专辑名'] ?? ''))?>"><?php else: ?><span class="related-placeholder" aria-hidden="true">♫</span><?php endif ?>
<span><strong><?=esc(display_value($om['专辑名'] ?? '未命名专辑'))?></strong><small><?=esc(display_value($om['出版年份'] ?? ''))?></small></span></a>
<?php endforeach ?></div></article></aside></div>
<dialog class="lightbox" aria-label="封面大图"><button type="button" data-close-cover aria-label="关闭大图">×</button><div class="picture-stage"><img alt="封面大图" draggable="false"><span class="picture-arrow previous" aria-hidden="true">‹</span><span class="picture-arrow next" aria-hidden="true">›</span><div class="picture-top"><div class="picture-tools"><button type="button" data-picture-action="rotate" aria-label="顺时针旋转" title="旋转">↻</button><button type="button" data-picture-action="in" aria-label="放大" title="放大">＋</button><button type="button" data-picture-action="out" aria-label="缩小" title="缩小">−</button></div></div></div></dialog>

<dialog class="document-preview" aria-labelledby="preview-title"><header><strong id="preview-title">附件预览</strong><button type="button" data-close-preview>关闭 ×</button></header><iframe title="附件内容"></iframe><p class="muted">若浏览器无法显示 PDF，可关闭预览后下载查看。</p></dialog>
