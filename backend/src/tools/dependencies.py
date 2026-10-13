"""Parse resolved dependency versions; unresolved ranges are never exact versions."""
import json
import re
import tomllib
from pathlib import PurePosixPath

SUPPORTED = {'package-lock.json', 'npm-shrinkwrap.json', 'requirements.txt', 'poetry.lock', 'Cargo.lock', 'go.mod'}
MANIFESTS = SUPPORTED | {'package.json', 'pyproject.toml', 'Cargo.toml', 'yarn.lock', 'pnpm-lock.yaml','uv.lock','Pipfile','Pipfile.lock','bun.lock','Gemfile','Gemfile.lock','composer.json','composer.lock','pom.xml','build.gradle','build.gradle.kts','gradle.lockfile','packages.lock.json','packages.config','Package.swift','Package.resolved','pubspec.yaml','pubspec.lock'}


def extract_packages(file: dict) -> list[dict]:
    name = PurePosixPath(file['path']).name
    content = file.get('content', '')
    packages = []
    def add(package, version, ecosystem):
        if re.fullmatch(r'\d[^\s^~<>=*,]*', str(version)):
            packages.append({'name':package,'version':str(version),'ecosystem':ecosystem,'source_file':file['path']})
    if name in {'package-lock.json', 'npm-shrinkwrap.json'}:
        data = json.loads(content)
        if 'packages' in data:
            for location, entry in data['packages'].items():
                if location and '/node_modules/' in '/'+location and not entry.get('link'):
                    add(entry.get('name') or location.rsplit('node_modules/',1)[-1],entry.get('version',''),'npm')
        else:
            def walk(entries):
                for package, entry in entries.items():
                    add(package,entry.get('version',''),'npm')
                    walk(entry.get('dependencies',{}))
            walk(data.get('dependencies',{}))
    elif name == 'package.json':
        data = json.loads(content)
        for package, version in (data.get('dependencies',{}) | data.get('devDependencies',{})).items(): add(package,version,'npm')
    elif name == 'requirements.txt':
        for line in content.splitlines():
            match = re.match(r'^([A-Za-z0-9_.-]+)(?:\[[^]]+\])?==([^;\s]+)',line.strip())
            if match: add(match[1],match[2],'PyPI')
    elif name in {'poetry.lock', 'Cargo.lock'}:
        for entry in tomllib.loads(content).get('package',[]): add(entry['name'],entry['version'],'PyPI' if name=='poetry.lock' else 'crates.io')
    elif name == 'go.mod':
        for line in content.splitlines():
            match = re.match(r'^(?:require\s+)?([^\s()]+)\s+v(\d[^\s]+)',line.strip())
            if match: add(match[1],match[2],'Go')
    return list({(p['ecosystem'],p['name'],p['version']):p for p in packages}.values())
