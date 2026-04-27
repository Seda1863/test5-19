# -*- coding: utf-8 -*-
import uuid
from odoo import models, fields, api, _
from odoo.exceptions import UserError


class MdxMutabakatWizard(models.TransientModel):
    _name = 'mdx.mutabakat.wizard'
    _description = 'Mutabakat Gönderme Sihirbazı'

    partner_ids = fields.Many2many(
        'res.partner',
        string='Tedarikçiler',
        required=True,
    )
    period_start = fields.Date(
        string='Dönem Başlangıç',
        required=True,
        default=lambda self: fields.Date.today().replace(month=1, day=1),
    )
    period_end = fields.Date(
        string='Dönem Bitiş',
        required=True,
        default=fields.Date.today,
    )
    sender_email = fields.Char(
        string='Yanıt Adresi',
        default='aysenur@minddx.ai',
        required=True,
    )
    auto_send = fields.Boolean(
        string='Oluştur ve Hemen Gönder',
        default=False,
        help='İşaretlenirse mutabakat oluşturulur ve e-posta hemen gönderilir.',
    )
    email_message = fields.Text(
        string='E-Posta Mesajı',
        default=lambda self: self.env['mdx.mutabakat']._default_email_message(),
        help='Varsayılan mesaj budur; isterseniz değiştirebilirsiniz.',
    )
    partner_count = fields.Integer(
        string='Seçili Tedarikçi',
        compute='_compute_partner_count',
    )

    @api.depends('partner_ids')
    def _compute_partner_count(self):
        for wiz in self:
            wiz.partner_count = len(wiz.partner_ids)

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        active_ids = self.env.context.get('active_ids', [])
        if active_ids:
            res['partner_ids'] = [(6, 0, active_ids)]
        return res

    def action_create_mutabakat(self):
        """Seçili tedarikçiler için mutabakat kaydı oluştur"""
        self.ensure_one()

        if not self.partner_ids:
            raise UserError(_("En az bir tedarikçi seçmelisiniz."))

        if self.period_start > self.period_end:
            raise UserError(_("Dönem başlangıç tarihi bitiş tarihinden sonra olamaz."))

        mutabakat_records = self.env['mdx.mutabakat']
        skipped = []

        for partner in self.partner_ids:
            if not partner.email:
                skipped.append(partner.name)
                continue

            mutabakat = self.env['mdx.mutabakat'].create({
                'partner_id': partner.id,
                'period_start': self.period_start,
                'period_end': self.period_end,
                'sender_email': self.sender_email,
                'email_message': self.email_message,
                'token': str(uuid.uuid4()),
            })

            # Fatura verilerini hesapla
            try:
                mutabakat.action_compute_lines()
            except UserError:
                # Fatura yoksa boş mutabakat oluştur
                pass

            mutabakat_records |= mutabakat

            # Otomatik gönder
            if self.auto_send and partner.email:
                try:
                    mutabakat.action_send_email()
                except Exception:
                    pass

        # Sonuç mesajı
        message = _("%d mutabakat kaydı oluşturuldu.") % len(mutabakat_records)
        if skipped:
            message += _("\n\n⚠️ E-posta adresi olmayan tedarikçiler atlandı:\n• %s") % "\n• ".join(skipped)

        if len(mutabakat_records) == 1:
            return {
                'type': 'ir.actions.act_window',
                'name': _('Mutabakat'),
                'res_model': 'mdx.mutabakat',
                'res_id': mutabakat_records.id,
                'view_mode': 'form',
                'target': 'current',
            }
        elif len(mutabakat_records) > 1:
            return {
                'type': 'ir.actions.act_window',
                'name': _('Mutabakatlar'),
                'res_model': 'mdx.mutabakat',
                'domain': [('id', 'in', mutabakat_records.ids)],
                'view_mode': 'list,form',
                'target': 'current',
            }
        else:
            raise UserError(_("Hiçbir mutabakat oluşturulamadı.\n\n") + message)
