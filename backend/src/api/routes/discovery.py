import uuid
from urllib.parse import quote
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func, exists, or_
from src.api.deps import get_current_user, get_db
from src.db.models import Repo, GitHubInstallation, GitHubConnection
from src.schemas.repo import RepoRead
from src.services.github_connection_service import authorize_repo
from src.core.github_app import mint_installation_token
from src.core.github_api import request, paginate
from src.services.source_service import tree_paths, eligible_paths
from src.core.settings import settings

router=APIRouter()


async def owned_repo(db,repo_id,user_id):
    repo=(await db.execute(select(Repo).where(Repo.id==repo_id,Repo.clerk_user_id==user_id))).scalar_one_or_none()
    if not repo: raise HTTPException(404,'Repository not found')
    return repo


@router.get('/browse')
async def browse(q: str='',account: str|None=None,page: int=Query(1,ge=1),page_size: int=Query(20,ge=1,le=100),sort: str='recent',user=Depends(get_current_user),db=Depends(get_db)):
    verified=exists(select(GitHubInstallation.id).join(GitHubConnection,GitHubInstallation.connection_id==GitHubConnection.id).where(GitHubConnection.clerk_user_id==user['clerk_user_id'],GitHubInstallation.installation_id==Repo.github_installation_id,GitHubInstallation.status=='connected',GitHubConnection.status=='connected'))
    filters=[Repo.clerk_user_id==user['clerk_user_id'],verified]
    if q:
        pattern='%'+q.replace('%','\\%').replace('_','\\_')+'%'
        filters.append(or_(Repo.name.ilike(pattern,escape='\\'),Repo.owner.ilike(pattern,escape='\\'),(Repo.owner+'/'+Repo.name).ilike(pattern,escape='\\')))
    if account: filters.append(Repo.owner==account)
    rows=(await db.execute(select(Repo,func.count().over().label('total_count')).where(*filters).order_by(Repo.name if sort=='name' else Repo.created_at.desc(),Repo.id).offset((page-1)*page_size).limit(page_size))).all()
    total=rows[0].total_count if rows else (await db.execute(select(func.count()).select_from(Repo).where(*filters))).scalar_one()
    return {'items':[RepoRead.model_validate(row[0]) for row in rows],'total':total,'page':page,'page_size':page_size,'branch_reviews_enabled':settings.branch_reviews_enabled}


@router.get('/{repo_id}')
async def detail(repo_id: uuid.UUID,user=Depends(get_current_user),db=Depends(get_db)) -> RepoRead:
    return RepoRead.model_validate(await owned_repo(db,repo_id,user['clerk_user_id']))


@router.get('/{repo_id}/pulls')
async def pulls(repo_id: uuid.UUID,state: str=Query('open',pattern='^(open|closed|all)$'),page: int=Query(1,ge=1),user=Depends(get_current_user),db=Depends(get_db)):
    repo=await owned_repo(db,repo_id,user['clerk_user_id'])
    token=await authorize_repo(db,user['clerk_user_id'],repo)
    items=await request(token,'GET',f'/repos/{repo.owner}/{repo.name}/pulls',params={'state':state,'page':page,'per_page':20,'sort':'updated','direction':'desc'})
    return {'items':[{'number':p['number'],'title':p['title'],'url':p['html_url'],'author':p['user']['login'],'branch':p['head']['ref'],'commit_sha':p['head']['sha'],'draft':p['draft'],'updated_at':p['updated_at']} for p in items],'page':page,'has_next':len(items)==20}


@router.get('/{repo_id}/branches')
async def branches(repo_id: uuid.UUID,page: int=Query(1,ge=1),user=Depends(get_current_user),db=Depends(get_db)):
    repo=await owned_repo(db,repo_id,user['clerk_user_id'])
    token=await authorize_repo(db,user['clerk_user_id'],repo)
    items=await request(token,'GET',f'/repos/{repo.owner}/{repo.name}/branches',params={'page':page,'per_page':100})
    return {'items':[{'name':branch['name'],'commit_sha':branch['commit']['sha']} for branch in items],'page':page,'has_next':len(items)==100}


@router.get('/{repo_id}/scope')
async def scope(repo_id: uuid.UUID,branch: str,offset: int=Query(0,ge=0),commit_sha: str|None=Query(None,pattern=r'^[0-9a-f]{40}$'),user=Depends(get_current_user),db=Depends(get_db)):
    if not settings.branch_reviews_enabled: raise HTTPException(409,'Branch reviews are not enabled yet')
    repo=await owned_repo(db,repo_id,user['clerk_user_id'])
    token=await authorize_repo(db,user['clerk_user_id'],repo)
    commit=await request(token,'GET',f'/repos/{repo.owner}/{repo.name}/commits/{quote(commit_sha or branch,safe="")}')
    paths=await tree_paths(token,repo.owner,repo.name,commit['sha'])
    available=eligible_paths(paths)
    return {'commit_sha':commit['sha'],'total_files':len(paths),'eligible_files':len(available),'paths':available[offset:offset+settings.review_max_files],'offset':offset,'next_offset':offset+settings.review_max_files if offset+settings.review_max_files<len(available) else None,'character_limit':settings.review_max_characters,'file_limit':settings.review_max_files}
