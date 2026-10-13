import re
from urllib.parse import urlsplit


def parse_pr_url(value: str) -> tuple[str, str, int, str]:
    try:
        url = urlsplit(value.strip())
        match = re.fullmatch(r'/([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+)/pull/([1-9][0-9]*)(?:/(?:files|commits|checks))?/?', url.path)
        if url.scheme != 'https' or url.netloc.lower() != 'github.com' or not match:
            raise ValueError()
        owner, name, number = match.groups()
        return owner, name, int(number), f'https://github.com/{owner}/{name}/pull/{number}'
    except (ValueError, AttributeError):
        raise ValueError('Enter a GitHub pull request URL, such as https://github.com/owner/repo/pull/42') from None
