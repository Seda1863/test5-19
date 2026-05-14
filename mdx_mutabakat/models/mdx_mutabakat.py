# -*- coding: utf-8 -*-
import base64
import logging
import uuid
from odoo import models, fields, api, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class MdxMutabakat(models.Model):
    _name = 'mdx.mutabakat'
    _description = 'Mutabakat Mektubu'
    _order = 'date desc, id desc'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(
        string='Mutabakat No',
        readonly=True,
        copy=False,
        default='Yeni',
    )
    partner_id = fields.Many2one(
        'res.partner',
        string='Tedarikçi / Müşteri',
        required=True,
        tracking=True,
    )
    partner_email = fields.Char(
        string='E-Posta',
        related='partner_id.email',
        store=True,
        readonly=False,
    )
    sender_id = fields.Many2one(
        'res.users',
        string='Gönderen',
        default=lambda self: self.env.user,
        tracking=True,
    )
    sender_email = fields.Char(
        string='Yanıt Adresi',
        default='aysenur@minddx.ai',
        help='Tedarikçinin yanıtı bu adrese gönderilecek.',
    )
    company_id = fields.Many2one(
        'res.company',
        string='Şirket',
        default=lambda self: self.env.company,
    )
    date = fields.Date(
        string='Mutabakat Tarihi',
        default=fields.Date.context_today,
        tracking=True,
    )
    period_start = fields.Date(
        string='Dönem Başlangıç',
        required=True,
    )
    period_end = fields.Date(
        string='Dönem Bitiş',
        required=True,
    )
    response_due_date = fields.Date(
        string='Yanıt Son Tarihi',
        help='Bu tarihten sonra yanıt kabul edilmez.',
    )
    state = fields.Selection([
        ('draft', 'Taslak'),
        ('sent', 'Gönderildi'),
        ('opened', 'Açıldı'),
        ('agreed', 'Mutabık'),
        ('disagreed', 'Mutabık Değil'),
        ('expired', 'Süresi Geçti'),
        ('cancelled', 'İptal'),
    ], string='Durum', default='draft', tracking=True, copy=False)

    token = fields.Char(
        string='Güvenlik Token',
        copy=False,
        readonly=True,
    )
    sent_date = fields.Datetime(
        string='Gönderim Tarihi',
        readonly=True,
    )
    opened_date = fields.Datetime(
        string='Açılma Tarihi',
        readonly=True,
    )
    response_date = fields.Datetime(
        string='Yanıt Tarihi',
        readonly=True,
        tracking=True,
    )
    response_note = fields.Text(
        string='Yanıt Notu',
        readonly=True,
    )
    notes = fields.Text(string='Notlar')
    email_message = fields.Text(
        string='E-Posta Mesajı',
        default=lambda self: self._default_email_message(),
        help='Mutabakat e-postasında gönderilecek mesaj. İsterseniz değiştirebilirsiniz.',
    )

    @api.model
    def _default_email_message(self):
        return (
            "İlgili dönem cari hesap mutabakat belgemiz ekte sunulmuştur. "
            "Belgeyi inceleyerek mutabık olmanız halinde kaşeleyip imzalayarak "
            "tarafımıza iletmenizi rica ederiz.\n\n"
            "Mutabık olmadığınız hususlar mevcut ise ayrıntılarıyla birlikte "
            "yanıt adresimize bildirilmesini rica ederiz."
        )

    # ──────────────────────────────────
    # Boolean computed (raporlama)
    # ──────────────────────────────────
    is_opened = fields.Boolean(
        string='Okundu',
        compute='_compute_status_booleans',
        store=True,
    )
    is_agreed = fields.Boolean(
        string='Mutabık',
        compute='_compute_status_booleans',
        store=True,
    )
    is_disagreed = fields.Boolean(
        string='Mutabık Değil',
        compute='_compute_status_booleans',
        store=True,
    )
    is_pending = fields.Boolean(
        string='Bekleyen',
        compute='_compute_status_booleans',
        store=True,
    )

    @api.depends('state', 'opened_date')
    def _compute_status_booleans(self):
        for rec in self:
            rec.is_opened = bool(rec.opened_date)
            rec.is_agreed = rec.state == 'agreed'
            rec.is_disagreed = rec.state == 'disagreed'
            rec.is_pending = rec.state in ('sent', 'opened')

    # ──────────────────────────────────
    # Satırlar
    # ──────────────────────────────────
    line_ids = fields.One2many(
        'mdx.mutabakat.line',
        'mutabakat_id',
        string='Mutabakat Detayları',
    )

    # ──────────────────────────────────
    # Computed alanlar
    # ──────────────────────────────────
    total_invoice_count = fields.Integer(
        string='Toplam Belge Sayısı',
        compute='_compute_totals',
        store=True,
    )
    total_amount = fields.Monetary(
        string='Toplam Tutar',
        compute='_compute_totals',
        store=True,
        currency_field='currency_id',
    )
    partner_balance = fields.Monetary(
        string='Bakiye',
        currency_field='currency_id',
        help='İş Ortağı Defteri bakiyesi (Borç - Alacak)',
    )
    currency_id = fields.Many2one(
        'res.currency',
        string='Para Birimi',
        default=lambda self: self.env.company.currency_id,
    )

    # ──────────────────────────────────
    # Gönderen firma bilgileri (computed)
    # ──────────────────────────────────
    company_vat = fields.Char(related='company_id.vat', string='Vergi No (Gönderen)')
    company_phone = fields.Char(related='company_id.phone', string='Telefon (Gönderen)')
    partner_vat = fields.Char(related='partner_id.vat', string='Vergi No (Alıcı)')
    partner_phone = fields.Char(related='partner_id.phone', string='Telefon (Alıcı)')

    @api.depends('line_ids.invoice_count', 'line_ids.amount', 'line_ids.mutabakat_type')
    def _compute_totals(self):
        for rec in self:
            # opening satırı TOPLAM'a dahil edilmez (opening bakiye ayrı bir kavram)
            non_opening = rec.line_ids.filtered(lambda l: l.mutabakat_type != 'opening')
            rec.total_invoice_count = sum(non_opening.mapped('invoice_count'))
            rec.total_amount = sum(non_opening.mapped('amount'))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'Yeni') == 'Yeni':
                vals['name'] = self.env['ir.sequence'].next_by_code('mdx.mutabakat') or 'Yeni'
            if not vals.get('token'):
                vals['token'] = str(uuid.uuid4())
        return super().create(vals_list)

    # ──────────────────────────────────
    # Aksiyonlar
    # ──────────────────────────────────
    def _build_email_body(self):
        """Mail gövdesini Python'da oluştur"""
        # Yetkili adı: partner'ın child_ids'te contact type varsa onu al, yoksa partner adı
        contact_name = self.partner_id.name or 'Yetkili'
        # Message paragraphs
        message_html = ''.join(
            f'<p style="line-height: 1.8; margin: 8px 0;">{p.strip()}</p>'
            for p in (self.email_message or '').split('\n') if p.strip()
        )
        reply_email = self.sender_email or self.company_id.email or ''

        return f"""
<div style="font-family: 'Segoe UI', Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 30px; background: #fff;">
    <h2 style="text-align: center; color: #1a1a2e; font-size: 20px; border-bottom: 2px solid #4a90d9; padding-bottom: 10px;">
        Cari Hesap Mutabakat Mektubu
    </h2>
    <p style="margin-top: 20px;"><strong>Sayın {contact_name},</strong></p>
    <p style="line-height: 1.8;">
        Şirketimiz kayıtlarına göre <strong>{self.period_start}</strong> — <strong>{self.period_end}</strong>
        tarihleri arasındaki cari hesap mutabakat belgemiz ilişikte sunulmuştur.
    </p>
    {message_html}
    <p style="line-height: 1.8;">
        <strong>Yanıt Adresi:</strong> {reply_email}
    </p>
    <p style="margin-top: 25px;">Saygılarımızla,</p>
    <p><strong>{self.company_id.name}</strong></p>
    <p style="color: #999; font-size: 11px; text-align: center; margin-top: 30px; border-top: 1px solid #eee; padding-top: 15px;">
        Bu e-posta {self.company_id.name} tarafından otomatik olarak gönderilmiştir.
        Mutabakat No: {self.name}
    </p>
</div>"""

    def action_send_email(self):
        """Mutabakat mektubunu e-posta ile gönder"""
        self.ensure_one()
        if not self.partner_email:
            raise UserError(_("Tedarikçinin e-posta adresi tanımlı değil!"))

        # Token yoksa oluştur (eski kayıtlar için) — explicit write
        if not self.token:
            self.write({'token': str(uuid.uuid4())})

        _logger.info(
            "Mutabakat mail gönderiliyor: id=%s, to=%s, token=%s, base_url=%s",
            self.id, self.partner_email, self.token, self.get_base_url(),
        )

        # PDF oluştur ve ek olarak ekle
        report = self.env.ref('mdx_mutabakat.action_report_mdx_mutabakat')
        pdf_content, _content_type = self.env['ir.actions.report']._render_qweb_pdf(report, self.ids)
        pdf_name = 'Mutabakat_%s.pdf' % (self.name or 'dokuman')
        attachment = self.env['ir.attachment'].create({
            'name': pdf_name,
            'type': 'binary',
            'datas': base64.b64encode(pdf_content),
            'res_model': self._name,
            'res_id': self.id,
            'mimetype': 'application/pdf',
        })

        # Template kullanmadan doğrudan mail.mail ile gönder
        body_html = self._build_email_body()
        mail = self.env['mail.mail'].sudo().create({
            'subject': 'Mutabakat Mektubu — %s — %s' % (self.company_id.name, self.name),
            'body_html': body_html,
            'email_from': self.company_id.email or 'noreply@minddx.ai',
            'email_to': self.partner_email,
            'reply_to': self.sender_email or self.company_id.email,
            'attachment_ids': [(4, attachment.id)],
            'auto_delete': False,
            'model': self._name,
            'res_id': self.id,
        })
        mail.send()

        self.write({
            'state': 'sent',
            'sent_date': fields.Datetime.now(),
        })
        self.message_post(body=_(
            "Mutabakat mektubu <b>%s</b> adresine gönderildi."
        ) % self.partner_email)

    def action_preview_pdf(self):
        """PDF raporunu tarayıcıda yeni sekmede aç (indirmeden görüntüle)"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_url',
            'url': '/report/pdf/mdx_mutabakat.report_mdx_mutabakat/%s' % self.id,
            'target': 'new',
        }

    def action_mark_agreed(self):
        """Manuel olarak mutabık olarak işaretle"""
        self.write({
            'state': 'agreed',
            'response_date': fields.Datetime.now(),
        })

    def action_mark_disagreed(self):
        """Manuel olarak mutabık değil olarak işaretle"""
        self.write({
            'state': 'disagreed',
            'response_date': fields.Datetime.now(),
        })

    def action_cancel(self):
        self.write({'state': 'cancelled'})

    def action_reset_draft(self):
        self.write({
            'state': 'draft',
            'response_date': False,
            'response_note': False,
            'sent_date': False,
            'opened_date': False,
        })

    def cron_mark_expired(self):
        """Yanıt son tarihi geçen mutabakatları 'expired' olarak işaretle"""
        expired = self.search([
            ('state', 'in', ('sent', 'opened')),
            ('response_due_date', '!=', False),
            ('response_due_date', '<', fields.Date.today()),
        ])
        if expired:
            expired.write({'state': 'expired'})
            _logger.info("Süresi geçen mutabakatlar: %s", expired.ids)

    def action_compute_lines(self):
        """İş Ortağı Defteri mantığıyla bakiye hesapla (account.move.line.balance)"""
        self.ensure_one()
        self.line_ids.unlink()

        if not self.partner_id or not self.period_start or not self.period_end:
            raise UserError(_("Tedarikçi ve dönem bilgileri zorunludur."))

        account_types = ('asset_receivable', 'liability_payable')

        # 1) Başlangıç bakiyesi — balance kullan (debit - credit değil)
        opening_amls = self.env['account.move.line'].search([
            ('partner_id', '=', self.partner_id.id),
            ('parent_state', '=', 'posted'),
            ('date', '<', self.period_start),
            ('account_id.account_type', 'in', account_types),
        ])
        opening_balance = sum(opening_amls.mapped('balance'))

        # 2) Dönem içi hareketler
        period_amls = self.env['account.move.line'].search([
            ('partner_id', '=', self.partner_id.id),
            ('parent_state', '=', 'posted'),
            ('date', '>=', self.period_start),
            ('date', '<=', self.period_end),
            ('account_id.account_type', 'in', account_types),
        ])
        period_debit = sum(period_amls.mapped('debit'))
        period_credit = sum(period_amls.mapped('credit'))
        period_balance = sum(period_amls.mapped('balance'))
        period_str = f"{self.period_start.strftime('%d.%m.%Y')} - {self.period_end.strftime('%d.%m.%Y')}"

        # Başlangıç bakiyesi her zaman oluşturulur (sıfır olsa bile)
        lines = [
            {
                'mutabakat_id': self.id,
                'mutabakat_type': 'opening',
                'period': f"{self.period_start.strftime('%d.%m.%Y')} öncesi",
                'invoice_count': 0,
                'amount': opening_balance,
            },
        ]

        debit_lines = period_amls.filtered(lambda l: l.debit > 0)
        if debit_lines:
            lines.append({
                'mutabakat_id': self.id,
                'mutabakat_type': 'borc',
                'period': period_str,
                'invoice_count': len(debit_lines),
                'amount': period_debit,
            })

        credit_lines = period_amls.filtered(lambda l: l.credit > 0)
        if credit_lines:
            lines.append({
                'mutabakat_id': self.id,
                'mutabakat_type': 'alacak',
                'period': period_str,
                'invoice_count': len(credit_lines),
                'amount': period_credit,
            })

        self.partner_balance = opening_balance + period_balance
        self.env['mdx.mutabakat.line'].create(lines)

    def get_response_url(self, action):
        """Mutabıkız / Mutabık Değiliz URL'i oluştur"""
        base_url = self.get_base_url()
        return f"{base_url}/mutabakat/response/{self.token}/{action}"

    def get_confirm_url(self):
        """Online onay sayfası URL'i"""
        base_url = self.get_base_url()
        return f"{base_url}/mutabakat/confirm/{self.token}"


class MdxMutabakatLine(models.Model):
    _name = 'mdx.mutabakat.line'
    _description = 'Mutabakat Satırı'
    _order = 'id'

    mutabakat_id = fields.Many2one(
        'mdx.mutabakat',
        string='Mutabakat',
        required=True,
        ondelete='cascade',
    )
    mutabakat_type = fields.Selection([
        ('opening', 'Başlangıç Bakiyesi'),
        ('alacak', 'Alacak'),
        ('borc', 'Borç'),
    ], string='Tip', required=True)
    period = fields.Char(string='Dönem')
    invoice_count = fields.Integer(string='Belge Sayısı')
    amount = fields.Monetary(
        string='Toplam Tutar',
        currency_field='currency_id',
    )
    currency_id = fields.Many2one(
        related='mutabakat_id.currency_id',
    )
