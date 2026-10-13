import asyncio
import re
from pathlib import PurePosixPath
from src.agents.state import ReviewState, Finding
from src.tools.dependencies import MANIFESTS, SUPPORTED, extract_packages
from src.tools.osv_search import osv_batch_query

SECRET_PATTERNS = [
    (r'(?i)(api[_-]?key|apikey)\s*=\s*["\']?([A-Za-z0-9_\-]{20,})','hardcoded_api_key'),
    (r'(?i)(secret|password|passwd|pwd)\s*=\s*["\']([^"\']{8,})["\']','hardcoded_secret'),
    (r'ghp_[A-Za-z0-9]{36}','github_token'), (r'sk-[A-Za-z0-9_-]{40,}','openai_key'),
    (r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----','private_key'),
]


def _scan_for_secrets(diff):
    return [Finding(agent='security_agent',severity='critical',type=issue,file=None,line=None,message=f"Potential {issue.replace('_',' ')} detected",suggestion='Remove the secret and rotate the credential.') for pattern,issue in SECRET_PATTERNS for _ in re.finditer(pattern,diff)]


_extract_packages = extract_packages


async def run(state: ReviewState) -> dict:
    findings = _scan_for_secrets(state.pr_diff)
    packages, warnings = [], []
    parsed_locks=set()
    for file in state.changed_files:
        if PurePosixPath(file['path']).name in {'package-lock.json','npm-shrinkwrap.json','poetry.lock','Cargo.lock'}:
            try:
                extract_packages(file)
                parsed_locks.add(file['path'])
            except (ValueError,KeyError,TypeError): pass
    for file in state.changed_files:
        name = PurePosixPath(file['path']).name
        if name not in MANIFESTS: continue
        companion={'package.json':('package-lock.json','npm-shrinkwrap.json'),'pyproject.toml':('poetry.lock',),'Cargo.toml':('Cargo.lock',)}.get(name,())
        if any(str(PurePosixPath(file['path']).parent/lock) in parsed_locks for lock in companion): continue
        try:
            extracted = extract_packages(file)
            packages.extend(extracted)
            if name not in SUPPORTED: warnings.append(f"{file['path']}: resolved dependency coverage is unsupported without a supported lockfile")
            elif not extracted and file.get('content','').strip(): warnings.append(f"{file['path']}: no resolved versions available; dependency coverage is incomplete")
        except (ValueError, KeyError, TypeError): warnings.append(f"{file['path']}: dependency file could not be parsed")
    try:
        vulnerabilities = await asyncio.wait_for(osv_batch_query(packages),timeout=90)
        for vuln in vulnerabilities:
            score = vuln.get('cvss_score')
            fixes = vuln.get('fixed_versions',[])
            findings.append(Finding(agent='security_agent',severity='critical' if score is not None and score>=9 else 'high' if score is not None and score>=7 else 'medium' if score is None or score>=4 else 'low',type='cve',file=vuln.get('source_file'),message=f"{vuln['cve_id']}: {vuln['package']} {vuln['version']}: {vuln['summary']}",suggestion='Upgrade to '+', '.join(fixes) if fixes else f"Review {vuln['cve_id']} and select a patched version",cvss_score=score,cwe_id=vuln.get('cwe_id')))
        status = {'status':'partial' if warnings else 'completed','warnings':warnings,'finding_count':len(findings),'packages_scanned':len(packages)}
    except Exception:
        status = {'status':'failed','error':'Dependency vulnerability lookup failed. Findings are incomplete.','warnings':warnings}
    return {'security_findings':findings,'completed_agents':['security_agent'],'agent_status':{'security_agent':status}}
