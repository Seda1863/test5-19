# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import UserError


class MdxYilsonuKapanishRun(models.Model):
    _name = 'mdx.yilsonu.kapanish.run'
    _description = 'Dönem Sonu Kapanış Kaydı'
    _order = 'date_from desc, id desc'
    _rec_name = 'period_label'

    company_id = fields.Many2one(
        'res.company', string='Şirket', required=True,
        default=lambda self: self.env.company,
    )
    period_label = fields.Char(string='Dönem', required=True)
    date_from = fields.Date(string='Başlangıç', required=True)
    date_to = fields.Date(string='Bitiş', required=True)
    journal_id = fields.Many2one('account.journal', string='Yevmiye Defteri')
    created_uid = fields.Many2one(
        'res.users', string='Oluşturan',
        default=lambda self: self.env.user, readonly=True,
    )

    move_ids = fields.Many2many(
        'account.move',
        'mdx_kapanish_run_move_rel', 'run_id', 'move_id',
        string='Oluşturulan Yevmiyeler',
    )
    move_count = fields.Integer(compute='_compute_move_stats', string='Yevmiye Sayısı')
    all_posted = fields.Boolean(compute='_compute_move_stats', string='Tümü Onaylı')
    has_draft = fields.Boolean(compute='_compute_move_stats', string='Onay Bekleyenler Var')

    step_yansitma_done = fields.Boolean(string='Yansıtma', default=False)
    step_kapanish_done = fields.Boolean(string='Kapatma', default=False)
    step_devir_done = fields.Boolean(string='690 Devir', default=False)

    warnings = fields.Text(string='Uyarılar', readonly=True)

    @api.depends('move_ids', 'move_ids.state')
    def _compute_move_stats(self):
        for rec in self:
            moves = rec.move_ids
            rec.move_count = len(moves)
            states = moves.mapped('state')
            rec.all_posted = bool(states) and all(s == 'posted' for s in states)
            rec.has_draft = 'draft' in states

    def action_view_moves(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Kapanış Yevmiyeleri — %s') % self.period_label,
            'res_model': 'account.move',
            'view_mode': 'list,form',
            'domain': [('id', 'in', self.move_ids.ids)],
            'target': 'current',
        }

    def action_post_all_moves(self):
        self.ensure_one()
        draft_moves = self.move_ids.filtered(lambda m: m.state == 'draft')
        if not draft_moves:
            raise UserError(_('Onaylanacak taslak yevmiye yok.'))
        draft_moves.action_post()
        return True
