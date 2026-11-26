"""Public, one-shot news discovery. No orders, background service or credentials.

Configured endpoints only; article links are evidence, never fetched automatically.
Local response archives are for replay, not redistribution of publisher content.
"""
import argparse
from datetime import date, datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
import hashlib
from html import unescape
from html.parser import HTMLParser
import ipaddress
import json
import os
from pathlib import Path
import re
import socket
import sys
import time
from urllib.parse import urlparse, urljoin
import uuid
import xml.etree.ElementTree as ET
from zoneinfo import ZoneInfo

UTC = timezone.utc
MAX_BYTES = 5_000_000
SOURCE_KINDS = {'issuer', 'sec', 'exchange', 'macro', 'wire', 'publisher', 'aggregator'}


def stamp(value):
    if isinstance(value, datetime):
        dt = value
    else:
        value = str(value or '').strip()
        if not value or len(value) == 10:
            raise ValueError('Full timezone-aware timestamp required')
        try:
            dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
        except ValueError:
            try:
                dt = datetime.strptime(value, '%Y%m%dT%H%M%SZ').replace(tzinfo=UTC)
            except ValueError:
                dt = parsedate_to_datetime(value)
    if dt.tzinfo is None:
        raise ValueError('Timestamp has no timezone')
    return dt.astimezone(UTC)


def iso(value):
    return stamp(value).isoformat().replace('+00:00', 'Z')


def date_only_issue(value, observed):
    """Check a civil publication day without assigning a publisher timezone or hour."""
    if value is None:
        return None
    try:
        day = date.fromisoformat(value)
        if day.isoformat() != value:
            return 'INVALID_PUBLICATION_DATE'
    except (TypeError, ValueError):
        return 'INVALID_PUBLICATION_DATE'
    # UTC+14 is the furthest-ahead civil time zone. A later day is impossible
    # at capture even if the publisher's local timezone was never supplied.
    if day > stamp(observed).astimezone(timezone(timedelta(hours=14))).date():
        return 'PUBLICATION_DATE_AFTER_OBSERVATION'
    return None


def digest(value):
    return hashlib.sha256(value if isinstance(value, bytes) else value.encode()).hexdigest()


