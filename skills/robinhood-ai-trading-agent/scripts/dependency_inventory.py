"""Capture actual installed dependency closure, SBOM and optional artifact-hash lock.

Does not download, install, execute wheels, infer license permissions, or claim
cross-platform compatibility. Packaging is needed to interpret PEP508 metadata.
"""
from __future__ import annotations
import argparse
import hashlib
import importlib.metadata as metadata
import json
from pathlib import Path
import platform
import sys
from experiment_registry import require, utcnow

def capture(requirements_path,output_dir,artifact_dir=None):
    from packaging.requirements import Requirement
    from packaging.markers import default_environment
    from packaging.utils import canonicalize_name, parse_wheel_filename, parse_sdist_filename
    source=Path(requirements_path).resolve();output=Path(output_dir).resolve()
    output.mkdir(parents=True,exist_ok=False)
    roots=[Requirement(line.strip()) for line in source.read_text(encoding='utf-8-sig').splitlines() if line.strip() and not line.lstrip().startswith('#')]
    require(roots,'REQUIREMENTS_REQUIRED')
    queue=list(roots);packages={};requested_extras={};errors=[];environment=default_environment()
    while queue:
        request=queue.pop(0)
        if request.marker and not request.marker.evaluate({**environment,'extra':''}):continue
        name=canonicalize_name(request.name)
        try:dist=metadata.distribution(name)
        except metadata.PackageNotFoundError:errors.append({'package':name,'reason':'NOT_INSTALLED'});continue
        if request.specifier and not request.specifier.contains(dist.version,prereleases=True):errors.append({'package':name,'reason':'INSTALLED_VERSION_CONFLICT','version':dist.version,'requirement':str(request)})
        old=requested_extras.get(name,set());extras=old|set(request.extras)
        if name in packages and extras==old:continue
        requested_extras[name]=extras
        children=[]
        for declaration in dist.requires or []:
            child=Requirement(declaration)
            if child.marker and not any(child.marker.evaluate({**environment,'extra':extra}) for extra in ['']+sorted(extras)):continue
            children.append(canonicalize_name(child.name));child.marker=None;queue.append(child)
        packages[name]={'name':name,'version':dist.version,'requested_extras':sorted(extras),'dependencies':sorted(set(children)),'license_expression_from_metadata':dist.metadata.get('License-Expression'),'license_metadata':dist.metadata.get('License'),'artifacts':[]}
    if artifact_dir is not None:
        root=Path(artifact_dir).resolve();require(root.is_dir(),'ARTIFACT_DIRECTORY_REQUIRED')
        for f in sorted(root.iterdir()):
            if not f.is_file():continue
            try:
                if f.name.endswith('.whl'):name,version,_,_=parse_wheel_filename(f.name);kind='wheel'
                else:name,version=parse_sdist_filename(f.name);kind='sdist'
            except Exception:continue
            name=canonicalize_name(name)
            if name in packages and str(version)==packages[name]['version']:
                packages[name]['artifacts'].append({'filename':f.name,'sha256':hashlib.sha256(f.read_bytes()).hexdigest(),'bytes':f.stat().st_size,'kind':kind})
    rows=[packages[k] for k in sorted(packages)]
    missing=[r['name'] for r in rows if not r['artifacts']]
    report={'schema_version':1,'captured_at':utcnow(),'requirements_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'roots':[str(r) for r in roots],'python':sys.version,'platform':platform.platform(),'marker_environment':environment,'packages':rows,'resolution_errors':errors,'artifact_hash_coverage_complete':not missing and not errors,'packages_missing_artifact_hashes':missing,'license_review_completed':False,'cross_platform_verified':False,'limits':['Installed metadata closure for this exact interpreter/platform; optional extras only when requested.','Installed versions are not wheel hashes. A hash lock is emitted only when every resolved distribution has retained artifact bytes and no version conflict.','SDist hashes authenticate source archives, not deterministic compiled builds; build dependencies require a separate locked build environment.','License metadata is inventory evidence, not a permission assessment.']}
    (output/'dependency-inventory.json').write_text(json.dumps(report,indent=2,allow_nan=False),encoding='utf-8')
    pins=''.join(f'{r["name"]}=={r["version"]}\n' for r in rows)
    (output/'requirements.environment.txt').write_text('# Observed platform-specific environment; not an artifact-hash lock.\n'+pins,encoding='utf-8')
    if report['artifact_hash_coverage_complete']:
        lines=['# Exact retained artifacts; platform-specific. Use pip --require-hashes.']
        for r in rows:lines.append(f'{r["name"]}=={r["version"]} '+' '.join('--hash=sha256:'+a['sha256'] for a in r['artifacts']))
        (output/'requirements.lock.txt').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    components=[]
    for r in rows:
        c={'type':'library','bom-ref':r['name']+'@'+r['version'],'name':r['name'],'version':r['version'],'purl':'pkg:pypi/'+r['name']+'@'+r['version'],'properties':[{'name':'license-review','value':'not-performed'}]}
        if r['license_expression_from_metadata']:c['licenses']=[{'expression':r['license_expression_from_metadata']}]
        # Component hashes are retained distribution artifact hashes, not installed tree hashes.
        if r['artifacts']:c['hashes']=[{'alg':'SHA-256','content':a['sha256']} for a in r['artifacts']]
        components.append(c)
    sbom={'bomFormat':'CycloneDX','specVersion':'1.6','version':1,'metadata':{'timestamp':report['captured_at'],'properties':[{'name':'scope','value':'Observed Python environment; platform-specific, not a legal or security certification'}]},'components':components,'dependencies':[{'ref':r['name']+'@'+r['version'],'dependsOn':[d+'@'+packages[d]['version'] for d in r['dependencies'] if d in packages]} for r in rows]}
    (output/'sbom.cdx.json').write_text(json.dumps(sbom,indent=2,allow_nan=False),encoding='utf-8')
    return report

def verify_artifacts(inventory,artifact_dir):
    root=Path(artifact_dir).resolve();require(root.is_dir(),'ARTIFACT_DIRECTORY_REQUIRED')
    checked=[]
    for row in inventory['packages']:
        require(row['artifacts'],'MISSING_DISTRIBUTION_ARTIFACT:'+row['name'])
        for artifact in row['artifacts']:
            require(Path(artifact['filename']).name==artifact['filename'],'ARTIFACT_BASENAME_REQUIRED')
            file=root/artifact['filename'];require(file.is_file(),'ARTIFACT_MISSING')
            require(file.stat().st_size==artifact['bytes'] and hashlib.sha256(file.read_bytes()).hexdigest()==artifact['sha256'],'ARTIFACT_HASH_MISMATCH')
            checked.append(artifact['filename'])
    require(not inventory['resolution_errors'],'ENVIRONMENT_RESOLUTION_ERRORS')
    return {'status':'RETAINED_DISTRIBUTION_BYTES_VERIFIED','artifacts':checked,'install_test_performed':False,'license_review_performed':False}

def main():
    p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='command',required=True)
    c=sub.add_parser('capture');c.add_argument('requirements',type=Path);c.add_argument('output',type=Path);c.add_argument('--artifacts',type=Path)
    v=sub.add_parser('verify');v.add_argument('inventory',type=Path);v.add_argument('artifacts',type=Path)
    a=p.parse_args()
    if a.command=='capture':r=capture(a.requirements,a.output,a.artifacts);print(json.dumps({'package_count':len(r['packages']),'artifact_hash_coverage_complete':r['artifact_hash_coverage_complete'],'resolution_errors':r['resolution_errors']},indent=2))
    else:print(json.dumps(verify_artifacts(json.loads(a.inventory.read_text(encoding='utf-8')),a.artifacts),indent=2))

if __name__=='__main__':main()
