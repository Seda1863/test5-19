# -*- coding: utf-8 -*-
import json
from datetime import date as date_cls
import calendar
from odoo import _, api, fields, models
from odoo.exceptions import UserError

import logging
_logger = logging.getLogger(__name__)


class MdxYilsonuKapanishPreviewLine(models.TransientModel):
    _name = 'mdx.yilsonu.kapanish.preview.line'
    _description = 'Yıl Sonu Kapanış Ön İzleme Satırı'
    _order = 'account_code'

    wizard_id = fields.Many2one('mdx.yilsonu.kapanish.wizard', ondelete='cascade')
    step = fields.Selection([
        ('yansitma', 'Yansıtma'),
        ('kapanish', 'Kapatma'),
        ('devir', '690 Devir'),
    ], string='Adım')
    account_code = fields.Char(string='Hesap Kodu')
    account_name = fields.Char(string='Hesap Adı')
    label = fields.Char(string='Açıklama')
    source_info = fields.Char(string='Kaynak Bakiye')
    debit = fields.Monetary(string='Borç', currency_field='currency_id')
    credit = fields.Monetary(string='Alacak', currency_field='currency_id')
    currency_id = fields.Many2one(
        'res.currency', default=lambda self: self.env.company.currency_id,
    )


class MdxYilsonuKapanishWizard(models.TransientModel):
    _name = 'mdx.yilsonu.kapanish.wizard'
    _description = 'Dönem Sonu Kapanış Sihirbazı'

    # -------------------------------------------------------------------------
    # Temel alanlar
    # -------------------------------------------------------------------------

    company_id = fields.Many2one(
        'res.company', string='Şirket',
        default=lambda self: self.env.company, required=True,
    )
    journal_id = fields.Many2one(
        'account.journal', string='Yevmiye Defteri',
        domain="[('company_id', '=', company_id), ('type', '=', 'general')]",
        required=True,
    )

    # Dönem seçimi
    preset = fields.Selection([
        ('this_year',    'Bu Yıl'),
        ('last_year',    'Geçen Yıl'),
        ('this_quarter', 'Bu Çeyrek'),
        ('this_month',   'Bu Ay'),
        ('last_month',   'Geçen Ay'),
        ('custom',       'Özel Aralık'),
    ], string='Hızlı Seçim', default='last_year')
    date_from = fields.Date(string='Dönem Başlangıcı', required=True)
    date_to = fields.Date(string='Dönem Bitişi', required=True)
    period_label = fields.Char(compute='_compute_period_label', string='Seçili Dönem')

    # Akış durumu
    state = fields.Selection([
        ('draft',   'Ayarlar'),
        ('preview', 'Ön İzleme'),
        ('done',    'Tamamlandı'),
    ], default='draft', string='Durum')

    # Ön izleme satırları — adım bazında ayrı One2many ile filtreleme
    yansitma_line_ids = fields.One2many(
        'mdx.yilsonu.kapanish.preview.line', 'wizard_id',
        domain=[('step', '=', 'yansitma')],
        string='Yansıtma Satırları',
    )
    kapanish_line_ids = fields.One2many(
        'mdx.yilsonu.kapanish.preview.line', 'wizard_id',
        domain=[('step', '=', 'kapanish')],
        string='Kapatma Satırları',
    )
    devir_line_ids = fields.One2many(
        'mdx.yilsonu.kapanish.preview.line', 'wizard_id',
        domain=[('step', '=', 'devir')],
        string='690 Devir Satırları',
    )

    warning_text = fields.Text(string='Uyarılar', readonly=True)
    created_move_ids = fields.Many2many(
        'account.move',
        'mdx_kapanish_wiz_created_rel', 'wizard_id', 'move_id',
        string='Oluşturulan Yevmiyeler',
    )
    created_move_count = fields.Integer(compute='_compute_created_move_count')

    # Phase 1 yeni alanlar
    move_lines_cache_json = fields.Text(string='Önizleme Önbelleği')
    closing_run_id = fields.Many2one(
        'mdx.yilsonu.kapanish.run', string='Kapanış Kaydı', readonly=True,
    )
    existing_draft_move_ids = fields.Many2many(
        'account.move',
        'mdx_kapanish_wiz_draft_rel', 'wizard_id', 'move_id',
        string='Mevcut Taslak Yevmiyeler',
    )

    # -------------------------------------------------------------------------
    # Default / compute
    # -------------------------------------------------------------------------

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        today = fields.Date.context_today(self)
        year = today.year
        res.update({
            'date_from': date_cls(year - 1, 1, 1),
            'date_to':   date_cls(year - 1, 12, 31),
        })
        return res

    @api.depends('date_from', 'date_to')
    def _compute_period_label(self):
        for rec in self:
            if rec.date_from and rec.date_to:
                df = fields.Date.to_string(rec.date_from)
                dt = fields.Date.to_string(rec.date_to)
                rec.period_label = '%s  \u2192  %s' % (df, dt)
            else:
                rec.period_label = ''

    @api.depends('created_move_ids')
    def _compute_created_move_count(self):
        for rec in self:
            rec.created_move_count = len(rec.created_move_ids)

    @api.onchange('preset')
    def _onchange_preset(self):
        today = fields.Date.context_today(self)
        y, m = today.year, today.month

        if self.preset == 'this_year':
            self.date_from = date_cls(y, 1, 1)
            self.date_to   = date_cls(y, 12, 31)

        elif self.preset == 'last_year':
            self.date_from = date_cls(y - 1, 1, 1)
            self.date_to   = date_cls(y - 1, 12, 31)

        elif self.preset == 'this_quarter':
            q_start = ((m - 1) // 3) * 3 + 1
            q_end   = q_start + 2
            last_day = calendar.monthrange(y, q_end)[1]
            self.date_from = date_cls(y, q_start, 1)
            self.date_to   = date_cls(y, q_end, last_day)

        elif self.preset == 'this_month':
            last_day = calendar.monthrange(y, m)[1]
            self.date_from = date_cls(y, m, 1)
            self.date_to   = date_cls(y, m, last_day)

        elif self.preset == 'last_month':
            if m == 1:
                py, pm = y - 1, 12
            else:
                py, pm = y, m - 1
            last_day = calendar.monthrange(py, pm)[1]
            self.date_from = date_cls(py, pm, 1)
            self.date_to   = date_cls(py, pm, last_day)
        # 'custom' → tarihlere dokunma

    # -------------------------------------------------------------------------
    # Hesap yardımcıları  (önek tabanlı — 63101001 gibi kodlar için)
    # -------------------------------------------------------------------------

    def _get_account_balance(self, code_prefix, company_id):
        """
        Verilen önek (ör. '631') ile başlayan tüm hesapların
        seçili dönemdeki bakiyelerini döner.
        Dönüş: [{'account': obj, 'balance': float, 'debit': float, 'credit': float}]
        """
        accounts = self.env['account.account'].search([
            ('code', '=like', code_prefix + '%'),
            ('company_ids', 'in', [company_id]),
        ])
        result = []
        for account in accounts:
            lines = self.env['account.move.line'].search([
                ('account_id', '=', account.id),
                ('move_id.state', '=', 'posted'),
                ('move_id.date', '>=', self.date_from),
                ('move_id.date', '<=', self.date_to),
                ('company_id', '=', company_id),
            ])
            debit  = sum(lines.mapped('debit'))
            credit = sum(lines.mapped('credit'))
            balance = debit - credit
            if abs(balance) > 0.001:
                result.append({
                    'account': account,
                    'balance': balance,
                    'debit':   debit,
                    'credit':  credit,
                })
        return result

    def _get_first_account_by_prefix(self, prefix, company_id):
        """İlk eşleşen hesabı döner (önek bazlı)."""
        return self.env['account.account'].search([
            ('code', '=like', prefix + '%'),
            ('company_ids', 'in', [company_id]),
        ], order='code', limit=1)

    def _period_ref(self):
        if not self.date_from or not self.date_to:
            return ''
        if self.date_from.year == self.date_to.year:
            return str(self.date_from.year)
        return '%d-%d' % (self.date_from.year, self.date_to.year)

    def _fmt_amount(self, amount):
        """Para birimi sembolü + virgüllü tutar."""
        symbol = self.company_id.currency_id.symbol or ''
        return '%s %s' % (symbol, '{:,.2f}'.format(amount))

    # -------------------------------------------------------------------------
    # Idempotency
    # -------------------------------------------------------------------------

    def _check_existing_closing(self):
        """
        Aynı dönem + şirket için daha önce oluşturulmuş yevmiye var mı kontrol eder.
        Onaylı varsa → UserError (sert engel).
        Taslak varsa → uyarı listesi döner + existing_draft_move_ids set eder.
        """
        period = self._period_ref()
        if not period:
            return []

        existing = self.env['account.move'].search([
            ('mdx_closing_period', '=', period),
            ('mdx_closing_step', '!=', False),
            ('company_id', '=', self.company_id.id),
        ])
        if not existing:
            return []

        posted = existing.filtered(lambda m: m.state == 'posted')
        drafts = existing.filtered(lambda m: m.state == 'draft')

        if posted:
            raise UserError(_(
                '%s dönemi için kapanış yevmiyeleri zaten onaylanmış!\n'
                'Onaylı yevmiye sayısı: %d\n\n'
                'Aynı dönem için yeniden kapanış işlemi yapılamaz.'
            ) % (period, len(posted)))

        warnings = []
        if drafts:
            self.existing_draft_move_ids = [(6, 0, drafts.ids)]
            warnings.append(
                'DİKKAT: %s dönemi için %d adet taslak kapanış yevmiyesi zaten mevcut. '
                'Devam ederseniz ek yevmiyeler oluşturulacaktır.' % (period, len(drafts))
            )
        return warnings

    # -------------------------------------------------------------------------
    # Adım 1 — Gider Yansıtma
    # 760→(Dr 631, Cr 761)  |  770→(Dr 632, Cr 771)  |  780→(Dr 660, Cr 781)
    # -------------------------------------------------------------------------

    YANSITMA_MAP = [
        # (dr_prefix, cr_prefix, src_prefix, açıklama)
        ('631', '761', '760', 'Paz.Sat.Dağ.Gid. Yansıtması'),
        ('632', '771', '770', 'Genel Yönetim Gid. Yansıtması'),
        ('660', '781', '780', 'Finansman Gid. Yansıtması'),
    ]

    def _build_yansitma_lines(self, company_id):
        move_lines, preview_lines, warnings = [], [], []
        currency = self.company_id.currency_id

        for dr_pfx, cr_pfx, src_pfx, adim_label in self.YANSITMA_MAP:
            src_items = self._get_account_balance(src_pfx, company_id)
            total = sum(abs(b['balance']) for b in src_items)
            if total < 0.01:
                continue

            dr_acc = self._get_first_account_by_prefix(dr_pfx, company_id)
            cr_acc = self._get_first_account_by_prefix(cr_pfx, company_id)
            if not dr_acc:
                warnings.append('Hesap bulunamadı — önek: %s (yansıtma borç)' % dr_pfx)
                continue
            if not cr_acc:
                warnings.append('Hesap bulunamadı — önek: %s (yansıtma alacak)' % cr_pfx)
                continue

            source_info = '%sxx bakiyesi = %s' % (src_pfx, self._fmt_amount(total))
            label = '%s — %s' % (self._period_ref(), adim_label)
            move_lines += [
                {'step': 'yansitma', 'account_id': dr_acc.id, 'debit': total, 'credit': 0.0, 'name': label},
                {'step': 'yansitma', 'account_id': cr_acc.id, 'debit': 0.0, 'credit': total, 'name': label},
            ]
            preview_lines += [
                {'step': 'yansitma', 'account_code': dr_acc.code, 'account_name': dr_acc.name,
                 'label': label, 'source_info': source_info,
                 'debit': total, 'credit': 0.0, 'currency_id': currency.id},
                {'step': 'yansitma', 'account_code': cr_acc.code, 'account_name': cr_acc.name,
                 'label': label, 'source_info': source_info,
                 'debit': 0.0, 'credit': total, 'currency_id': currency.id},
            ]
        return move_lines, preview_lines, warnings

    # -------------------------------------------------------------------------
    # Adım 2 — Yansıtma Kapatma
    # Dr 761, Cr 760  |  Dr 771, Cr 770  |  Dr 781, Cr 780
    # -------------------------------------------------------------------------

    KAPANISH_MAP = [
        ('761', '760'),
        ('771', '770'),
        ('781', '780'),
    ]

    def _build_kapanish_lines(self, company_id):
        move_lines, preview_lines, warnings = [], [], []
        currency = self.company_id.currency_id

        for dr_pfx, cr_pfx in self.KAPANISH_MAP:
            dr_items = self._get_account_balance(dr_pfx, company_id)
            total = sum(abs(b['balance']) for b in dr_items)
            if total < 0.01:
                continue

            dr_acc = self._get_first_account_by_prefix(dr_pfx, company_id)
            cr_acc = self._get_first_account_by_prefix(cr_pfx, company_id)
            if not dr_acc:
                warnings.append('Hesap bulunamadı — önek: %s (kapatma borç)' % dr_pfx)
                continue
            if not cr_acc:
                warnings.append('Hesap bulunamadı — önek: %s (kapatma alacak)' % cr_pfx)
                continue

            source_info = '%sxx bakiyesi = %s' % (dr_pfx, self._fmt_amount(total))
            label = '%s — %s/%s Kapatma' % (self._period_ref(), dr_pfx, cr_pfx)
            move_lines += [
                {'step': 'kapanish', 'account_id': dr_acc.id, 'debit': total, 'credit': 0.0, 'name': label},
                {'step': 'kapanish', 'account_id': cr_acc.id, 'debit': 0.0, 'credit': total, 'name': label},
            ]
            preview_lines += [
                {'step': 'kapanish', 'account_code': dr_acc.code, 'account_name': dr_acc.name,
                 'label': label, 'source_info': source_info,
                 'debit': total, 'credit': 0.0, 'currency_id': currency.id},
                {'step': 'kapanish', 'account_code': cr_acc.code, 'account_name': cr_acc.name,
                 'label': label, 'source_info': source_info,
                 'debit': 0.0, 'credit': total, 'currency_id': currency.id},
            ]
        return move_lines, preview_lines, warnings

    # -------------------------------------------------------------------------
    # Adım 3 — 690 Dönem Devri
    # Alacak bakiyeli (gelir) → Dr hesap, Cr 690
    # Borç bakiyeli (gider)   → Dr 690, Cr hesap
    # -------------------------------------------------------------------------

    def _build_690_devir_lines(self, company_id):
        move_lines, preview_lines, warnings = [], [], []
        currency = self.company_id.currency_id

        account_690 = self._get_first_account_by_prefix('690', company_id)
        if not account_690:
            warnings.append('690 hesabı bulunamadı. Lütfen hesap planını kontrol edin.')
            return move_lines, preview_lines, warnings

        processed_ids = set()
        total_690_debit = 0.0
        total_690_credit = 0.0

        for prefix in ['60', '61', '62', '63', '64', '65', '66', '67', '68']:
            for item in self._get_account_balance(prefix, company_id):
                account = item['account']
                # 690 kendisi veya daha önce işlenmiş hesabı atla
                if account.id in processed_ids or account.code.startswith('690'):
                    continue
                processed_ids.add(account.id)

                balance = item['balance']
                if abs(balance) < 0.01:
                    continue

                label = '%s — %s Devir' % (self._period_ref(), account.code)
                amount_str = self._fmt_amount(abs(balance))

                if balance < 0:
                    # Alacak fazlası = gelir → Dr hesap, Cr 690
                    amount = abs(balance)
                    source_info = '%s alacak bak. = %s' % (account.code, amount_str)
                    move_lines.append(
                        {'step': 'devir', 'account_id': account.id,
                         'debit': amount, 'credit': 0.0, 'name': label}
                    )
                    total_690_credit += amount
                    preview_lines.append({
                        'step': 'devir', 'account_code': account.code,
                        'account_name': account.name, 'label': label,
                        'source_info': source_info,
                        'debit': amount, 'credit': 0.0, 'currency_id': currency.id,
                    })
                else:
                    # Borç fazlası = gider → Cr hesap, Dr 690
                    amount = balance
                    source_info = '%s borç bak. = %s' % (account.code, amount_str)
                    move_lines.append(
                        {'step': 'devir', 'account_id': account.id,
                         'debit': 0.0, 'credit': amount, 'name': label}
                    )
                    total_690_debit += amount
                    preview_lines.append({
                        'step': 'devir', 'account_code': account.code,
                        'account_name': account.name, 'label': label,
                        'source_info': source_info,
                        'debit': 0.0, 'credit': amount, 'currency_id': currency.id,
                    })

        # 690 dengeleme satırı
        # Hareket öncesi: Borç = total_690_credit (gelir hesapları Dr)
        #                 Alacak = total_690_debit (gider hesapları Cr)
        # Dengelemek için: 690 Dr/Cr = total_690_debit - total_690_credit
        net_690 = total_690_debit - total_690_credit
        if abs(net_690) > 0.01:
            label_690 = '%s — 690 Net Kâr/Zarar' % self._period_ref()
            source_info_690 = 'Net = Gider(%s) - Gelir(%s) = %s' % (
                '{:,.2f}'.format(total_690_debit),
                '{:,.2f}'.format(total_690_credit),
                self._fmt_amount(abs(net_690)),
            )
            if net_690 > 0:
                # Gider > Gelir → Zarar → Dr 690 (690 borç bakiyeli = zarar)
                move_lines.append(
                    {'step': 'devir', 'account_id': account_690.id,
                     'debit': net_690, 'credit': 0.0, 'name': label_690}
                )
                preview_lines.append({
                    'step': 'devir', 'account_code': account_690.code,
                    'account_name': account_690.name, 'label': label_690,
                    'source_info': source_info_690,
                    'debit': net_690, 'credit': 0.0, 'currency_id': currency.id,
                })
            else:
                # Gelir > Gider → Kâr → Cr 690 (690 alacak bakiyeli = kâr)
                move_lines.append(
                    {'step': 'devir', 'account_id': account_690.id,
                     'debit': 0.0, 'credit': abs(net_690), 'name': label_690}
                )
                preview_lines.append({
                    'step': 'devir', 'account_code': account_690.code,
                    'account_name': account_690.name, 'label': label_690,
                    'source_info': source_info_690,
                    'debit': 0.0, 'credit': abs(net_690), 'currency_id': currency.id,
                })

        return move_lines, preview_lines, warnings

    # -------------------------------------------------------------------------
    # Yevmiye oluşturma
    # -------------------------------------------------------------------------

    def _create_move(self, move_lines, ref, closing_step=False):
        if not move_lines:
            return False
        return self.env['account.move'].create({
            'move_type': 'entry',
            'date': self.date_to,
            'journal_id': self.journal_id.id,
            'company_id': self.company_id.id,
            'ref': ref,
            'mdx_closing_step': closing_step or False,
            'mdx_closing_period': self._period_ref() or False,
            'line_ids': [(0, 0, {
                'account_id': l['account_id'],
                'debit':      l['debit'],
                'credit':     l['credit'],
                'name':       l['name'],
            }) for l in move_lines],
        })

    # -------------------------------------------------------------------------
    # Aksiyonlar
    # -------------------------------------------------------------------------

    def action_preview(self):
        self.ensure_one()
        if not self.date_from or not self.date_to:
            raise UserError(_('Dönem başlangıç ve bitiş tarihlerini giriniz.'))
        if self.date_from > self.date_to:
            raise UserError(_('Dönem başlangıcı, bitiş tarihinden büyük olamaz.'))

        company_id = self.company_id.id
        warnings = []

        # Idempotency: aynı dönem için önceki kapanış var mı?
        existing_warns = self._check_existing_closing()
        warnings.extend(existing_warns)

        all_move_lines = []
        all_preview = []

        for builder, step_label in [
            (self._build_yansitma_lines, 'Yansıtma'),
            (self._build_kapanish_lines, 'Kapatma'),
            (self._build_690_devir_lines, '690 Devir'),
        ]:
            try:
                mlines, plines, bwarns = builder(company_id)
                all_move_lines.extend(mlines)
                all_preview.extend(plines)
                warnings.extend(['[%s] %s' % (step_label, w) for w in bwarns])
            except Exception as e:
                warnings.append('[%s] Beklenmedik hata: %s' % (step_label, str(e)))

        # Snapshot: tüm move_lines → JSON cache (step dahil, create sırasında kullanılır)
        self.move_lines_cache_json = json.dumps(all_move_lines)

        # Mevcut satırları sil, yenilerini oluştur
        self.env['mdx.yilsonu.kapanish.preview.line'].search(
            [('wizard_id', '=', self.id)]
        ).unlink()
        if all_preview:
            self.env['mdx.yilsonu.kapanish.preview.line'].create(
                [dict(v, wizard_id=self.id) for v in all_preview]
            )

        self.warning_text = '\n'.join(warnings) if warnings else False
        self.state = 'preview'

        return {
            'type': 'ir.actions.act_window',
            'res_model': 'mdx.yilsonu.kapanish.wizard',
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def action_create_entries(self):
        self.ensure_one()

        # State guard: create sadece preview'dan sonra yapılabilir
        if self.state != 'preview':
            raise UserError(_('Önce ön izleme yapmanız gerekmektedir.'))

        # JSON cache'den satırları al (preview→create tutarlılığı için)
        if not self.move_lines_cache_json:
            raise UserError(_(
                'Ön izleme önbelleği bulunamadı. '
                'Lütfen önce "Ön İzleme Yap" butonunu kullanın.'
            ))

        cached_lines = json.loads(self.move_lines_cache_json)

        # Step bazında grupla
        step_map = {}
        for line in cached_lines:
            step = line.get('step', 'yansitma')
            step_map.setdefault(step, []).append(line)

        STEP_CONFIG = [
            ('yansitma', 'Yıl Sonu Yansıtma'),
            ('kapanish', 'Yıl Sonu Kapatma'),
            ('devir',    'Yıl Sonu 690 Devir'),
        ]

        created_moves = self.env['account.move']
        step_done = {}

        for step_code, ref_suffix in STEP_CONFIG:
            move_lines = step_map.get(step_code, [])
            if move_lines:
                move = self._create_move(
                    move_lines,
                    '%s — %s' % (self._period_ref(), ref_suffix),
                    closing_step=step_code,
                )
                if move:
                    created_moves |= move
                    step_done[step_code] = True

        if not created_moves:
            raise UserError(_(
                'Oluşturulacak kayıt bulunamadı.\n'
                'Seçili dönemde (%s) onaylı bakiye verisi olmayabilir.'
            ) % self.period_label)

        # Kapanış kaydı oluştur (iz bırak)
        run = self.env['mdx.yilsonu.kapanish.run'].create({
            'company_id': self.company_id.id,
            'period_label': self.period_label,
            'date_from': self.date_from,
            'date_to': self.date_to,
            'journal_id': self.journal_id.id,
            'step_yansitma_done': bool(step_done.get('yansitma')),
            'step_kapanish_done': bool(step_done.get('kapanish')),
            'step_devir_done': bool(step_done.get('devir')),
            'move_ids': [(6, 0, created_moves.ids)],
            'warnings': self.warning_text,
        })

        self.created_move_ids = [(6, 0, created_moves.ids)]
        self.closing_run_id = run.id
        self.state = 'done'

        return {
            'type': 'ir.actions.act_window',
            'res_model': 'mdx.yilsonu.kapanish.wizard',
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def action_view_created_moves(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Oluşturulan Yevmiyeler'),
            'res_model': 'account.move',
            'view_mode': 'list,form',
            'domain': [('id', 'in', self.created_move_ids.ids)],
            'target': 'current',
        }

    def action_view_closing_run(self):
        self.ensure_one()
        if not self.closing_run_id:
            raise UserError(_('Kapanış kaydı bulunamadı.'))
        return {
            'type': 'ir.actions.act_window',
            'name': _('Kapanış Kaydı'),
            'res_model': 'mdx.yilsonu.kapanish.run',
            'res_id': self.closing_run_id.id,
            'view_mode': 'form',
            'target': 'current',
        }
