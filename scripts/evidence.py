"""Validate source acquisition states and dated travel quote claims offline."""
from __future__ import annotations
import argparse,json
from datetime import datetime
from pathlib import Path
from urllib.parse import parse_qs,urlparse

SECRET_KEYS={'key','api_key','apikey','token','access_token','csrf','sessdata','xsec_token','cookie','cookies','authorization','password','secret','bili_jct'}

def credential_paths(value,path='root'):
    found=[]
    if isinstance(value,dict):
        for key,item in value.items():
            child=path+'.'+str(key)
            if str(key).lower() in SECRET_KEYS:found.append(child)
            if isinstance(item,str) and item.startswith(('https://','http://')):
                if SECRET_KEYS.intersection(k.lower() for k in parse_qs(urlparse(item).query)):found.append(child)
            found.extend(credential_paths(item,child))
    elif isinstance(value,list):
        for i,item in enumerate(value):found.extend(credential_paths(item,f'{path}[{i}]'))
    return found

def date_ok(value):
    try:datetime.fromisoformat(value.replace('Z','+00:00'));return True
    except (ValueError,AttributeError,TypeError):return False

def public_url(value):
    if not isinstance(value,str):return False
    p=urlparse(value);return p.scheme in {'https','http'} and bool(p.netloc)

def validate_sources(sources,root):
    if not isinstance(sources,list):return ['sources must be an array']
    errors=[];seen=set()
    for i,s in enumerate(sources):
        prefix=f'sources[{i}]'
        if not isinstance(s,dict):errors.append(prefix+' must be an object');continue
        for key in ['id','title','author']:
            if not isinstance(s.get(key),str) or not s[key].strip():errors.append(prefix+' '+key+' required')
        if s.get('id') in seen:errors.append(prefix+' duplicate source id')
        seen.add(s.get('id'))
        original=s.get('platform')=='original' or s.get('status')=='original' or s.get('verification')=='planning_assumption'
        if not original and not public_url(s.get('url')):errors.append(prefix+' public source url required')
        if not date_ok(s.get('captured_at',s.get('checked_at'))):errors.append(prefix+' capture/check date required')
        status=s.get('status','reference')
        if status not in {'reference','verified_text','linked_only','captured','blocked','original'}:errors.append(prefix+' unknown acquisition status')
        if status=='captured':
            local=s.get('asset_path',s.get('evidence_path'))
            if not isinstance(local,str) or not (Path(root)/local).is_file():errors.append(prefix+' captured status requires an existing local file')
        if status in {'linked_only','blocked'} and s.get('included_in_video') is True:errors.append(prefix+' unavailable material cannot be included in video')
    errors += ['credential field or URL at '+p for p in credential_paths(sources,'sources')]
    return errors

def validate_quotes(quotes,root):
    if not isinstance(quotes,list):return ['quotes must be an array']
    errors=[];seen=set()
    for i,q in enumerate(quotes):
        prefix=f'quotes[{i}]'
        if not isinstance(q,dict):errors.append(prefix+' must be an object');continue
        if not q.get('id') or q.get('id') in seen:errors.append(prefix+' unique id required')
        seen.add(q.get('id'))
        if not q.get('provider'):errors.append(prefix+' provider required')
        if not date_ok(q.get('checked_at')):errors.append(prefix+' query check date required')
        kind=q.get('kind');claim=q.get('claim','display');query=q.get('query')
        if kind not in {'flight','hotel','train','ticket','package'}:errors.append(prefix+' valid kind required')
        if claim not in {'display','generic','locked','unavailable'}:errors.append(prefix+' unknown price claim')
        if not isinstance(query,dict):errors.append(prefix+' query object required');query={}
        if claim not in {'generic','unavailable'}:
            fields={'flight':['dep_date'],'train':['dep_date'],'hotel':['check_in_date','check_out_date'],'ticket':['visit_date'],'package':['travel_date']}.get(kind,[])
            for field in fields:
                if not date_ok(query.get(field)):errors.append(prefix+' travel date condition missing: '+field)
            for field in ({'flight':['origin','destination'],'train':['origin','destination'],'hotel':['dest_name']}.get(kind,[])):
                if not query.get(field):errors.append(prefix+' route/destination condition missing: '+field)
        if q.get('price') is not None:
            for field in ['currency','unit']:
                if not q.get(field):errors.append(prefix+' price '+field+' required')
        elif claim not in {'unavailable','generic'}:errors.append(prefix+' displayed/locked price required')
        response=q.get('response_path')
        if response is not None and (not isinstance(response,str) or not (Path(root)/response).is_file()):errors.append(prefix+' response file missing')
        if claim=='locked':
            proof=q.get('lock_evidence')
            if not isinstance(proof,str) or not (public_url(proof) or (Path(root)/proof).is_file()):errors.append(prefix+' locked price requires supplier lock_evidence')
            if not date_ok(q.get('expires_at')):errors.append(prefix+' locked price requires expiry date')
    errors += ['credential field or URL at '+p for p in credential_paths(quotes,'quotes')]
    return errors

def validate_task(root):
    root=Path(root);errors=[]
    for name,validator in [('sources.json',validate_sources),('quotes.json',validate_quotes)]:
        try:value=json.loads((root/name).read_text(encoding='utf-8'));errors.extend(validator(value,root))
        except (OSError,ValueError,TypeError):errors.append(name+' must be readable valid JSON')
    return errors

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('command',choices=['validate']);p.add_argument('task_dir',type=Path);a=p.parse_args()
    errors=validate_task(a.task_dir);print(json.dumps({'valid':not errors,'errors':errors},ensure_ascii=False));return int(bool(errors))

if __name__=='__main__':raise SystemExit(main())