class _Text(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []

    def handle_data(self, data):
        self.parts.append(data)


def plain(value):
    p = _Text()
    p.feed(value or '')
    return re.sub(r'\s+', ' ', unescape(' '.join(p.parts))).strip()


def local(tag):
    return tag.rsplit('}', 1)[-1]


def eastern_event(day, clock):
    try:
        day = datetime.strptime(day.strip(), '%m/%d/%Y').date()
        wall = datetime.fromisoformat(f'{day}T{clock.strip()}')
        zone = ZoneInfo('America/New_York')
        a, b = wall.replace(tzinfo=zone, fold=0), wall.replace(tzinfo=zone, fold=1)
        if a.utcoffset() != b.utcoffset():
            return None  # Ambiguous/nonexistent DST local times require review.
        return iso(a)
    except (ValueError, AttributeError):
        return None


def parse_feed(raw, source):
    try:
        decoded = raw.decode('utf-8-sig')
    except UnicodeError as exc:
        raise ValueError('Only UTF-8 feeds supported') from exc
    if '\x00' in decoded or '<!DOCTYPE' in decoded.upper() or '<!ENTITY' in decoded.upper():
        raise ValueError('DTD/entities forbidden')
    root = ET.fromstring(decoded)
    if local(root.tag) not in ('rss', 'feed', 'RDF'):
        raise ValueError('Not an RSS/Atom feed')
    rows = []
    for item in root.iter():
        if local(item.tag) not in ('item', 'entry'):
            continue
        fields = {}
        for child in item:
            key = local(child.tag)
            if key == 'link' and child.attrib.get('rel', 'alternate') == 'alternate':
                fields['url'] = child.attrib.get('href') or child.text or ''
            elif key not in fields:
                fields[key] = ''.join(child.itertext())
        # Some RSS feeds use pubDate; Atom distinguishes original and updated time.
        record = {'title': plain(fields.get('title', '')),
                     'summary': plain(fields.get('description', fields.get('summary', fields.get('content', ''))))[:12000],
                     'url': urljoin(source['url'], fields.get('url', fields.get('link', ''))) if fields.get('url', fields.get('link')) else '',
                     'published_at': fields.get('published', fields.get('pubDate', fields.get('date'))),
                     'updated_at': fields.get('updated'), 'source_item_id': fields.get('id', fields.get('guid')),
                     'evidence_kind': 'FEED_EXCERPT'}
        if source['source_kind'] == 'exchange' and fields.get('HaltDate'):
            keys = ('HaltDate', 'HaltTime', 'IssueSymbol', 'IssueName', 'Market', 'ReasonCode',
                    'PauseThresholdPrice', 'ResumptionDate', 'ResumptionQuoteTime', 'ResumptionTradeTime')
            record.update(exchange_fields={k: fields.get(k, '').strip() for k in keys},
                          source_item_id='|'.join(fields.get(k, '') for k in ('IssueSymbol', 'HaltDate', 'HaltTime')),
                          event_at=eastern_event(fields['HaltDate'], fields.get('HaltTime', '')),
                          feed_dateline=record['published_at'], published_at=None,
                          url=record['url'] or source['url'], evidence_kind='EXCHANGE_STATUS_EVENT')
        rows.append(record)
    return rows


def parse_sec(raw, source):
    data = json.loads(raw)
    recent = data['filings']['recent']
    cik = int(source['cik'])
    if int(data['cik']) != cik:
        raise ValueError('SEC CIK mismatch')
    rows = []
    for i, form in enumerate(recent['form']):
        if form not in ('8-K', '8-K/A', '6-K', '6-K/A', '10-Q', '10-Q/A', '10-K', '10-K/A', '20-F', '20-F/A'):
            continue
        acc = recent['accessionNumber'][i].replace('-', '')
        doc = recent['primaryDocument'][i]
        items = recent.get('items', [''] * len(recent['form']))[i]
        rows.append({'title': f"{data['name']} {form} items {items}".strip(),
                     'summary': 'Filing metadata only; review filing and linked exhibits, including 99.x.',
                     'url': f'https://www.sec.gov/Archives/edgar/data/{cik}/{acc}/{doc}',
                     'published_at': recent['acceptanceDateTime'][i], 'updated_at': None,
                     'form': form, 'items': items, 'evidence_kind': 'FILING_METADATA_ONLY'})
    return rows


def parse_gdelt(raw, source):
    data = json.loads(raw)
    if not isinstance(data.get('articles'), list):
        raise ValueError('GDELT articles missing; not a valid empty response')
    return [{'title': plain(r.get('title', '')), 'summary': '', 'url': r.get('url', ''),
             'published_at': None, 'updated_at': None, 'provider_seen_at': r.get('seendate'),
             'evidence_kind': 'AGGREGATOR_HEADLINE_ONLY'} for r in data['articles']]


PARSERS = {'rss': parse_feed, 'sec_submissions': parse_sec, 'gdelt': parse_gdelt}


def normalize(row, source, observed, seen):
    now = stamp(observed)
    flags = []
    date_issue = date_only_issue(row.get('published_date'), now)
    if date_issue:
        flags.append(date_issue)
    times = {}
    for key in ('published_at', 'updated_at', 'provider_seen_at', 'event_at'):
        try:
            dt = stamp(row.get(key))
            if dt > now:
                flags.append(key.upper() + '_IN_FUTURE')
            times[key] = iso(dt)
        except (ValueError, TypeError, OverflowError):
            times[key] = None
    if times['published_at'] is None:
        flags.append('PUBLICATION_TIME_UNKNOWN')
    url = row.get('url', '')
    if urlparse(url).scheme not in ('http', 'https') or not urlparse(url).hostname:
        flags.append('ARTICLE_URL_INVALID')
    content = digest(json.dumps([row.get('title', ''), row.get('summary', ''), times,
                                 row.get('source_item_id'), row.get('exchange_fields')], sort_keys=True))
    identity = digest(source['id'] + '\n' + url + '\n' + content)
    first = seen.get(identity, iso(now))
    # A later revision becomes available when observed, not at the original dateline.
    available = max([stamp(first)] + [stamp(v) for v in times.values() if v])
    return {**row, **times, 'event_id': identity, 'content_sha256': content,
            'source_id': source['id'], 'source_kind': source['source_kind'],
            'scope_issuers': source.get('scope_issuers', []), 'retrieved_at': iso(now),
            'first_seen_at': first, 'available_at': iso(available),
            'new_revision': identity not in seen, 'flags': sorted(flags)}


def interval(source):
    host = (urlparse(source['url']).hostname or '').lower()
    floor = 60 if host.endswith('nasdaqtrader.com') else 300
    if source['adapter'] == 'sec_submissions':
        floor = 60
    if source['adapter'] == 'gdelt':
        floor = 900
    requested = source.get('poll_seconds', floor)
    if isinstance(requested, bool) or not isinstance(requested, int) or requested <= 0:
        raise ValueError('Polling interval must be a positive integer')
    return max(floor, requested)


def validate_url(url):
    u = urlparse(url)
    if u.scheme != 'https' or not u.hostname or u.username or u.password or u.port not in (None, 443):
        raise ValueError('Public HTTPS endpoint required, without credentials')
    if re.search(r'(api.?key|token|secret|password|authorization)=', u.query, re.I):
        raise ValueError('Credential query parameters unsupported by public adapter')
    addresses = socket.getaddrinfo(u.hostname, 443, type=socket.SOCK_STREAM)
    if not addresses:
        raise ValueError('No public endpoint addresses returned')
    for address in addresses:
        if not ipaddress.ip_address(address[4][0]).is_global:
            raise PublicEgressUnavailable('Private/local network endpoints forbidden')


class PublicEgressUnavailable(ValueError):
    """Local resolution cannot establish a public destination for the direct adapter."""


def import_search_observations(document):
    """Convert an explicit host search capture into news-analysis records without network I/O."""
    if document.get('schema_version') != 1 or not isinstance(document.get('searches'), list) or not document['searches']:
        raise ValueError('Search import requires schema_version 1 and nonempty searches')
    report = {'schema': 1, 'records': [], 'sources': [], 'coverage': 'DECLARED_SEARCHES_ONLY',
              'input_sha256': digest(json.dumps(document, sort_keys=True)), 'execution_authorized': False}
    ids = set()
    for search in document['searches']:
        source_id = search['source_id']
        if not re.fullmatch(r'[a-z0-9_-]{1,80}', source_id) or source_id in ids:
            raise ValueError('Unique search source_id required')
        ids.add(source_id)
        provider, query = search['provider'], search['query']
        if not all(isinstance(v, str) and v.strip() for v in (provider, query)):
            raise ValueError('Actual provider and query required')
        checked = iso(search['observed_at'])
        status, results = search['status'], search['results']
        statuses = {'observed': 'SEARCH_RESULTS_IMPORTED', 'empty': 'EMPTY_SEARCH', 'unavailable': 'SEARCH_UNAVAILABLE'}
        if status not in statuses or not isinstance(results, list) or (status == 'observed') != bool(results):
            raise ValueError('Search status and supplied results disagree')
        receipt = {'source_id': source_id, 'search_provider': provider, 'search_query': query,
                   'checked_at': checked, 'status': statuses[status], 'result_count': len(results)}
        if status == 'unavailable':
            if not isinstance(search.get('reason'), str) or not search['reason'].strip():
                raise ValueError('Unavailable search needs a reason')
            receipt['reason'] = search['reason']
        known = {}
        for item in results:
            url = urlparse(item['url'])
            if url.scheme not in ('http', 'https') or not url.hostname or url.username is not None or url.password is not None:
                raise ValueError('Search result needs a public article reference without credentials')
            title, snippet = item['title'], item.get('snippet', '')
            if not isinstance(title, str) or not title.strip() or not isinstance(snippet, str):
                raise ValueError('Search result needs an observed title and optional text snippet')
            publication = item.get('published_at')
            if publication is not None:
                publication = iso(publication)
            updated = item.get('updated_at')
            if updated is not None:
                updated = iso(updated)
            dateline = item.get('published_date')
            if dateline is not None:
                if date.fromisoformat(dateline).isoformat() != dateline:
                    raise ValueError('Search result calendar dateline must use YYYY-MM-DD')
            row = {'title': title, 'summary': snippet, 'url': item['url'], 'published_at': publication,
                   'published_date': dateline,
                   'source_item_id': digest(json.dumps([item['url'], title], ensure_ascii=False)),
                   'updated_at': updated, 'search_provider': provider, 'search_query': query,
                   'evidence_kind': 'SEARCH_SNIPPET' if snippet else 'SEARCH_HEADLINE_ONLY',
                   'source_refresh_status': 'SEARCH_IMPORT'}
            record = normalize(row, {'id': source_id, 'source_kind': 'aggregator'}, checked, known)
            if record['event_id'] not in known:
                known[record['event_id']] = checked
                report['records'].append(record)
        receipt['unique_count'] = len(known)
        report['sources'].append(receipt)
    return report


def fetch(source, prior, user_agent):
    import requests
    validate_url(source['url'])
    headers = {'User-Agent': user_agent, 'Accept': 'application/rss+xml, application/atom+xml, application/json, application/xml, text/xml'}
    for k, h in [('etag', 'If-None-Match'), ('last_modified', 'If-Modified-Since')]:
        if prior.get(k):
            headers[h] = prior[k]
    with requests.Session() as session:
        # No implicit .netrc credentials, authentication profiles or login cookies.
        session.trust_env = False
        with session.get(source['url'], headers=headers, timeout=(10, 25), stream=True, allow_redirects=False) as response:
            chunks, size = [], 0
            for chunk in response.iter_content(65536):
                size += len(chunk)
                if size > MAX_BYTES:
                    raise ValueError('Response exceeds size limit')
                chunks.append(chunk)
            return response.status_code, dict(response.headers), b''.join(chunks)


def delay_seconds(header, now):
    try:
        return max(0, int(header))
    except (ValueError, TypeError):
        try:
            return max(0, (stamp(header) - stamp(now)).total_seconds())
        except (ValueError, TypeError):
            return 0


def save_json(path, data):
    path = Path(path)
    temp = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    try:
        temp.write_text(json.dumps(data, indent=2, sort_keys=True) + '\n', encoding='utf-8')
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def poll(config, state_path, run_dir, transport=fetch, clock=None, sleeper=time.sleep):
    """One sequential pass; caller must explicitly request/schedule further passes."""
    clock = clock or (lambda: datetime.now(UTC))
    sources = config['sources']
    ids = [s['id'] for s in sources]
    if len(set(ids)) != len(ids) or any(not re.fullmatch(r'[a-z0-9_-]{1,80}', i) for i in ids):
        raise ValueError('Unique safe source IDs required')
    ua = config.get('user_agent', '')
    if len(ua) < 10 or (any(s['adapter'] == 'sec_submissions' and s.get('enabled', True) for s in sources) and
                         ('@' not in ua or '.invalid' in ua or 'example.com' in ua)):
        raise ValueError('Identify application; SEC requires a real contact User-Agent')
    declared = set()
    for source in sources:
        if source.get('source_kind') not in SOURCE_KINDS:
            raise ValueError('Unknown source_kind; use the documented catalog categories')
        if source['adapter'] not in PARSERS:
            raise ValueError('Unsupported adapter: ' + source['adapter'])
        if 'fallback_for' in source and source['fallback_for'] not in declared:
            raise ValueError('A fallback must follow its configured primary source')
        interval(source)
        declared.add(source['id'])
    state_path = Path(state_path)
    state_path.parent.mkdir(parents=True, exist_ok=True)
    lock = state_path.with_name(state_path.name + '.lock')
    # Never delete another process's lock; a crash requires operator inspection.
    with lock.open('x', encoding='utf-8') as handle:
        handle.write(str(os.getpid()))
    try:
        state = json.loads(state_path.read_text(encoding='utf-8')) if state_path.exists() else {'sources': {}, 'seen': {}}
        run = Path(run_dir)
        run.mkdir(parents=True, exist_ok=False)
        report = {'schema': 1, 'started_at': iso(clock()), 'config_sha256': digest(json.dumps(config, sort_keys=True)),
                  'implementation_sha256': digest(Path(__file__).read_bytes()),
                  'sources': [], 'records': [], 'coverage': 'CONFIGURED_SOURCES_ONLY', 'execution_authorized': False}
        for source in sources:
            now = stamp(clock())
            previous = state['sources'].get(source['id'], {})
            config_hash = digest(json.dumps(source, sort_keys=True))
            # Changed endpoint/scope invalidates cached validators and success claims.
            if previous.get('config_sha256') != config_hash:
                previous = {}
            receipt = {'source_id': source['id'], 'url': source['url'], 'checked_at': iso(now),
                       'source_kind': source['source_kind'], 'poll_seconds': interval(source),
                       'last_success_at': previous.get('last_success_at')}
            if 'fallback_for' in source:
                receipt['fallback_for'] = source['fallback_for']
            if not source.get('enabled', True):
                receipt['status'] = 'DISABLED'
                report['sources'].append(receipt)
                continue
            if 'fallback_for' in source:
                primary = next(s for s in report['sources'] if s['source_id'] == source['fallback_for'])
                state_at_primary = primary.get('previous_status') if primary['status'] == 'NOT_DUE' else primary['status']
                if state_at_primary not in ('RATE_LIMITED', 'ACCESS_DENIED', 'FAILED', 'HTTP_ERROR', 'REDIRECT_REQUIRES_CONFIG'):
                    receipt['status'] = 'FALLBACK_NOT_NEEDED'
                    report['sources'].append(receipt)
                    continue
            if previous.get('next_poll_at') and now < stamp(previous['next_poll_at']):
                receipt.update(status='NOT_DUE', previous_status=previous.get('status'), next_poll_at=previous['next_poll_at'])
                report['records'].extend(dict(r, new_revision=False, source_refresh_status='NOT_DUE') for r in previous.get('cached_records', []))
                report['sources'].append(receipt)
                continue
            current = dict(previous, config_sha256=config_hash)
            wait = interval(source)
            try:
                code, headers, raw = transport(source, previous, ua)
                now = stamp(clock())
                receipt.update(checked_at=iso(now), http_status=code, response_sha256=digest(raw), bytes=len(raw))
                (run / (source['id'] + '.response')).write_bytes(raw)
                headers = {k.lower(): v for k, v in headers.items()}
                if code == 304:
                    if not previous.get('last_success_at') or 'cached_records' not in previous:
                        raise ValueError('304 without successful cached parse')
                    cached = [dict(r, retrieved_at=iso(now), new_revision=False) for r in previous['cached_records']]
                    report['records'].extend(cached)
                    receipt.update(status='UNCHANGED', record_count=len(cached), new_revision_count=0,
                                   cached_response_sha256=previous.get('last_response_sha256'))
                elif code == 200:
                    rows = PARSERS[source['adapter']](raw, source)
                    records = [normalize(r, source, now, state['seen']) for r in rows]
                    for r in records:
                        state['seen'].setdefault(r['event_id'], r['first_seen_at'])
                    report['records'].extend(records)
                    current.update(cached_records=records, last_response_sha256=digest(raw))
                    receipt.update(status='PARSED' if records else 'EMPTY_VALID', record_count=len(records),
                                   new_revision_count=sum(r['new_revision'] for r in records))
                else:
                    receipt['status'] = ('ACCESS_DENIED' if code in (401, 403) else 'RATE_LIMITED' if code == 429
                                         else 'REDIRECT_REQUIRES_CONFIG' if 300 <= code < 400 else 'HTTP_ERROR')
                if receipt['status'] in ('PARSED', 'EMPTY_VALID', 'UNCHANGED'):
                    current.update(failures=0, last_success_at=iso(now))
                    receipt['last_success_at'] = iso(now)
                    for key, field in [('etag', 'etag'), ('last-modified', 'last_modified')]:
                        if key in headers:
                            current[field] = headers[key]
                        elif code == 200:
                            current.pop(field, None)
                else:
                    current['failures'] = int(current.get('failures', 0)) + 1
                    wait = max(wait, delay_seconds(headers.get('retry-after'), now), min(86400, wait * 2 ** min(current['failures'], 8)))
            except Exception as exc:
                receipt.update(status='FAILED', error_type=type(exc).__name__)
                if isinstance(exc, PublicEgressUnavailable):
                    receipt['next_route'] = 'HOST_APPROVED_EGRESS_OR_OFFLINE_SEARCH_IMPORT'
                # Avoid exception URLs/headers possibly exposing endpoint secrets.
                current['failures'] = int(current.get('failures', 0)) + 1
                wait = max(wait, min(86400, wait * 2 ** min(current['failures'], 8)))
            current.update(status=receipt['status'], next_poll_at=iso(now + timedelta(seconds=wait)))
            if receipt['status'] not in ('PARSED', 'EMPTY_VALID', 'UNCHANGED'):
                report['records'].extend(dict(r, new_revision=False, source_refresh_status=receipt['status']) for r in previous.get('cached_records', []))
            receipt['next_poll_at'] = current['next_poll_at']
            state['sources'][source['id']] = current
            report['sources'].append(receipt)
            # Conservative per-process spacing; other SEC jobs must share an external budget.
            sleeper(1)
        report['completed_at'] = iso(clock())
        save_json(run / 'news.json', report)
        save_json(state_path, state)
        return report
    finally:
        lock.unlink(missing_ok=True)


def main():
    if sys.argv[1:2] == ['import-search']:
        p = argparse.ArgumentParser(description=import_search_observations.__doc__)
        p.add_argument('capture')
        p.add_argument('output')
        args = p.parse_args(sys.argv[2:])
        raw = Path(args.capture).read_bytes()
        report = import_search_observations(json.loads(raw))
        report['input_file_sha256'] = digest(raw)
        with Path(args.output).open('x', encoding='utf-8') as handle:
            json.dump(report, handle, indent=2)
            handle.write('\n')
        return
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('config')
    p.add_argument('state')
    p.add_argument('run_dir', help='New output directory; never overwrite a prior run')
    a = p.parse_args()
    result = poll(json.loads(Path(a.config).read_text(encoding='utf-8')), a.state, a.run_dir)
    print(json.dumps({k: v for k, v in result.items() if k != 'records'}, indent=2))


if __name__ == '__main__':
    main()
