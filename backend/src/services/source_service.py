import base64
import asyncio
from pathlib import PurePosixPath
from urllib.parse import quote
from src.core.github_api import request, paginate
from src.core.settings import settings
from src.tools.dependencies import MANIFESTS
from src.agents.context_selection import SOURCE_EXTENSIONS

EXCLUDED={'node_modules','vendor','dist','build','coverage','.git','.next','__pycache__','.venv','.venv-win','venv','generated','__generated__','.nuxt','.svelte-kit','.cache','target'}


def eligible(path):
    parts=PurePosixPath(path).parts
    name=PurePosixPath(path).name
    return not any(part in EXCLUDED for part in parts) and '.generated.' not in name and not name.endswith(('.min.js','_pb2.py','_pb2_grpc.py')) and (PurePosixPath(path).suffix in SOURCE_EXTENSIONS or name in MANIFESTS)


def eligible_paths(paths):
    # Compact declarations precede source; large lockfiles follow source so a
    # large dependency graph cannot consume the entire source character budget.
    locks={'package-lock.json','npm-shrinkwrap.json','poetry.lock','Cargo.lock','yarn.lock','pnpm-lock.yaml'}
    def priority(path):
        name=PurePosixPath(path).name
        return (2 if name in locks or name.endswith('.lock') or name.endswith('-lock.json') else 0 if name in MANIFESTS else 1,path)
    return sorted(set(path for path in paths if eligible(path)),key=priority)


async def file_content(token,owner,name,sha,path):
    data=await request(token,'GET',f'/repos/{owner}/{name}/contents/{quote(path,safe="/")}',params={'ref':sha})
    if data.get('encoding')!='base64' or data.get('type')!='file': raise ValueError('File contents are unavailable or binary')
    return base64.b64decode(data['content']).decode('utf-8')


async def tree_paths(token,owner,name,sha):
    root=f'/repos/{owner}/{name}/git/trees/'
    data=await request(token,'GET',root+sha,params={'recursive':1})
    if not data.get('truncated'): return [item['path'] for item in data['tree'] if item['type']=='blob']
    # GitHub recursive tree responses may be truncated; walk individual subtrees.
    queue=[('',sha)]; paths=[]
    while queue:
        prefix,ref=queue.pop(0)
        data=await request(token,'GET',root+ref)
        for item in data['tree']:
            path=prefix+item['path']
            if item['type']=='blob': paths.append(path)
            elif item['type']=='tree' and item['path'] not in EXCLUDED: queue.append((path+'/',item['sha']))
    return paths


async def select_files(token,owner,name,sha,paths,scope):
    available=eligible_paths(paths)
    all_eligible=list(available)
    offset=scope.get('offset',0)
    if not isinstance(offset,int) or isinstance(offset,bool) or offset<0: raise ValueError('Invalid scope offset')
    requested=scope.get('paths')
    if requested is not None:
        if not isinstance(requested,list) or any(not isinstance(path,str) or path not in available for path in requested): raise ValueError('Selected files must belong to the eligible repository scope')
        available=list(dict.fromkeys(requested))
    selected=available[offset:offset+settings.review_max_files]
    files=[]; omitted=[]; truncated=[]; characters=0; budget_skipped=[]; next_offsets={}; ranges=[]
    file_offsets=scope.get('file_offsets',{})
    if not isinstance(file_offsets,dict) or any(path not in available or not isinstance(start,int) or isinstance(start,bool) or start<0 for path,start in file_offsets.items()): raise ValueError('Invalid file content offsets')
    for path in selected:
        if characters>=settings.review_max_characters: budget_skipped.append(path); continue
        try: content=await file_content(token,owner,name,sha,path)
        except Exception: omitted.append(path); continue
        total=len(content); start=file_offsets.get(path,0)
        if start>=total and total: omitted.append(path); continue
        remaining=settings.review_max_characters-characters
        end=min(total,start+remaining)
        if start or end<total: truncated.append(path)
        if end<total: next_offsets[path]=end
        ranges.append({'path':path,'start':start,'end':end,'total':total})
        start_line=content[:start].count('\n')+1
        content=content[start:end]
        characters+=len(content)
        files.append({'path':path,'content':content,'start_line':start_line})
    reviewed=[file['path'] for file in files]
    skipped=[path for path in paths if path not in reviewed]
    next_offset=offset+len(selected)
    coverage={'total_files':len(paths),'eligible_files':len(all_eligible),'selected_files':len(selected),'reviewed_files':len(files),'reviewed_paths':reviewed,'skipped_files':len(skipped),'skipped_paths':skipped,'truncated_files':truncated,'unavailable_files':omitted,'characters':characters,'scope_complete':not omitted and not truncated and len(files)==len(all_eligible),'next_offset':next_offset if requested is None and next_offset<len(available) else None,'commit_sha':sha}
    coverage.update(reviewed_ranges=ranges,budget_skipped_files=budget_skipped,next_file_offsets=next_offsets)
    coverage['scope_complete']=coverage['scope_complete'] and not budget_skipped
    return files,coverage


async def pr_context(token,owner,name,number,sha,scope):
    base=f'/repos/{owner}/{name}'
    metadata=await request(token,'GET',f'{base}/pulls/{number}')
    if sha and metadata['head']['sha']!=sha: raise ValueError('This pull request changed after submission. Start a new review of its latest commit.')
    sha=sha or metadata['head']['sha']
    entries=await paginate(token,f'{base}/pulls/{number}/files',max_pages=30,allow_limit=True)
    paths=[entry['filename'] for entry in entries if entry.get('status')!='removed']
    files,coverage=await select_files(token,owner,name,sha,paths,scope)
    reviewed=set(coverage['reviewed_paths'])
    patches=[f"=== {entry['filename']} ===\n{entry.get('patch','')}" for entry in entries if entry['filename'] in reviewed]
    coverage['removed_files']=[entry['filename'] for entry in entries if entry.get('status')=='removed']
    coverage['missing_patches']=[entry['filename'] for entry in entries if entry['filename'] in reviewed and not entry.get('patch')]
    coverage['_analysis_diff']='\n\n'.join(patches)
    missing=max(0,metadata.get('changed_files',len(entries))-len(entries))
    coverage['unlisted_changed_files']=missing
    coverage['total_changed_files']=metadata.get('changed_files',len(entries))
    if missing: coverage['scope_complete']=False
    # Secret detection examines every available patch; LLMs receive only the
    # selected analysis diff and source files.
    raw_diff='\n\n'.join(f"=== {entry['filename']} ===\n{entry.get('patch','')}" for entry in entries)
    return metadata,files,raw_diff,coverage
