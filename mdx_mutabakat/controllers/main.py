# -*- coding: utf-8 -*-
from odoo import http, fields, _
from odoo.http import request
import logging

_logger = logging.getLogger(__name__)


class MutabakatController(http.Controller):

    @http.route('/mutabakat/confirm/<string:token>', type='http', auth='public', website=True, csrf=False)
    def mutabakat_confirm_page(self, token, **kwargs):
        """Online onay sayfası — dokümani gör ve onayla."""
        _logger.info("Mutabakat confirm sayfası açılıyor: token=%s", token)
        mutabakat = request.env['mdx.mutabakat'].sudo().search([('token', '=', token)], limit=1)
        _logger.info("Mutabakat confirm sonuç: token=%s, found=%s", token, bool(mutabakat))
        if not mutabakat:
            return request.render('mdx_mutabakat.response_page', {
                'title': 'Hata',
                'message': 'Bu mutabakat bağlantısı geçersiz veya süresi dolmuş.',
                'success': False,
            })

        # Süresi geçti mi kontrol
        if mutabakat.response_due_date and fields.Date.today() > mutabakat.response_due_date and mutabakat.state in ('sent', 'opened'):
            mutabakat.write({'state': 'expired'})

        # İlk açılışta opened yap
        if mutabakat.state == 'sent':
            mutabakat.write({'state': 'opened', 'opened_date': fields.Datetime.now()})
        elif mutabakat.state == 'draft' and not mutabakat.opened_date:
            mutabakat.write({'opened_date': fields.Datetime.now()})

        if mutabakat.state == 'expired':
            return request.render('mdx_mutabakat.response_page', {
                'title': 'Süresi Geçti',
                'message': f'Bu mutabakat bağlantısının yanıt süresi dolmuştur ({mutabakat.name}).',
                'success': False,
                'mutabakat': mutabakat,
            })

        if mutabakat.state in ('agreed', 'disagreed'):
            return request.render('mdx_mutabakat.response_page', {
                'title': 'Zaten Yanıtlandı',
                'message': f'Bu mutabakat ({mutabakat.name}) daha önce yanıtlanmış.',
                'success': False,
                'mutabakat': mutabakat,
            })

        return request.render('mdx_mutabakat.confirmation_page', {'mutabakat': mutabakat})

    @http.route('/mutabakat/response/<string:token>/<string:action>',
                type='http', auth='public', website=True, csrf=False)
    def mutabakat_response(self, token, action, **kwargs):
        """Tedarikçinin e-postadaki butona tıklamasını yakala"""
        _logger.info("Mutabakat response: token=%s, action=%s", token, action)
        mutabakat = request.env['mdx.mutabakat'].sudo().search([
            ('token', '=', token),
        ], limit=1)
        _logger.info("Mutabakat response sonuç: token=%s, found=%s", token, bool(mutabakat))

        if not mutabakat:
            return request.render('mdx_mutabakat.response_page', {
                'title': 'Hata',
                'message': 'Bu mutabakat bağlantısı geçersiz veya süresi dolmuş.',
                'success': False,
            })

        # Süresi geçti mi kontrol
        if mutabakat.response_due_date and fields.Date.today() > mutabakat.response_due_date and mutabakat.state in ('sent', 'opened'):
            mutabakat.write({'state': 'expired'})

        if mutabakat.state == 'expired':
            return request.render('mdx_mutabakat.response_page', {
                'title': 'Süresi Geçti',
                'message': f'Bu mutabakat bağlantısının yanıt süresi dolmuştur ({mutabakat.name}).',
                'success': False,
                'mutabakat': mutabakat,
            })

        if mutabakat.state in ('agreed', 'disagreed'):
            return request.render('mdx_mutabakat.response_page', {
                'title': 'Zaten Yanıtlandı',
                'message': f'Bu mutabakat ({mutabakat.name}) daha önce yanıtlanmış.',
                'success': False,
                'mutabakat': mutabakat,
            })

        if mutabakat.state not in ('sent', 'opened', 'draft'):
            return request.render('mdx_mutabakat.response_page', {
                'title': 'Geçersiz Durum',
                'message': f'Bu mutabakat bu durumda yanıt kabul etmiyor.',
                'success': False,
                'mutabakat': mutabakat,
            })

        # Yanıtı kaydet
        if action == 'agree':
            mutabakat.write({
                'state': 'agreed',
                'opened_date': mutabakat.opened_date or fields.Datetime.now(),
                'response_date': fields.Datetime.now(),
                'response_note': 'Tedarikçi e-posta üzerinden "Mutabıkız" yanıtı verdi.',
            })
            title = '✅ Mutabıkız'
            message = 'Yanıtınız başarıyla kaydedildi. Teşekkür ederiz!'

        elif action == 'disagree':
            mutabakat.write({
                'state': 'disagreed',
                'opened_date': mutabakat.opened_date or fields.Datetime.now(),
                'response_date': fields.Datetime.now(),
                'response_note': 'Tedarikçi e-posta üzerinden "Mutabık Değiliz" yanıtı verdi.',
            })
            title = '❌ Mutabık Değiliz'
            message = 'Yanıtınız kaydedildi. En kısa sürede sizinle iletişime geçilecektir.'

        else:
            return request.render('mdx_mutabakat.response_page', {
                'title': 'Geçersiz İşlem',
                'message': 'Geçersiz bir işlem denendi.',
                'success': False,
            })

        # Chatter mesajı
        mutabakat.message_post(
            body=_(
                "<b>Tedarikçi Yanıtı:</b> %s<br>"
                "<b>Tarih:</b> %s<br>"
                "<b>Tedarikçi:</b> %s"
            ) % (title, fields.Datetime.now().strftime('%d.%m.%Y %H:%M'), mutabakat.partner_id.name),
            message_type='notification',
            subtype_xmlid='mail.mt_note',
        )

        # Gönderene bildirim
        try:
            self._notify_sender(mutabakat, action)
        except Exception as e:
            _logger.warning("Gönderene bildirim gönderilemedi: %s", str(e))

        return request.render('mdx_mutabakat.response_page', {
            'title': title,
            'message': message,
            'success': True,
            'mutabakat': mutabakat,
        })

    def _notify_sender(self, mutabakat, action):
        """Gönderen kullanıcıya bildirim gönder"""
        status = "✅ Mutabıkız" if action == 'agree' else "❌ Mutabık Değiliz"

        if mutabakat.sender_id:
            mutabakat.activity_schedule(
                'mail.mail_activity_data_todo',
                user_id=mutabakat.sender_id.id,
                summary=f'Mutabakat Yanıtı: {mutabakat.partner_id.name} — {status}',
                note=f'{mutabakat.name} numaralı mutabakat için {mutabakat.partner_id.name} yanıt verdi: {status}',
            )

        if mutabakat.sender_email:
            mail_values = {
                'subject': f'Mutabakat Yanıtı: {mutabakat.partner_id.name} — {status}',
                'body_html': f"""
                    <div style="font-family: Arial, sans-serif; padding: 20px;">
                        <h2>Mutabakat Yanıtı Geldi</h2>
                        <table style="border-collapse: collapse; width: 100%;">
                            <tr><td style="padding:8px; border:1px solid #ddd;"><strong>Mutabakat No</strong></td>
                                <td style="padding:8px; border:1px solid #ddd;">{mutabakat.name}</td></tr>
                            <tr><td style="padding:8px; border:1px solid #ddd;"><strong>Tedarikçi</strong></td>
                                <td style="padding:8px; border:1px solid #ddd;">{mutabakat.partner_id.name}</td></tr>
                            <tr><td style="padding:8px; border:1px solid #ddd;"><strong>Yanıt</strong></td>
                                <td style="padding:8px; border:1px solid #ddd;"><strong>{status}</strong></td></tr>
                            <tr><td style="padding:8px; border:1px solid #ddd;"><strong>Tarih</strong></td>
                                <td style="padding:8px; border:1px solid #ddd;">{fields.Datetime.now().strftime('%d.%m.%Y %H:%M')}</td></tr>
                        </table>
                    </div>
                """,
                'email_to': mutabakat.sender_email,
                'email_from': mutabakat.company_id.email or 'noreply@minddx.ai',
                'auto_delete': True,
            }
            request.env['mail.mail'].sudo().create(mail_values).send()
