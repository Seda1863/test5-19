# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.tools.misc import formatLang
import json


class MdxInhAccountJournal(models.Model):
    _inherit = 'account.journal'

    # Portföydeki çekler için hesaplanan alanlar
    portfolio_cheque_count = fields.Integer(
        string='Portföydeki Çek Sayısı',
        compute='_compute_portfolio_cheques',
        store=False,
    )
    portfolio_cheque_amount = fields.Monetary(
        string='Portföydeki Çek Tutarı',
        compute='_compute_portfolio_cheques',
        store=False,
        currency_field='currency_id',
    )

    @api.depends('type')
    def _compute_portfolio_cheques(self):
        """
        Portföydeki çekleri hesapla - Alınan çekler kısmında gösterilecek
        PORTFOYDE durumundaki çekler
        """
        for journal in self:
            if journal.type in ('bank', 'cash'):
                # Portföydeki çekleri bul (inbound_payment_id dolu ve outbound_payment_id boş)
                portfolio_status = self.env['mdx.sabit.kod'].search([
                    ('liste_id.code', '=', 'CEKSTATU'),
                    ('code', '=', 'PORTFOYDE')
                ], limit=1)
                
                if portfolio_status:
                    cheques = self.env['mdx.cheque.leaf'].search([
                        ('company_id', '=', journal.company_id.id),
                        ('cheque_status', '=', portfolio_status.id),
                        ('active', '=', True),
                    ])
                    journal.portfolio_cheque_count = len(cheques)
                    journal.portfolio_cheque_amount = sum(cheques.mapped('amount'))
                else:
                    journal.portfolio_cheque_count = 0
                    journal.portfolio_cheque_amount = 0.0
            else:
                journal.portfolio_cheque_count = 0
                journal.portfolio_cheque_amount = 0.0

    def _fill_bank_cash_dashboard_data(self, dashboard_data):
        """
        Override: Banka ve nakit jurnalleri için dashboard verilerini doldur.
        - Bakiye hesaplamasını gerçek hesap bakiyesi olarak güncelle (Borç - Alacak)
        - Portföydeki çek bilgilerini ekle (sadece çek hesabı olan jurnallerde)
        """
        # Önce parent metodunu çağır
        result = super(MdxInhAccountJournal, self)._fill_bank_cash_dashboard_data(dashboard_data)
        
        bank_cash_journals = self.filtered(lambda journal: journal.type in ('bank', 'cash', 'credit'))
        if not bank_cash_journals:
            return result
        
        # Gerçek hesap bakiyelerini hesapla (Borç - Alacak = balance)
        for journal in bank_cash_journals:
            if not journal.default_account_id:
                continue
                
            currency = journal.currency_id or self.env['res.currency'].browse(journal.company_id.sudo().currency_id.id)
            
            # Hesabın gerçek bakiyesini hesapla
            self._cr.execute("""
                SELECT 
                    COALESCE(SUM(aml.balance), 0) as balance
                FROM account_move_line aml
                JOIN account_move am ON am.id = aml.move_id
                WHERE aml.account_id = %s
                  AND am.state = 'posted'
                  AND aml.company_id IN %s
            """, [journal.default_account_id.id, tuple(self.env.companies.ids)])
            
            result_balance = self._cr.fetchone()
            real_balance = result_balance[0] if result_balance else 0.0
            
            # Dashboard'daki account_balance'ı gerçek bakiye ile değiştir
            dashboard_data[journal.id]['account_balance'] = currency.format(real_balance)
            
            # Diğer işlemler kısmını kaldır (artık bakiyeye dahil)
            dashboard_data[journal.id]['misc_operations_balance'] = None
            dashboard_data[journal.id]['nb_misc_operations'] = 0
        
        # Çek hesap kodları - bu kodlarla başlayan hesaplara sahip jurnallerde çek bilgisi gösterilecek
        CHEQUE_ACCOUNT_CODES = ('101.01', '103.01')  # 101.01.xxx Alınan Çekler, 103.01.xxx Verilen Çekler
        
        # Hangi jurnallerin çek jurnali olduğunu belirle
        cheque_journals = bank_cash_journals.filtered(
            lambda j: j.default_account_id and j.default_account_id.code and
            any(j.default_account_id.code.startswith(code) for code in CHEQUE_ACCOUNT_CODES)
        )
        
        if not cheque_journals:
            # Hiçbir çek jurnali yoksa portföy bilgilerini 0 olarak ayarla
            for journal in bank_cash_journals:
                dashboard_data[journal.id].update({
                    'portfolio_cheque_count': 0,
                    'portfolio_cheque_amount': '',
                    'has_portfolio_cheques': False,
                    'balance_includes_misc': False,
                })
            return result
        
        # Portföydeki çek bilgilerini hesapla - sadece çek jurnalleri için
        portfolio_status = self.env['mdx.sabit.kod'].search([
            ('liste_id.code', '=', 'CEKSTATU'),
            ('code', '=', 'PORTFOYDE')
        ], limit=1)
        
        # Portföydeki çekleri hesap bazında grupla
        portfolio_cheque_data = {}
        if portfolio_status:
            for journal in cheque_journals:
                # Journal'ın hesabına bağlı çekleri bul
                cheques = self.env['mdx.cheque.leaf'].search([
                    ('company_id', '=', journal.company_id.id),
                    ('cheque_status', '=', portfolio_status.id),
                    ('account_id', '=', journal.default_account_id.id),  # Sadece bu hesaba ait çekler
                    ('active', '=', True),
                ])
                
                # Para birimi bazında grupla
                cheque_by_currency = {}
                for cheque in cheques:
                    currency_id = cheque.currency_id.id
                    if currency_id not in cheque_by_currency:
                        cheque_by_currency[currency_id] = {
                            'count': 0,
                            'amount': 0.0,
                            'currency': cheque.currency_id,
                        }
                    cheque_by_currency[currency_id]['count'] += 1
                    cheque_by_currency[currency_id]['amount'] += cheque.amount
                
                portfolio_cheque_data[journal.id] = cheque_by_currency
        
        # Dashboard verilerine portföy çek bilgilerini ekle
        for journal in bank_cash_journals:
            currency = journal.currency_id or self.env['res.currency'].browse(journal.company_id.sudo().currency_id.id)
            
            # Çek jurnali değilse boş değerler ata
            if journal not in cheque_journals:
                dashboard_data[journal.id].update({
                    'portfolio_cheque_count': 0,
                    'portfolio_cheque_amount': '',
                    'has_portfolio_cheques': False,
                })
                continue
            
            # Portföy çek bilgileri
            cheque_data = portfolio_cheque_data.get(journal.id, {})
            total_cheque_count = sum(d['count'] for d in cheque_data.values())
            
            # Aynı para birimindeki çeklerin toplamı
            same_currency_amount = 0.0
            if currency.id in cheque_data:
                same_currency_amount = cheque_data[currency.id]['amount']
            
            # Farklı para birimindeki çekleri dönüştür
            other_currency_amount = 0.0
            for curr_id, data in cheque_data.items():
                if curr_id != currency.id:
                    other_currency_amount += data['currency']._convert(
                        data['amount'],
                        currency,
                        journal.company_id,
                        fields.Date.today(),
                    )
            
            total_cheque_amount = same_currency_amount + other_currency_amount
            
            # Dashboard verisini güncelle
            dashboard_data[journal.id].update({
                'portfolio_cheque_count': total_cheque_count,
                'portfolio_cheque_amount': currency.format(total_cheque_amount) if total_cheque_amount else currency.format(0),
                'has_portfolio_cheques': total_cheque_count > 0,
            })
        
        return result

    def action_open_portfolio_cheques(self):
        """
        Portföydeki çekleri listeleyen action
        """
        self.ensure_one()
        portfolio_status = self.env['mdx.sabit.kod'].search([
            ('liste_id.code', '=', 'CEKSTATU'),
            ('code', '=', 'PORTFOYDE')
        ], limit=1)
        
        return {
            'name': _('Portföydeki Çekler'),
            'type': 'ir.actions.act_window',
            'res_model': 'mdx.cheque.leaf',
            'view_mode': 'list,form',
            'domain': [
                ('company_id', '=', self.company_id.id),
                ('cheque_status', '=', portfolio_status.id if portfolio_status else False),
                ('active', '=', True),
            ],
            'context': {
                'default_company_id': self.company_id.id,
            },
        }

