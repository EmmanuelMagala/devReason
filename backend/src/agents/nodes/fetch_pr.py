from src.agents.state import ReviewState
from src.core.urls import parse_pr_url
from src.services.source_service import pr_context, tree_paths, select_files


async def run(state: ReviewState):
    config=state.repo_config
    token=config.github_token.get_secret_value()
    number=state.pr_number
    diff=''; coverage={}
    try:
        if config.mode=='snapshot':
            if not config.commit_sha: raise ValueError('Snapshot review requires an immutable commit')
            paths=await tree_paths(token,config.owner,config.name,config.commit_sha)
            files,coverage=await select_files(token,config.owner,config.name,config.commit_sha,paths,config.scope)
            metadata={'title':f'{config.owner}/{config.name} · {config.branch}','head':{'sha':config.commit_sha}}
            diff='\n\n'.join(f"=== {file['path']} ===\n{file['content']}" for file in files)
        else:
            owner,name,number,_=parse_pr_url(state.pr_url)
            if (owner.lower(),name.lower())!=(config.owner.lower(),config.name.lower()): raise ValueError('PR repository mismatch')
            metadata,files,diff,coverage=await pr_context(token,owner,name,number,config.commit_sha,config.scope)
        analysis_diff=coverage.pop('_analysis_diff',diff)
        if not files: raise ValueError('No eligible readable source files were found in this scope')
        return {'pr_number':number,'pr_metadata':metadata,'pr_diff':diff,'analysis_diff':analysis_diff,'changed_files':files,'coverage':coverage,'agent_status':{'fetch_pr':{'status':'completed','selected_file_count':len(files),'total_changed_files':coverage['total_files'],'changed_file_count':len(files)}}}
    except Exception as error:
        message=str(error) if isinstance(error,ValueError) else 'GitHub code could not be loaded. Check access and retry.'
        coverage.pop('_analysis_diff',None)
        return {'pr_number':number,'pr_diff':diff,'analysis_diff':'','changed_files':[],'coverage':coverage,'error':message,'agent_status':{'fetch_pr':{'status':'failed','error':message}}}
