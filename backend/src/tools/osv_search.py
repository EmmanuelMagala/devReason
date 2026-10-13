import asyncio
import json
import hashlib
import httpx
from cvss import CVSS2, CVSS3, CVSS4
from src.core.redis_client import create_redis_pool

OSV_URL = 'https://api.osv.dev/v1/querybatch'


def _extract_cvss(vuln: dict) -> float | None:
    scores = []
    for severity in vuln.get('severity',[]):
        try:
            vector = str(severity['score'])
            if vector.startswith('CVSS:4'): score = CVSS4(vector).scores()[0]
            elif vector.startswith('CVSS:3'): score = CVSS3(vector).scores()[0]
            elif vector.startswith('AV:'): score = CVSS2(vector).scores()[0]
            else: score = float(vector)
            if 0 <= score <= 10: scores.append(score)
        except Exception:
            continue
    return max(scores) if scores else None


def _parse_osv_result(pkg: dict, result: dict) -> list[dict]:
    return [{'package':pkg['name'], 'version':pkg['version'], 'source_file':pkg.get('source_file'),
        'cve_id':next((alias for alias in vuln.get('aliases',[]) if isinstance(alias,str) and alias.startswith('CVE-')),vuln.get('id','')),
        'osv_id':vuln.get('id'), 'cvss_score':_extract_cvss(vuln), 'summary':vuln.get('summary','Vulnerability found; severity is not published'),
        'cwe_id':next((value for value in vuln.get('database_specific',{}).get('cwe_ids',[]) if isinstance(value,str) and value.startswith('CWE-')),None),
        'fixed_versions':[event['fixed'] for affected in vuln.get('affected',[]) for span in affected.get('ranges',[]) for event in span.get('events',[]) if 'fixed' in event],
    } for vuln in result.get('vulns',[])]


async def osv_batch_query(packages: list[dict]) -> list[dict]:
    if not packages: return []
    redis = await create_redis_pool()
    semaphore = asyncio.Semaphore(6)
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            async def lookup(pkg):
                key = 'osv:v2:'+hashlib.sha256(f"{pkg['ecosystem']}:{pkg['name']}:{pkg['version']}".encode()).hexdigest()
                records = None
                try:
                    cached = await redis.get(key)
                    if cached: records = json.loads(cached)
                except Exception: pass
                if records is None:
                    records, page = [], None
                    async with semaphore:
                        while True:
                            body = {'package':{'name':pkg['name'],'ecosystem':pkg['ecosystem']},'version':pkg['version']}
                            if page: body['page_token'] = page
                            response = await client.post('https://api.osv.dev/v1/query',json=body)
                            response.raise_for_status()
                            payload = response.json()
                            records.extend(payload.get('vulns',[]))
                            page = payload.get('next_page_token')
                            if not page: break
                    try: await redis.setex(key,86400,json.dumps(records))
                    except Exception: pass
                return _parse_osv_result(pkg,{'vulns':records})
            groups = await asyncio.gather(*(lookup(pkg) for pkg in packages))
            return [v for group in groups for v in group]
    finally:
        await redis.aclose()
