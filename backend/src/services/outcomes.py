FAILED = {'failed','timeout','rule_lookup_failed','missing_tool','retrying'}


def review_outcome(statuses: dict, error=None, coverage=None) -> str:
    if error or statuses.get('fetch_pr',{}).get('status')=='failed': return 'failed'
    checks=[statuses.get(name,{}).get('status') for name in ('code_analyst','security_agent','semantic_security_agent','architecture_agent') if name in statuses]
    if checks and all(status in FAILED for status in checks): return 'failed'
    if any(value.get('status') in FAILED | {'partial'} for value in statuses.values()): return 'partial'
    if coverage and not coverage.get('scope_complete',True): return 'partial'
    return 'completed'
