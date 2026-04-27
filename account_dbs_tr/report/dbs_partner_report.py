# -*- coding: utf-8 -*-
from odoo import api, models


class ReportDbsPartner(models.AbstractModel):
    _name = 'report.account_dbs_tr.report_dbs_partner_document'
    _description = 'DBS Partner Report'

    @api.model
    def _get_report_values(self, docids, data=None):
        docs = self.env['res.partner'].browse(docids)
        payloads = {partner.id: partner._get_dbs_report_payload() for partner in docs}
        return {
            'doc_ids': docids,
            'doc_model': 'res.partner',
            'docs': docs,
            'payloads': payloads,
        }
