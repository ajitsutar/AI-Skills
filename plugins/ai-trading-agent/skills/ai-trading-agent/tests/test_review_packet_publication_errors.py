"""Packet consumer preserves stream-error origin after genuine temporary opens."""
import errno
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

import test_review_packet as fixtures

packet=fixtures.module
research=fixtures.research


class PacketPublicationErrorTests(unittest.TestCase):
    setUp=fixtures.ReviewPacketTests.setUp
    add=fixtures.ReviewPacketTests.add
    write=fixtures.ReviewPacketTests.write
    prepare=fixtures.ReviewPacketTests.prepare

    def files(self):
        return {p.relative_to(self.output).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
                for p in self.output.rglob('*') if p.is_file()}

    def retry_cli(self):
        command=[sys.executable,'-X','utf8','-B',str(Path(packet.__file__).resolve()),'prepare',
                 '--request',str(self.request_path),'--manifest',str(self.manifest),'--manifest-sha256',self.pin,
                 '--source-root',str(self.source),'--private-output-root',str(self.output)]
        environment=dict(os.environ,PYTHONDONTWRITEBYTECODE='1')
        result=subprocess.run(command,capture_output=True,text=True,encoding='utf-8',env=environment)
        self.assertEqual(result.returncode,0,result.stderr)
        value=json.loads(result.stdout);self.assertTrue(value['dispatch_ready'])
        self.assertEqual(packet.verify(value['packet_directory'],value['packet_sha256'])['integrity_status'],'VERIFIED')
        folder=Path(value['packet_directory'])
        for sid,source in self.sources.items():self.assertEqual((folder/'sealed'/(sid+'.bin')).read_bytes(),source['raw'])
        self.assertEqual((folder/'participants/brief_assisted/brief.bin').read_bytes(),self.sources['brief']['raw'])
        return value

    def error(self,kind):
        value=FileNotFoundError(errno.ENOENT,'injected successful-open stream fault') if kind=='enoent' else OSError(errno.EINVAL,'injected successful-open stream fault')
        if kind=='native206':value.winerror=206
        return value

    def stream_fault(self,operation,error):
        opened=[];actual_open=research._open_temporary;actual_sync=research.os.fsync
        class Stream:
            def __init__(self,raw):self.raw=raw
            def close(self):
                self.raw.close()
                if operation=='preflight-close':raise error
            def __enter__(self):self.raw.__enter__();return self
            def __exit__(self,*args):
                self.raw.__exit__(*args)
                if operation=='publication-close':raise error
            def write(self,data):
                if operation=='write':raise error
                return self.raw.write(data)
            def flush(self):
                if operation=='flush':raise error
                return self.raw.flush()
            def fileno(self):return self.raw.fileno()
        def opening(*args):
            path,raw=actual_open(*args);opened.append(raw);return path,Stream(raw)
        def sync(fd):
            if operation=='fsync':raise error
            return actual_sync(fd)
        observed=None
        with patch.object(research,'_open_temporary',opening),patch.object(research.os,'fsync',sync), \
                patch.object(research,'_publish',wraps=research._publish) as publish:
            try:self.prepare()
            except Exception as caught:observed=caught
            if operation=='preflight-close':self.assertEqual(publish.call_count,0)
        self.assertTrue(opened);self.assertTrue(all(raw.closed for raw in opened))
        self.assertEqual(self.files(),{})
        self.retry_cli()  # Actual unpatched CLI, exact sealed and participant bytes.
        self.assertIs(observed,error)
        self.assertIsNone(observed.__cause__)

    def test_successful_preflight_close_preserves_enoent_and_native206_identity(self):
        for kind in ('enoent','native206'):
            with self.subTest(kind=kind):
                self.output=self.root/('preflight-'+kind);self.output.mkdir()
                self.stream_fault('preflight-close',self.error(kind))

    def test_packet_publication_stream_faults_keep_original_identity_and_recover(self):
        for operation in ('write','flush','fsync','publication-close'):
            for kind in ('enoent','native206'):
                with self.subTest(operation=operation,kind=kind):
                    self.output=self.root/(operation+'-'+kind);self.output.mkdir()
                    self.stream_fault(operation,self.error(kind))

    def test_actual_directory_operation_failure_retains_path_guidance(self):
        folder=self.output/'synthetic-review-r1';actual=Path.mkdir
        error=FileNotFoundError(errno.ENOENT,'injected actual directory creation failure',str(folder))
        def mkdir(path,*args,**kwargs):
            if path.resolve()==folder.resolve():raise error
            return actual(path,*args,**kwargs)
        with patch.object(Path,'mkdir',mkdir),patch.object(research,'_preflight_publications',wraps=research._preflight_publications) as preflight:
            with self.assertRaisesRegex(ValueError,'OUTPUT_PUBLICATION_PATH_UNAVAILABLE') as raised:self.prepare()
            self.assertIs(raised.exception.__cause__,error);self.assertEqual(preflight.call_count,0)
        self.assertEqual(self.files(),{});self.retry_cli()

    def test_directory_fault_injection_matches_existing_parent_alias(self):
        self.output=self.output/'..'/self.output.name
        self.assertTrue(self.output.is_dir())
        self.assertNotEqual(self.output,self.output.resolve())
        self.test_actual_directory_operation_failure_retains_path_guidance()

    def test_actual_preflight_open_path_failure_retains_guidance_then_retries(self):
        actual=Path.open;opened=[]
        def opening(path,mode='r',*args,**kwargs):
            if mode=='xb' and path.parent.name=='brief_assisted':
                error=FileNotFoundError(errno.ENOENT,'injected actual path open failure',str(path));opened.append(error);raise error
            return actual(path,mode,*args,**kwargs)
        with patch.object(Path,'open',opening),patch.object(research,'_publish',wraps=research._publish) as publish:
            with self.assertRaisesRegex(ValueError,'OUTPUT_PUBLICATION_PATH_UNAVAILABLE') as raised:self.prepare()
            self.assertIs(raised.exception.__cause__,opened[-1]);self.assertEqual(publish.call_count,0)
        self.assertEqual(self.files(),{});self.retry_cli()

    def test_idempotence_and_foreign_existing_packet_bytes_remain_protected(self):
        first=self.prepare();before=self.files();second=self.prepare()
        self.assertEqual(first['packet_sha256'],second['packet_sha256']);self.assertEqual(self.files(),before)
        foreign=Path(first['packet_directory'])/'request.json';foreign.write_bytes(b'foreign bytes')
        with self.assertRaisesRegex(ValueError,'IMMUTABLE_ARTIFACT_CONFLICT'):self.prepare()
        self.assertEqual(foreign.read_bytes(),b'foreign bytes')


if __name__=='__main__':unittest.main()
