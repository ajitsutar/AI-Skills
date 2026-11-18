"""Small, offline Inline XBRL extractor; unsupported constructs stay explicit.

This is a conservative supported subset, not a complete XBRL validator. It also
requires well-formed XHTML and retains in-scope XML namespace bindings.
No external entity expansion, network, scripts or source-provided code execution.
"""
from __future__ import annotations

import argparse
import json
import re
from decimal import Decimal, localcontext
from io import StringIO
from pathlib import Path
import xml.etree.ElementTree as ET


INSTANCE = 'http://www.xbrl.org/2003/instance'
ISO4217 = 'http://www.xbrl.org/2003/iso4217'
XSI = 'http://www.w3.org/2001/XMLSchema-instance'
INLINE = {'http://www.xbrl.org/2013/inlineXBRL', 'http://www.xbrl.org/2008/inlineXBRL'}
TRANSFORMS = {'http://www.xbrl.org/inlineXBRL/transformation/' + date for date in
              ('2010-04-20', '2011-07-31', '2015-02-26', '2020-02-12', '2022-02-16')}


def expanded(name):
    if name.startswith('{') and '}' in name:
        return tuple(name[1:].split('}', 1))
    return '', name


def qname(value, namespaces):
    parts = value.strip().split(':')
    if len(parts) == 1:
        prefix, local = '', parts[0]
    elif len(parts) == 2:
        prefix, local = parts
    else:
        raise ValueError('INVALID_QNAME:' + value)
    uri = namespaces.get(prefix)
    if not uri or not local:
        raise ValueError('UNRESOLVED_QNAME:' + value)
    return uri, local


def extract_html(text):
    if '<!ENTITY' in text.upper() or '<!DOCTYPE' in text.upper():
        raise ValueError('XML_ENTITY_OR_DTD_UNSUPPORTED')
    scopes, stack, pending = {}, [], {}
    try:
        parser = ET.iterparse(StringIO(text), events=('start', 'end', 'start-ns'))
        for event, item in parser:
            if event == 'start-ns':
                pending[item[0]] = item[1]
            elif event == 'start':
                scope = dict(stack[-1]) if stack else {}
                scope.update(pending); pending.clear()
                scopes[item] = scope; stack.append(scope)
            else:
                stack.pop()
    except ET.ParseError as exc:
        raise ValueError('WELL_FORMED_XHTML_REQUIRED:' + str(exc)) from exc
    contexts, units, facts = {}, {}, []
    def node(item):
        return dict(element=item.tag, attributes=dict(item.attrib),
                    text=''.join(item.itertext()).strip(), namespaces=scopes[item])
    for item in parser.root.iter():
        uri, local = expanded(item.tag)
        if local in {'context', 'unit'}:
            dest = contexts if local == 'context' else units
            key = item.get('id', '')
            value = [node(child) for child in item.iter()]
            if not key or (key in dest and dest[key] != value):
                raise ValueError('MISSING_OR_DUPLICATE_CONTEXT_OR_UNIT:' + key)
            dest[key] = value
        elif local in {'nonFraction', 'fraction'}:
            facts.append(dict(element=item.tag, attributes=dict(item.attrib), namespaces=scopes[item],
                              display_text=''.join(item.itertext()),
                              unsupported_inline_construct=any(expanded(child.tag)[1] in
                                  {'exclude', 'continuation', 'fraction', 'nonFraction'} for child in list(item.iter())[1:])))
    return dict(extract_schema_version=2, contexts=contexts, units=units, numeric_inline_facts=facts)


def numeric(attrs, display):
    """Apply supported transformation, then scale and sign; decimals is accuracy."""
    if attrs.get('xsi:nil', '').lower() in {'true', '1'}:
        raise ValueError('NIL_FACT')
    if attrs.get('continuedat'):
        raise ValueError('CONTINUED_FACT_UNSUPPORTED')
    fmt = attrs.get('format', '').split(':')[-1].lower()
    text = re.sub(r'\s+', '', display)
    if fmt in {'num-dash', 'zerodash', 'zero-dash'}:
        if text not in {'-', '—', '–'}:
            raise ValueError('INVALID_DASH_TRANSFORM')
        text = '0'
    elif fmt in {'num-dot-decimal', 'numdotdecimal', ''}:
        if not re.fullmatch(r'(?:\d+|\d{1,3}(?:,\d{3})+)(?:\.\d+)?', text):
            raise ValueError('INVALID_DOT_DECIMAL')
        text = text.replace(',', '')
    elif fmt in {'num-comma-decimal', 'numcommadecimal'}:
        if not re.fullmatch(r'(?:\d+|\d{1,3}(?:\.\d{3})+)(?:,\d+)?', text):
            raise ValueError('INVALID_COMMA_DECIMAL')
        text = text.replace('.', '').replace(',', '.')
    else:
        raise ValueError('UNSUPPORTED_TRANSFORM:' + fmt)
    scale = int(attrs.get('scale', '0'))
    decimals = attrs.get('decimals')
    if abs(scale) > 30 or (decimals != 'INF' and (decimals is None or abs(int(decimals)) > 30)):
        raise ValueError('SCALE_OR_ACCURACY_UNSUPPORTED')
    if attrs.get('sign', '') not in {'', '-'}:
        raise ValueError('INVALID_SIGN')
    with localcontext() as ctx:
        ctx.prec = 50
        value = Decimal(text) * Decimal(10) ** scale
        if attrs.get('sign') == '-':
            value = -value
        return str(value), decimals


