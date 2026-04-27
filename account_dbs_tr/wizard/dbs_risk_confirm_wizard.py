# -*- coding: utf-8 -*-
from odoo import _, fields, models


class DbsRiskConfirmWizard(models.TransientModel):
    _name = 'dbs.risk.confirm.wizard'
    _description = 'DBS Risk Confirm Wizard'

    move_id = fields.Many2one('account.move', required=True, readonly=True)
    contract_id = fields.Many2one('dbs.contract', required=True, readonly=True)
    partner_id = fields.Many2one('res.partner', required=True, readonly=True)
    limit_amount = fields.Monetary(string='DBS Limit', currency_field='currency_id', readonly=True)
    available_amount = fields.Monetary(string='Kullanilabilir Limit', currency_field='currency_id', readonly=True)
    required_amount = fields.Monetary(string='Islem Tutari', currency_field='currency_id', readonly=True)
    over_amount = fields.Monetary(string='Asim Tutari', currency_field='currency_id', readonly=True)
    currency_id = fields.Many2one('res.currency', required=True, readonly=True)
    message = fields.Text(string='Bilgi', readonly=True)

    def action_confirm(self):
        self.ensure_one()
        return self.move_id.with_context(dbs_risk_confirmed=True).action_send_to_dbs()

    def action_cancel(self):
        return {'type': 'ir.actions.act_window_close'}
