# -*- coding: utf-8 -*-

import logging
from markupsafe import escape
from odoo import api, fields, models, _

_logger = logging.getLogger(__name__)


class MdxEfaturaIslem(models.Model):
    _name = 'mdx.efatura.islem'
    _description = 'E-Fatura İşlem Kaydı'
    _order = 'create_date desc'
    _rec_name = 'name'

    name = fields.Char('İşlem No', readonly=True, default=lambda self: _('New'), copy=False)

    document_ref = fields.Reference(
        selection=[('account.move', 'Fatura'), ('stock.picking', 'İrsaliye')],
        string='Belge',
        index=True,
    )
    document_type = fields.Selection([
        ('EFATURA', 'E-Fatura'),
        ('EARSIV', 'E-Arşiv'),
        ('EIHRACAT', 'E-İhracat'),
        ('EIRSALIYE', 'E-İrsaliye'),
    ], string='Belge Türü')

    state = fields.Selection([
        ('draft', 'Hazırlanıyor'),
        ('validating', 'Doğrulanıyor'),
        ('sending', 'Gönderiliyor'),
        ('sent', 'Gönderildi'),
        ('error', 'Hata'),
        ('retry_scheduled', 'Tekrar Planlandı'),
        ('cancelled', 'İptal'),
    ], default='draft', string='Durum', index=True)

    # Error handling
    error_code_id = fields.Many2one('mdx.efatura.hata.kodu', string='Hata Kodu', ondelete='set null')
    error_message = fields.Text('Ham Hata Mesajı')
    error_display = fields.Html('Hata Detayı', compute='_compute_error_display', sanitize=True)

    # Retry mechanism
    retry_count = fields.Integer('Deneme Sayısı', default=0)
    max_retry = fields.Integer('Max Deneme', default=3)
    last_attempt_date = fields.Datetime('Son Deneme')
    next_retry_date = fields.Datetime('Sonraki Deneme')
    can_retry = fields.Boolean('Yeniden Denenebilir', compute='_compute_can_retry', store=True)

    # Series management
    series_id = fields.Many2one('mdx.fatura.seri', string='Kullanılan Seri', ondelete='set null')
    series_number = fields.Integer('Seri Numarası')
    series_confirmed = fields.Boolean('Seri Onaylandı', default=False)

    # Technical data
    xml_content = fields.Text('XML İçeriği')
    response_content = fields.Text('Yanıt İçeriği')

    company_id = fields.Many2one('res.company', string='Şirket', default=lambda self: self.env.company)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code('mdx.efatura.islem') or _('New')
        return super().create(vals_list)

    @api.depends('error_code_id', 'error_message')
    def _compute_error_display(self):
        for record in self:
            if record.error_code_id:
                solution_html = ''
                if record.error_code_id.solution_hint_tr:
                    solution_html = (
                        '<p class="text-muted"><i class="fa fa-lightbulb-o"></i> '
                        '%s</p>' % escape(record.error_code_id.solution_hint_tr)
                    )
                record.error_display = (
                    '<div class="alert alert-danger">'
                    '<h4><i class="fa fa-exclamation-triangle"></i> %s</h4>'
                    '<p><strong>%s</strong></p>'
                    '%s'
                    '</div>'
                ) % (
                    escape(record.error_code_id.code),
                    escape(record.error_code_id.user_message_tr or ''),
                    solution_html,
                )
            elif record.error_message:
                record.error_display = (
                    '<div class="alert alert-warning">'
                    '<p>%s</p>'
                    '</div>'
                ) % escape(record.error_message)
            else:
                record.error_display = False

    @api.depends('retry_count', 'max_retry', 'error_code_id', 'state')
    def _compute_can_retry(self):
        for record in self:
            record.can_retry = (
                record.retry_count < record.max_retry
                and record.error_code_id
                and record.error_code_id.is_retryable
                and record.state == 'error'
            )

    def action_process_retry_queue(self):
        """Cron: Planlanmış tekrar denemeleri işle."""
        return self.env['mdx.retry.manager.mixin'].process_retry_queue()

    def send_daily_error_report(self):
        """Günlük hata raporunu loglar (cron job)."""
        today_start = fields.Datetime.now().replace(hour=0, minute=0, second=0)
        error_transactions = self.search([
            ('state', '=', 'error'),
            ('create_date', '>=', today_start),
        ])
        if error_transactions:
            _logger.info(
                "Günlük hata raporu: %d adet hatalı işlem tespit edildi.",
                len(error_transactions),
            )
            categories = {}
            for trans in error_transactions:
                cat = trans.error_code_id.category if trans.error_code_id else 'UNKNOWN'
                categories[cat] = categories.get(cat, 0) + 1
            for cat, count in categories.items():
                _logger.info("  Kategori %s: %d adet", cat, count)
