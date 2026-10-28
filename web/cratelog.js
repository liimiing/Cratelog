// Persist only list state, separately for each deployed directory on this host.
const listState = document.getElementById('list-state');
const paginationFooter = document.querySelector('.pagination-footer');
if (paginationFooter) {
  const fitFooter = () => document.body.style.setProperty('--pagination-height', `${paginationFooter.offsetHeight + 24}px`);
  fitFooter();
  if (typeof ResizeObserver !== 'undefined') new ResizeObserver(fitFooter).observe(paginationFooter);
  else window.addEventListener('resize', fitFooter);
}
if (listState) {
  try {
    const key = 'cratelog:list:' + location.pathname.replace(/[^/]*$/, '');
    const params = new URLSearchParams(location.search);
    const saved = JSON.parse(localStorage.getItem(key) || 'null');
    if (!params.has('page') && !params.has('q') && saved &&
        Number.isSafeInteger(saved.page) && saved.page >= 0 && typeof saved.q === 'string' &&
        (saved.page !== Number(listState.dataset.page) || saved.q !== listState.dataset.query)) {
      const target = new URL(location.href);
      target.search = new URLSearchParams({page: String(saved.page), q: saved.q}).toString();
      location.replace(target.href);
    } else {
      localStorage.setItem(key, JSON.stringify({page: Number(listState.dataset.page), q: listState.dataset.query}));
    }
  } catch (_) { /* Browsing remains available when storage is disabled. */ }
}
document.querySelectorAll('[data-album-url]').forEach(row => {
  row.addEventListener('dblclick', event => {
    if (!event.target.closest('a,button,input')) location.assign(row.dataset.albumUrl);
  });
  row.addEventListener('keydown', event => {
    if (event.key === 'Enter' && event.target === row) location.assign(row.dataset.albumUrl);
  });
});
const lightbox = document.querySelector('.lightbox');
const previewDialog = document.querySelector('.document-preview');
if (previewDialog) {
  document.querySelectorAll('[data-preview]').forEach(link => link.addEventListener('click', event => {
    event.preventDefault();
    previewDialog.querySelector('strong').textContent = link.dataset.title;
    previewDialog.querySelector('iframe').src = link.href;
    previewDialog.showModal();
  }));
  previewDialog.querySelector('[data-close-preview]').addEventListener('click', () => previewDialog.close());
  previewDialog.addEventListener('click', event => { if (event.target === previewDialog) previewDialog.close(); });
  previewDialog.addEventListener('close', () => previewDialog.querySelector('iframe').removeAttribute('src'));
}
const aboutDialog = document.querySelector('#about-cratelog');
document.querySelector('[data-about]')?.addEventListener('click', event => { event.preventDefault(); aboutDialog?.showModal(); });
aboutDialog?.addEventListener('click', event => { if (event.target === aboutDialog) aboutDialog.close(); });
if (lightbox) {
  const buttons = [...document.querySelectorAll('[data-cover]')];
  const pictures = [...new Map(buttons.map(b => [b.dataset.cover, {src:b.dataset.cover, name:b.querySelector('img')?.alt || ''}])).values()];
  const stage = lightbox.querySelector('.picture-stage'), img = stage.querySelector('img');
  let index=0, zoom=1, angle=0, x=0, y=0, drag=null;
  function render() {
    if (!img.naturalWidth) return;
    const swap=angle%180!==0, w=img.naturalWidth, h=img.naturalHeight;
    const fit=Math.min(1,(stage.clientWidth-24)/(swap?h:w),(stage.clientHeight-24)/(swap?w:h));
    img.style.width=`${w*fit}px`; img.style.height=`${h*fit}px`;
    img.style.transform=`translate(-50%,-50%) translate(${x}px,${y}px) rotate(${angle}deg) scale(${zoom})`;
  }
  function show(i) {
    index=(i+pictures.length)%pictures.length; zoom=1;angle=0;x=0;y=0;
    img.src=pictures[index].src;img.alt=pictures[index].name;render();
  }
  function scale(factor) {zoom=Math.max(.25,Math.min(8,zoom*factor));render();}
  img.addEventListener('load',render);
  buttons.forEach(button=>button.addEventListener('click',()=>{
    lightbox.showModal();show(pictures.findIndex(p=>p.src===button.dataset.cover));
  }));
  lightbox.querySelector('[data-close-cover]').addEventListener('click',()=>lightbox.close());
  stage.querySelectorAll('[data-picture-action]').forEach(button=>button.addEventListener('click',()=>{
    const action=button.dataset.pictureAction;
    if(action==='rotate'){angle=(angle+90)%360;x=0;y=0;render();}else scale(action==='in'?1.2:1/1.2);
  }));
  stage.addEventListener('wheel',event=>{event.preventDefault();scale(Math.exp(-Math.max(-100,Math.min(100,event.deltaY*(event.deltaMode?16:1)))*.002));},{passive:false});
  stage.addEventListener('pointerdown',event=>{
    if(event.button!==0 || event.target.closest('button'))return;
    drag={id:event.pointerId,x:event.clientX,y:event.clientY,px:x,py:y,moved:false};stage.setPointerCapture(event.pointerId);
  });
  stage.addEventListener('pointermove',event=>{
    const rect=stage.getBoundingClientRect();stage.dataset.side=event.clientX-rect.left<rect.width/2?'previous':'next';
    if(!drag || drag.id!==event.pointerId)return;
    const dx=event.clientX-drag.x,dy=event.clientY-drag.y;
    if(Math.hypot(dx,dy)>5)drag.moved=true;
    if(drag.moved){x=drag.px+dx;y=drag.py+dy;render();}
  });
  stage.addEventListener('pointerup',event=>{
    if(!drag || drag.id!==event.pointerId)return;
    const moved=drag.moved;drag=null;stage.releasePointerCapture(event.pointerId);
    if(!moved){const r=stage.getBoundingClientRect();show(index+(event.clientX-r.left<r.width/2?-1:1));}
  });
  stage.addEventListener('pointercancel',()=>{drag=null;});
  stage.addEventListener('pointerleave',()=>{delete stage.dataset.side;});
  lightbox.addEventListener('keydown',event=>{
    if(event.target.closest('button') && (event.key===' ' || event.key==='Enter'))return;
    if(['ArrowRight','ArrowLeft',' '].includes(event.key)){event.preventDefault();show(index+(event.key==='ArrowLeft'?-1:1));}
    if(event.key==='+' || event.key==='=')scale(1.2);if(event.key==='-')scale(1/1.2);
  });
  lightbox.addEventListener('close',()=>{drag=null;delete stage.dataset.side;});
  window.addEventListener('resize',render);
}
