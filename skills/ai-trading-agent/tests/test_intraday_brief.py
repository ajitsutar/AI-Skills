"""Exercise both source replay and the delivered readable/structured pair."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import intraday_brief as brief


class IntradayBriefTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.symbol = 'NORTH'
        self.clock = '2032-11-09T17:00:00Z'
        self.quote = {'symbol':self.symbol, 'quote_time':'2032-11-09T16:59:58Z','bid':9.9,'ask':10.1,'currency':'USD'}
        self.halt = {'symbol':self.symbol,'event_kind':'exchange_halt','halt_time':'2032-11-09T16:40:00Z',
                     'published_at':'2032-11-09T16:45:00Z','reason':'news'}
        self.sources = {'prompt':'Prepare the intraday brief for NORTH.',
                        'scope':{'as_of':self.clock,'source_authenticity':'Synthetic research fixture.'},
                        'universe':{'as_of':'2032-11-08T22:00:00Z','rows':[{'symbol':self.symbol,'issuer':'North Tools','exchange':'XNAS','currency':'USD'}]},
                        'session':{'scenario_clock':self.clock,'session_date':'2032-11-09','timezone':'America/New_York',
                                   'regular_open':'2032-11-09T09:30:00-05:00','regular_close':'2032-11-09T16:00:00-05:00'},
                        'quotes':{'scenario_clock':self.clock,'quotes':[self.quote]},
                        'events':{'observations':[self.halt]},
                        'history':'symbol,session_date,unadjusted_close_usd,shares_volume\nNORTH,2032-11-08,12,300\nNORTH,2032-11-04,8,400\nNORTH,2032-11-09,500,3000000\n'}
        self.save()

    def save(self):
        refs={}
        for role, doc in self.sources.items():
            file=self.root/(role+'.source')
            raw=doc.encode() if isinstance(doc,str) else json.dumps(doc).encode()
            file.write_bytes(raw)
            refs[role]={'path':file.name,'sha256':hashlib.sha256(raw).hexdigest()}
        self.request={'symbols':[self.symbol],'sources':refs}
        self.request_path=self.root/'request.json'
        self.request_path.write_text(json.dumps(self.request),encoding='utf8')

    def render(self):
        self.save()
        files=brief.render(self.request,self.root)
        return files['first-response.md'].decode(),json.loads(files['response.json'])

    def cli(self, phase):
        return subprocess.run([sys.executable,'-B',brief.__file__,phase,str(self.request_path),
                               str(self.root),str(self.root/'out')],capture_output=True,text=True,timeout=30)

    def test_unknown_status_retained_across_both_outputs_with_partial_quote_liquidity(self):
        md, doc=self.render()
        row=doc['symbols'][0]
        self.assertIn('Actual trade resumption is unconfirmed',md)
        self.assertIn('bid size unavailable, ask size unavailable, book depth unavailable',md)
        self.assertIn(row['setup_statement'],md)
        self.assertIsNone(row['halt_review']['current_exchange_status'])
        self.assertEqual(row['quote']['age_seconds'],2)
        self.assertEqual(row['quote']['midpoint'],'10.0')
        self.assertEqual(row['history']['mean_dollar_volume_usd'],'3400')
        self.assertEqual(row['history']['mean_shares'],'350')
        self.assertEqual(doc['first_response_sha256'],hashlib.sha256(md.encode()).hexdigest())

    def test_recorded_resumptions_reported_size_and_current_dated_status(self):
        self.halt.update(quote_resume_at='2032-11-09T16:42:00Z',quote_resumed_at='2032-11-09T16:43:00Z',
                         trade_resumed_at='2032-11-09T16:44:00Z')
        self.sources['events']['observations'].append({'symbol':self.symbol,'event_kind':'exchange_status',
                 'status':'open', 'status_as_of':self.clock,'published_at':self.clock})
        self.quote.update(bid_size_shares=75,ask_size_shares=90,book_depth_levels=3)
        md,doc=self.render()
        row=doc['symbols'][0]
        self.assertIn('actual trade resumption at 2032-11-09T16:44:00Z',md)
        self.assertIn('Venue status was reported as open at '+self.clock,md)
        self.assertIn('bid size 75 displayed shares',row['liquidity_statement'])
        self.assertIn('3 displayed book levels',md)
        self.assertIsNone(row['broker_tradability'])
        self.assertEqual(row['reported_venue_status_at_cutoff'],'open')
        self.sources['events']['observations'].append(dict(self.sources['events']['observations'][-1],status='halted'))
        with self.assertRaisesRegex(ValueError,'CONFLICTING_VENUE_STATUS_AT_CUTOFF'):self.render()

    def test_schedule_and_unavailable_quote_stay_distinct_from_activity(self):
        self.halt.update(trade_resume_at='2032-11-09T16:55:00Z')
        self.quote['quote_time']='2032-11-09T17:00:01Z'
        md,doc=self.render()
        self.assertIsNone(doc['symbols'][0]['quote'])
        self.assertIn('scheduled trade resumption',md)
        self.assertIn('Actual trade resumption is unconfirmed',md)
        self.assertIn('No eligible two-sided quote',md)

    def test_cli_rejects_tamper_in_setup_or_structured_status(self):
        built=self.cli('build')
        self.assertEqual(built.returncode,0,built.stderr)
        self.assertEqual(self.cli('verify').returncode,0)
        self.assertNotEqual(self.cli('build').returncode,0)
        first=self.root/'out/first-response.md'; raw=first.read_bytes()
        first.write_bytes(raw+b'\nNORTH remains halted.\n')
        self.assertNotEqual(self.cli('verify').returncode,0)
        first.write_bytes(raw)
        path=self.root/'out/response.json';doc=json.loads(path.read_bytes())
        doc['symbols'][0]['halt_review']['current_exchange_status']='HALTED'
        path.write_text(json.dumps(doc),encoding='utf8')
        self.assertNotEqual(self.cli('verify').returncode,0)

    def test_no_halt_and_non_halt_event_are_source_scoped(self):
        self.sources['events']['observations']=[dict(symbol=self.symbol,event_kind='issuance',
            published_at=self.clock,body='New agreement begins next year.',earnings_release_window=['2032-12-05','2032-12-07'])]
        self.quote['bid_size_shares']=0
        md,doc=self.render()
        self.assertIn('New agreement begins next year.',md)
        self.assertIn('2032-12-05 through 2032-12-07',md)
        self.assertIn('No eligible exchange-halt observation',md)
        self.assertEqual(doc['symbols'][0]['quote']['bid_size_shares'],'0')
        self.assertIsNone(doc['symbols'][0]['quote']['ask_size_shares'])

    def test_source_hash_and_symbol_selection_binding(self):
        self.request['sources']['quotes']['sha256']='0'*64
        with self.assertRaisesRegex(ValueError,'SOURCE_HASH_MISMATCH'):brief.render(self.request,self.root)
        self.save()
        self.request['symbols']=['SOUTH']
        with self.assertRaisesRegex(ValueError,'NAMED_SECURITY'):brief.render(self.request,self.root)

    def test_catalyst_assessment_calendars_and_pending_observations(self):
        event={'symbol':self.symbol,'published_at':self.clock,'event_kind':'issuer_calendar',
               'body':'Calendar reviewed.','earnings_release':'2032-12-09T15:00:00Z'}
        for records in ([],[event],[self.halt]):
            with self.subTest(records=records):
                self.sources['events']['observations']=records
                md,doc=self.render()
                assessment=doc['symbols'][0]['catalyst_assessment']
                self.assertEqual(assessment['state'],'NO_CONFIRMED_FRESH_CATALYST_SUPPLIED')
                self.assertIn('No confirmed fresh catalyst was supplied',assessment['statement'])
                self.assertIn(assessment['statement'],md)
                self.assertEqual(assessment['as_of'],self.clock)
                self.assertEqual(assessment['pending_or_unconfirmed'],['/observations/0'] if records==[self.halt] and self.halt['reason']=='pending_news' else [])
        self.halt['reason']='pending_news'
        self.sources['events']['observations']=[self.halt]
        md,doc=self.render()
        self.assertIn('substance remains unconfirmed',md)
        self.assertEqual(doc['symbols'][0]['catalyst_assessment']['pending_or_unconfirmed'],['/observations/0'])
        self.sources['events']['observations']=[dict(event,earnings_released_at='2032-11-09T15:00:00Z')]
        md,doc=self.render()
        self.assertEqual(doc['symbols'][0]['catalyst_assessment']['state'],'SESSION_DATE_DEVELOPMENT_REPORTED')
        self.assertIn('reported earnings release at 2032-11-09T15:00:00Z',md)

    def test_catalyst_assessment_material_prior_unknown_future_and_unconfirmed(self):
        base={'symbol':self.symbol,'event_kind':'regulatory_decision','published_at':self.clock,
              'body':'The regulator published a decision.'}
        self.sources['events']['observations']=[base,dict(base,published_at='2032-11-08T22:00:00Z'),
            dict(base,event_kind='misc_update'),dict(base,published_at='2032-11-09T18:00:00Z'),
            dict(base,event_status='unconfirmed')]
        md,doc=self.render()
        assessment=doc['symbols'][0]['catalyst_assessment']
        self.assertEqual(assessment['session_date_reported'],['/observations/0'])
        self.assertEqual(assessment['prior_reported'],['/observations/1'])
        self.assertEqual(assessment['unclassified'],['/observations/2'])
        self.assertEqual(assessment['pending_or_unconfirmed'],['/observations/4'])
        self.assertIn(assessment['statement'],md)
        self.assertIn('price impact is unverified',md)
        self.sources['events']['observations']=[dict(base,event_kind='misc_update')]
        md,doc=self.render()
        self.assertEqual(doc['symbols'][0]['catalyst_assessment']['state'],'SUBSTANCE_OR_FRESHNESS_UNRESOLVED')
        self.assertNotIn('No confirmed fresh catalyst was supplied',md)

    def test_extra_market_data_or_unknown_quote_size_units_require_broader_coverage(self):
        self.quote['bid_size']=100
        with self.assertRaisesRegex(ValueError,'UNMAPPED_QUOTE_SIZE'):self.render()
        del self.quote['bid_size']
        self.sources['quotes']['trades']=[{'price':10}]
        with self.assertRaisesRegex(ValueError,'ADDITIONAL_INTRADAY_DATA'):self.render()

    def test_native_envelope_exposes_source_rows_and_applicable_limits(self):
        md,doc=self.render()
        self.assertEqual(doc['rows'],doc['symbols'])
        self.assertEqual([r['symbol'] for r in doc['rows']],[self.symbol])
        limits=' '.join(doc['limitations'])
        for term in ('Synthetic research fixture.',self.symbol,'displayed bid size','displayed ask size',
                     'displayed book depth','venue status as of the cutoff','quote and trade resumption'):
            self.assertIn(term,limits)
        self.assertNotIn('an eligible two-sided quote',limits)
        self.assertNotIn('prior-session volume history',limits)
        self.halt['quote_resumed_at']='2032-11-09T16:43:00Z'
        self.quote.update(bid_size_shares=0,book_depth_levels=2)
        self.sources['events']['observations'].append(dict(symbol=self.symbol,event_kind='exchange_status',
                        status='open',status_as_of=self.clock,published_at=self.clock))
        _,doc=self.render()
        gaps=' '.join(v for v in doc['limitations'] if v.startswith(self.symbol+':'))
        self.assertIn('displayed ask size',gaps)
        self.assertIn('actual trade resumption unconfirmed',gaps)
        for term in ('displayed bid size','displayed book depth','venue status as of the cutoff','quote resumption'):
            self.assertNotIn(term,gaps)
        self.sources['quotes']['quotes']=[]
        self.sources['history']=self.sources['history'].splitlines()[0]
        _,doc=self.render()
        self.assertIn('an eligible two-sided quote, prior-session volume history',' '.join(doc['limitations']))

    def test_packaged_protocol_requires_host_fields_and_replays_destination_bytes(self):
        # Package intake recognizes the inventory-bound original prompt and protocol.
        prompt=self.root/'PROMPT.txt'
        prompt.write_bytes((self.root/'prompt.source').read_bytes())
        self.request['sources']['prompt']['path']=prompt.name
        protocol=self.root/'PROTOCOL.txt'
        required=['case_id','candidate_version','input_hashes','rows','limitations','runtime_model_metadata','evidence_paths']
        protocol.write_text('Save response.json containing '+', '.join(required)+'.', encoding='utf8')
        inventory={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (prompt,protocol)}
        (self.root/'HASHES.json').write_text(json.dumps(inventory),encoding='utf8')
        with self.assertRaisesRegex(ValueError,'MISSING_REQUIRED_RESPONSE_FIELDS'):
            brief.render(self.request,self.root)
        self.request['metadata']=dict(case_id='offline-brief',runtime_model_metadata={'model':'unknown'},
                                      evidence_paths=['retained/commands'])
        self.request_path.write_text(json.dumps(self.request),encoding='utf8')
        self.assertEqual(self.cli('build').returncode,0)
        self.assertEqual(self.cli('verify').returncode,0)
        p=self.root/'out/response.json'
        raw=p.read_bytes()
        original=json.loads(raw)
        self.assertEqual(original['response_contract']['required_fields_present'],required)
        self.assertEqual(original['response_contract']['contract_sha256'],inventory[protocol.name])
        for key in ('rows','limitations','evidence_paths'):
            with self.subTest(field=key):
                changed=dict(original)
                del changed[key]
                p.write_text(json.dumps(changed),encoding='utf8')
                self.assertNotEqual(self.cli('verify').returncode,0)
        p.write_bytes(raw)
        self.assertEqual(self.cli('verify').returncode,0)
        self.request['metadata']['evidence_paths']=[]
        with self.assertRaisesRegex(ValueError,'DECLARED_EVIDENCE_PATHS_REQUIRED'):
            brief.render(self.request,self.root)
        protocol.write_text('Save response.json containing rows.',encoding='utf8')
        with self.assertRaisesRegex(ValueError,'ORIGINAL_PROMPT_OR_PROTOCOL_HASH_CHANGED'):
            brief.render(self.request,self.root)

    def test_explicit_contract_and_generated_fields_cannot_be_overridden(self):
        self.sources['response_contract']={'required':['rows','limitations']}
        _,doc=self.render()
        self.assertEqual(doc['response_contract']['required_fields_present'],['rows','limitations'])
        self.request['metadata']={'rows':[]}
        with self.assertRaisesRegex(ValueError,'METADATA_CANNOT_OVERRIDE_BRIEF'):
            brief.render(self.request,self.root)
        self.sources['prompt']+=' Save response.json containing rows and evidence_paths.'
        with self.assertRaisesRegex(ValueError,'CONFLICTING_ORIGINAL_RESPONSE_DECLARATIONS'):
            self.render()


if __name__=='__main__':
    unittest.main()