def observations(extract, source_id):
    records, issues = [], []
    for i, fact in enumerate(extract.get('numeric_inline_facts', [])):
        attrs = {k.lower(): v for k, v in fact.get('attributes', {}).items()}
        fid = attrs.get('id') or 'ordinal-' + str(i)
        try:
            if extract.get('extract_schema_version') != 2:
                raise ValueError('REEXTRACT_WITH_NAMESPACE_BINDINGS_REQUIRED')
            uri, local = expanded(fact.get('element', ''))
            if uri not in INLINE or local != 'nonFraction' or fact.get('unsupported_inline_construct'):
                raise ValueError('INLINE_CONSTRUCT_UNSUPPORTED')
            namespaces = fact['namespaces']
            concept_uri, concept_local = qname(attrs['name'], namespaces)
            if not re.fullmatch(r'http://fasb.org/us-gaap/20\d{2}', concept_uri):
                raise ValueError('UNSUPPORTED_CONCEPT_NAMESPACE:' + concept_uri)
            if attrs.get('format'):
                fmt_uri, fmt_local = qname(attrs['format'], namespaces)
                if fmt_uri not in TRANSFORMS:
                    raise ValueError('UNSUPPORTED_TRANSFORM_NAMESPACE:' + fmt_uri)
                attrs['format'] = fmt_local
            attrs['xsi:nil'] = fact['attributes'].get('{' + XSI + '}nil', '')
            context = extract['contexts'][attrs['contextref']]
            if context[0]['element'] != '{' + INSTANCE + '}context':
                raise ValueError('CONTEXT_NAMESPACE')
            if any(expanded(x['element'])[1] in ('segment', 'scenario', 'explicitMember', 'typedMember') for x in context):
                raise ValueError('DIMENSIONED_FACT_NOT_AUTOMAPPED')
            def one(tag):
                values = [x['text'] for x in context if x['element'] == '{' + INSTANCE + '}' + tag]
                if len(values) != 1:
                    raise ValueError('CONTEXT_' + tag.upper())
                return values[0]
            entity = one('identifier')
            units = extract['units'][attrs['unitref']]
            measures = [qname(x['text'], x['namespaces']) for x in units if x['element'] == '{' + INSTANCE + '}measure']
            if units[0]['element'] != '{' + INSTANCE + '}unit' or measures != [(ISO4217, 'USD')] or any(expanded(x['element'])[1] == 'divide' for x in units):
                raise ValueError('NON_USD_MONETARY_UNIT')
            value, decimals = numeric(attrs, fact.get('display_text', ''))
            instant = any(x['element'] == '{' + INSTANCE + '}instant' for x in context)
            if instant and any(expanded(x['element'])[1] in {'startDate', 'endDate'} for x in context):
                raise ValueError('AMBIGUOUS_PERIOD')
            record = dict(record_id=source_id + ':' + fid, source_id=source_id,
                          entity_id=entity, concept='us-gaap:' + concept_local, value=value,
                          concept_namespace=concept_uri,
                          unit='USD', decimals=decimals,
                          period_end=one('instant') if instant else one('endDate'),
                          locator=dict(fact_id=fid, context_id=attrs['contextref'], unit_id=attrs['unitref']),
                          display_text=fact.get('display_text', ''), scale=attrs.get('scale', '0'),
                          sign=attrs.get('sign', ''), acquisition='inline_xbrl')
            if not instant:
                record['period_start'] = one('startDate')
            records.append(record)
        except (ValueError, KeyError, TypeError, IndexError) as exc:
            issues.append(dict(record_id=source_id + ':' + fid, concept=attrs.get('name'), reason=str(exc)))
    return records, issues


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    data = extract_html(args.input.read_text(encoding='utf-8-sig'))
    root = Path(__file__).resolve().parents[1]
    if args.output.resolve().is_relative_to(root):
        raise ValueError('Save extracted data outside the installed skill')
    with args.output.open('x', encoding='utf-8') as stream:
        json.dump(data, stream, indent=2)
        stream.write('\n')


if __name__ == '__main__':
    main()
