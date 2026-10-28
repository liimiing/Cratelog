"""New web features exercised against the isolated running PHP server."""
import json
import re
import shutil
import sqlite3
import io
from PIL import Image
from cratelog_library import load_album, payload, Remote, Conflict, atomic_json


def check_web_features(base, url, token, session, db_path=None):
    remote=Remote(url,token)
    headers={'Authorization':'Bearer '+token}
    root=base/'feature-albums';root.mkdir(exist_ok=True)
    seed=load_album(root)
    seed['metadata']={'音乐人':'Feature Artist','专辑名':'Feature Album','出版年份':'2001','编号':'9000','唱片厂牌':'','备注':'保留网页内容'}
    seed['rating']=4.5;seed['personal_comment']='保留评价'
    seed['local_path']=''
    response=session.post(url,headers=headers,data={'album':json.dumps(payload(seed)),'revision':0},timeout=10)
    assert response.status_code==200,response.text
    seed_number=int(response.json()['album']['metadata']['编号'])
    folder=root/'Feature Artist -2001- Feature Album';folder.mkdir(exist_ok=True)
    (folder/'01 test.wav').write_bytes(b'RIFF test fixture')
    shutil.copyfile(base/'cover.jpg',folder/'shared.jpg')
    Image.new('RGB',(60,60),'blue').save(folder/'unique.png')
    atomic_json(folder/'album_info.json',{'音乐人':'Wrong artist','专辑名':'Wrong title','唱片厂牌':'New Label','备注':'不能覆盖','曲目表':json.dumps([{'位置':'1','标题':'76.1','时长':'6:06'}])})
    originals={ext:('文档 '+ext).encode() if ext in ('md','txt') else b'\x00\xff\x80binary-'+ext.encode() for ext in ('md','txt','doc','docx','pdf','rtf','htm','mht','mhtml')}
    pdf=io.BytesIO();Image.new('RGB',(40,40),'white').save(pdf,format='PDF');originals['pdf']=pdf.getvalue()
    originals['htm']=b'<h1>HTML preview</h1><script>alert(1)</script>'
    (folder/'too-large.txt').write_bytes(b'x'*(5*1024*1024+1))
    for ext,content in originals.items(): (folder/('notes.'+ext)).write_bytes(content)
    result=remote.sync(folder)
    assert result['skipped_files']==['too-large.txt']
    linked=load_album(folder)
    assert linked['id']==seed['id']
    saved=remote.fetch(linked)
    assert saved['metadata']['音乐人']=='Feature Artist'
    assert saved['metadata']['唱片厂牌']=='New Label' and saved['metadata']['备注']=='保留网页内容'
    assert saved['rating']==4.5 and saved['personal_comment']=='保留评价'
    assert int(saved['metadata']['编号'])==seed_number
    assert saved['local_path']==payload(load_album(folder))['local_path']
    assert load_album(folder)['local_path']==str(folder.resolve())
    catalog=remote.catalog()
    assert catalog.contains(folder)
    assert catalog.contains(root/'Feature Artist -2001- Feature Album')
    assert not catalog.contains(root/'Absent Artist -2001- Absent Album')
    web=url.replace('_api','')
    detail=session.get(web,params={'album':saved['id']},timeout=10)
    assert '<td>76.1</td>' in detail.text and '<td>6:06</td>' in detail.text
    assert '<dialog class="lightbox"' in detail.text
    for doc in saved['documents']:
        download=session.get(web,params={'album':saved['id'],'document':doc['sha256']},timeout=10)
        assert download.content==originals[doc['filename'].split('.')[-1]]
        ext=doc['filename'].split('.')[-1]
        preview=session.get(web,params={'album':saved['id'],'document':doc['sha256'],'preview':1},timeout=10)
        assert preview.status_code==(200 if ext in ('md','txt','pdf','htm') else 415)
        if ext=='htm':assert 'sandbox;' in preview.headers['Content-Security-Policy']
        if ext=='pdf':
            assert preview.headers['Content-Type']=='application/pdf' and preview.content==originals['pdf']
    edit_url=web+'?album='+saved['id']+'&edit=1'
    edit=session.get(edit_url,timeout=10)
    csrf=re.search(r'name="csrf" value="([^"]+)"',edit.text)[1]
    data={'csrf':csrf,'revision':saved['_revision'],'action':'save','rating':'3.5','comment':'网页修改','path':saved['local_path']}
    data['selected[0]']='on';data['highlighted[0]']='on'
    data.update({'metadata['+key+']':value for key,value in saved['metadata'].items()})
    denied=session.post(edit_url,data={**data,'csrf':'bad'},timeout=10)
    assert '页面已过期' in denied.text and remote.fetch(linked)['_revision']==saved['_revision']
    edited=session.post(edit_url,data=data,timeout=10)
    assert edited.history and edited.history[0].status_code==303
    updated=remote.fetch(linked)
    assert updated['personal_comment']=='网页修改' and updated['rating']==3.5
    assert updated['tracks'][0]['selected'] and updated['tracks'][0]['highlighted']
    stale=session.post(edit_url,data=data,timeout=10)
    assert '资料已被其他页面' in stale.text
    try:remote.sync(folder)
    except Conflict:pass
    else:raise AssertionError('web edit conflict was not detected')
    images={i['filename']:i['sha256'] for i in updated['images']}
    if db_path:
        with sqlite3.connect(db_path) as db:
            db.execute("CREATE TRIGGER fail_delete BEFORE DELETE ON cratelog_albums BEGIN SELECT RAISE(ABORT,'test rollback'); END")
        failed=session.post(edit_url,data={'csrf':csrf,'revision':updated['_revision'],'action':'delete'},timeout=10)
        assert not failed.history and remote.fetch(linked) is not None
        restored=session.get(web,params={'image':images['unique.png']},timeout=10)
        assert restored.content==(folder/'unique.png').read_bytes()
        with sqlite3.connect(db_path) as db:db.execute('DROP TRIGGER fail_delete')
    deleted=session.post(edit_url,data={'csrf':csrf,'revision':updated['_revision'],'action':'delete'},timeout=10)
    assert deleted.history and remote.fetch(linked) is None
    assert session.get(web,params={'image':images['unique.png']},timeout=10).status_code==404
    assert session.get(web,params={'image':images['shared.jpg']},timeout=10).status_code==200
    assert (folder/'notes.pdf').is_file()
    previous_revision=load_album(folder)['_revision']
    remote.sync(folder)
    recreated=remote.fetch(load_album(folder))
    assert recreated is not None and recreated['_revision']==previous_revision+1
    assert recreated['id']==linked['id'] and len(recreated['documents'])==9
    assert session.get(web,params={'image':images['unique.png']},timeout=10).content==(folder/'unique.png').read_bytes()
    remote.sync(folder)
    assert remote.fetch(load_album(folder))['_revision']==previous_revision+2
    print('PASS: folder matching, empty-only merge, six attachment types, parsed tracks, web edit/delete, CSRF and version checks')
