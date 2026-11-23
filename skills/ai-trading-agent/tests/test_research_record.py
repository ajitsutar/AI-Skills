import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
import research_contracts as contracts
import research_record as records


class RequestRecordTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()
        self.source = self.root/"method notes.json"
        self.record = {"period":"weekly", "methods":["level", "change"], "unit":"index points"}
        self.source.write_text(json.dumps({"panels":[{"x/y~":self.record}],"household":"OUTSIDE_RECORD"}),encoding="utf8")
        self.prompt = self.root/"question.txt"
        self.prompt.write_text("Design a study for `method notes.json#/panels/0/x~1y~0`.",encoding="utf8")

    def entry(self,*extra):
        return subprocess.run([sys.executable,"-X","utf8","-B",str(ROOT/"scripts/research_preflight.py"),
                               "--request",str(self.prompt),"--source-root",str(self.root),"--source",self.source.name,*map(str,extra)],
                              capture_output=True,text=True,encoding="utf8")

    def test_open_without_workflow_choice_reads_only_named_record(self):
        result = self.entry("--source","irrelevant-file-that-does-not-exist.json")
        self.assertEqual(result.returncode,0,result.stderr)
        opened=json.loads(result.stdout)
        self.assertEqual(opened["record"],self.record)
        self.assertNotIn("OUTSIDE_RECORD",result.stdout)
        self.assertEqual(opened["request_sha256"],hashlib.sha256(self.prompt.read_bytes()).hexdigest())
        self.assertEqual(opened["source_sha256"],hashlib.sha256(self.source.read_bytes()).hexdigest())

    def test_literal_punctuation_ambiguity_allowlist_and_escaped_pointers(self):
        doc=b'{"alpha":1,"alpha.":2,"only":3,"a b":4}'
        def locate(prompt):
            return records.selected(prompt.encode(),{"notes.json"},lambda _:doc)
        self.assertEqual(locate("Review notes.json#/only: details follow.")["record"],3)
        self.assertEqual(locate("Review <notes.json#/alpha.>.")["record"],2)
        self.assertEqual(locate("Review notes.json#/a%20b.")["record"],4)
        for prompt in ("Review notes.json#/alpha.","Compare notes.json#/only and notes.json#/alpha",
                       "Read ../notes.json#/only","Read https://example.invalid/notes.json#/only",
                       "Read other.json#/only","Read notes.json#","Review notes.json#/missing","No explicit record",
                       "Read notes.json#/a%","Read notes.json#/bad~2","Read notes.json#/only and hidden.json#/other"):
            with self.subTest(prompt=prompt),self.assertRaises(ValueError):
                locate(prompt)

    def test_open_uses_entire_bare_key_and_respects_other_code_spans(self):
        keys = ["base", "base(sum)", "base[3]", "base's", 'base"quoted"', "base;units", "base#section"]
        self.source = self.root/"measure.json"
        self.source.write_text(json.dumps({k:"value of "+k for k in keys}),encoding="utf8")
        for key in keys:
            with self.subTest(key=key):
                self.prompt.write_text("Compare `gross result` with measure.json#/"+key+" before `later operations`.",encoding="utf8")
                run = self.entry()
                self.assertEqual(run.returncode,0,run.stderr)
                data = json.loads(run.stdout)
                self.assertEqual((data["pointer"],data["record"]),("/"+key,"value of "+key))
        # A valid prefix is never substituted if the complete neighboring key is missing.
        for fragment in ("base(other)", "base[0]", "base'absent", "base\"absent", "base>unclosed", "base)"):
            with self.subTest(fragment=fragment):
                self.prompt.write_text("Inspect measure.json#/"+fragment+" before review.",encoding="utf8")
                self.assertNotEqual(self.entry().returncode,0)

    def test_never_extract_a_local_substring_from_larger_url_or_adjacent_markup(self):
        raw=b'{"net":1,"net.":2,"study[1]":3}'
        def read(text):
            return records.selected(text.encode(),{"data.json"},lambda _:raw)
        self.assertEqual(read("Open <data.json#/net>.")["record"],1)
        self.assertEqual(read("Open `data.json#/study[1]`.")["record"],3)
        for text in ("Inspect https://host.invalid/a/data.json#/net",
                     "Inspect https://host.invalid/?next=data.json#/net",
                     "Inspect [report](https://host.invalid/data.json#/net)",
                     "Inspect (data.json#/net)", "Inspect 'data.json#/net'",
                     "Inspect `data.json#/net`suffix", "Inspect <data.json#/net>data.json#/net.",
                     "Inspect data.json#/net,data.json#/study[1]", "Inspect see:data.json#/net"):
            with self.subTest(text=text),self.assertRaises(ValueError):
                read(text)

    def test_selected_design_dispatch_and_replay_original_request(self):
        rule=lambda purpose:{"purpose":purpose,"measure":"excess return" if purpose=="performance" else "shortfall",
                             "comparison":">" if purpose=="performance" else "<","threshold":0.01,"units":"fraction",
                             "measurement_window":"locked sample","on_failure":"hold","if_unmeasurable":"inconclusive"}
        choices={"design_kind":"research_contract","design_terms":{"benchmark":{"proposal":"equal-weight reference"},
                 "evaluation_window":{"proposal":"chronological holdout"},"execution_convention":{"proposal":"following observation"},
                 "development_validation_split":{"proposal":"predeclared sequential folds"}},
                 "proposed_decision_rules":[rule("performance"),rule("risk")],
                 "answer_controls":{"session_basis":"reported release dates","initial_state":"empty portfolio","warmup":"enough prior releases",
                 "variants":{"mode":"fixed_primary","primary":{"record_pointer":"/methods/0"}},
                 "sample":{"minimum_observations":40,"observation_unit":"weeks","minimum_events":10,"event_unit":"signals","rationale":"prespecified precision check"},
                 "uncertainty":{"performance_rule":0,"confidence":0.95,"method":"moving-block bootstrap","dependence_treatment":"resample contiguous weeks"}}}
        settings=self.root/"settings.json";settings.write_text(json.dumps(choices),encoding="utf8")
        output=self.root/"export"
        run=self.entry("--design",settings,"--private-output",output)
        self.assertEqual(run.returncode,0,run.stderr)
        self.assertEqual(json.loads(run.stdout)["operation"],"strategy-answer")
        want=contracts.verify(output,output/"answer.md",output/"answer-rows.json")
        self.assertEqual(want["operation"],"strategy-answer")
        row=json.loads((output/"answer-rows.json").read_bytes())[0]
        self.assertEqual(row["supplied_strategy"],self.record)
        self.assertEqual(row["original_request_binding"]["pointer"],"/panels/0/x~1y~0")
        self.assertNotIn("OUTSIDE_RECORD",(output/"answer.md").read_text(encoding="utf8"))
        self.assertEqual((output/"source-bytes"/records.PROMPT).read_bytes(),self.prompt.read_bytes())
        settings.write_text(json.dumps(dict(choices,strategy_source={"source_id":"record","pointer":"/household"})),encoding="utf8")
        self.assertIn("DESIGN_CHOICES_ONLY",self.entry("--design",settings,"--private-output",self.root/"other").stderr)
        captured=output/"source-bytes"/records.PROMPT
        captured.write_bytes(b"Read `method notes.json#/household`.")
        snapshot=json.loads((output/"receipt.json").read_bytes())
        snapshot["files"]["source-bytes/"+records.PROMPT]=hashlib.sha256(captured.read_bytes()).hexdigest()
        (output/"receipt.json").write_text(json.dumps(snapshot),encoding="utf8")
        with self.assertRaises(ValueError):
            contracts.verify(output)
