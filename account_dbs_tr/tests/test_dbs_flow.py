# -*- coding: utf-8 -*-
import io

from odoo.tests.common import TransactionCase
from odoo.exceptions import UserError


class TestDbsFlow(TransactionCase):

    def test_module_models_exist(self):
        self.env['dbs.contract']
        self.env['dbs.batch']
        self.env['dbs.batch.line']

    def test_adapter_manual_available(self):            
        adapter = self.env['dbs.adapter.manual']
        self.assertTrue(adapter)

    def test_adapter_manual_ack_mapping(self):
        adapter = self.env['dbs.adapter.manual']
        payload = io.StringIO()
        payload.write('line_ref;status;reject_code;message\n')
        payload.write('DBS-1-20260330-00001;ok;;tamam\n')
        payload.write('DBS-1-20260330-00002;fail;R01;limit\n')
        payload.write('DBS-1-20260330-00003;settled;;tahsil\n')

        rows = adapter.import_ack(False, payload.getvalue().encode('utf-8'))

        self.assertEqual(rows[0]['status'], 'accepted')
        self.assertEqual(rows[1]['status'], 'rejected')
        self.assertEqual(rows[1]['reject_code'], 'R01')
        self.assertEqual(rows[2]['status'], 'settled')

    def test_adapter_manual_ack_header_strict_mode(self):
        adapter = self.env['dbs.adapter.manual']
        payload = io.StringIO()
        payload.write('line_ref;status\n')
        payload.write('DBS-1-20260330-00001;ok\n')

        with self.assertRaises(UserError):
            adapter.import_ack(False, payload.getvalue().encode('utf-8'))

    def test_adapter_manual_ack_header_non_strict_mode(self):
        adapter = self.env['dbs.adapter.manual'].with_context(dbs_ack_strict_header=False)
        payload = io.StringIO()
        payload.write('line_ref;status\n')
        payload.write('DBS-1-20260330-00001;ok\n')

        rows = adapter.import_ack(False, payload.getvalue().encode('utf-8'))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['dbs_line_ref'], 'DBS-1-20260330-00001')
        self.assertEqual(rows[0]['status'], 'accepted')

    def test_adapter_manual_ack_cp1254_fallback(self):
        adapter = self.env['dbs.adapter.manual'].with_context(dbs_ack_strict_header=False)
        payload = 'line_ref;status;reject_code;message\nDBS-1-20260330-00001;ok;;fatura \x95 test\n'

        rows = adapter.import_ack(False, payload.encode('cp1254'))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['status'], 'accepted')
