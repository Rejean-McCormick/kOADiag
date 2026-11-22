# -*- coding: utf-8 -*-
"""No remote network: all probe tests use a temporary local HTTP server."""
import json
import socket
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from koa_ecosystem_diag import port_diagnostics as c0


class FakeHTTP(BaseHTTPRequestHandler):
    title = 'Orgo · Organize and Go'
    marker = ''
    def do_GET(self):
        data = ('<html><head><title>'+self.title+'</title></head><body>test</body></html>').encode()
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        if self.marker:
            self.send_header('X-KOA-Service-Id', self.marker)
        self.end_headers()
        self.wfile.write(data)
    def log_message(self, *args):
        pass


class C0Tests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.registry = self.root / 'register.json'
        self.doc = {'schema_version': 1, 'registry_id': c0.REGISTRY_ID,
                    'host': '127.0.0.1', 'transport': 'tcp',
                    'pool': {'start': 21100, 'end': 21199},
                    'blocks': [{'owner':'orgo','start':21110,'end':21119},
                               {'owner':'initkoa','start':21120,'end':21129}],
                    'services': [{'id':'orgo-web','owner':'orgo','port':21110},
                                 {'id':'initkoa-web','owner':'initkoa','port':21120}]}
        self.save()

    def save(self):
        self.registry.write_text(json.dumps(self.doc), encoding='utf-8')

    def test_registry_validation_and_missing_file(self):
        p, reg = c0.read_registry(self.root, self.registry)
        self.assertEqual(len(reg['services']), 2)
        self.assertEqual(p, self.registry)
        with self.assertRaises(FileNotFoundError):
            c0.read_registry(self.root)

    def test_duplicate_port_refused(self):
        self.doc['services'][1]['port'] = 21110
        self.save()
        with self.assertRaises(ValueError):
            c0.read_registry(self.root, self.registry)

    def test_rogue_remote_host_refused(self):
        self.doc['host'] = '0.0.0.0'
        self.save()
        with self.assertRaises(ValueError):
            c0.read_registry(self.root, self.registry)

    def test_out_of_block_refused(self):
        self.doc['services'][0]['port'] = 21155
        self.save()
        with self.assertRaises(ValueError):
            c0.read_registry(self.root, self.registry)

    def with_server(self, title, marker=''):
        handler = type('CustomHTTP', (FakeHTTP,), {'title': title, 'marker': marker})
        server = ThreadingHTTPServer(('127.0.0.1', 0), handler)
        self.addCleanup(server.server_close)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.shutdown)
        return server.server_address[1]

    def test_wrong_service_is_not_counted_as_healthy(self):
        port = self.with_server('Orgo · Organize and Go')
        result = c0.probe_service({'id':'initkoa-web','owner':'initkoa','port':port})
        self.assertEqual(result['status'], 'WRONG_SERVICE')

    def test_family_match_does_not_claim_specific_instance(self):
        port = self.with_server('Orgo · Organize and Go')
        result = c0.probe_service({'id':'orgo-koali-web','owner':'orgo','port':port})
        self.assertEqual(result['status'], 'FAMILY_MATCH')

    def test_exact_header_confirms_identity(self):
        port = self.with_server('Application', 'orgo-web')
        result = c0.probe_service({'id':'orgo-web','owner':'orgo','port':port})
        self.assertEqual(result['status'], 'IDENTITY_CONFIRMED')
        result = c0.probe_service({'id':'initkoa-web','owner':'initkoa','port':port})
        self.assertEqual(result['status'], 'WRONG_SERVICE')

    def test_http_without_identity_is_unverified(self):
        port = self.with_server('Generic')
        result = c0.probe_service({'id':'orgo-web','owner':'orgo','port':port})
        self.assertEqual(result['status'], 'HTTP_UNVERIFIED')

    def test_closed_port_not_a_collision(self):
        with socket.socket() as s:
            s.bind(('127.0.0.1', 0))
            port = s.getsockname()[1]
        result = c0.probe_service({'id':'orgo-web','owner':'orgo','port':port})
        self.assertEqual(result['status'], 'STOPPED')

    def test_non_http_port_not_claimed_identity(self):
        with socket.socket() as s:
            s.bind(('127.0.0.1',0))
            s.listen(1)
            port = s.getsockname()[1]
            result = c0.probe_service({'id':'orgo-koali-pglite','owner':'orgo','port':port})
        self.assertEqual(result['status'], 'TCP_OPEN_UNVERIFIED')

    def test_reports_are_writable_without_secrets(self):
        result = c0.check_all(self.root, registry=self.registry, timeout=0.1)
        folder = c0.write_reports(result, self.root/'reports')
        self.assertEqual(result['expected'],2)
        self.assertTrue((folder/'ports-c0.csv').is_file())
        self.assertTrue((folder/'ports-c0.json').is_file())
        self.assertTrue((folder/'ports-c0.txt').is_file())
        self.assertTrue(all(not link['e2e_proven'] for link in result['endpoint_pairs']))


if __name__ == '__main__':
    unittest.main()
