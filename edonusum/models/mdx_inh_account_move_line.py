from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
from odoo import Command

class MdxInhAccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    @api.constrains('account_id', 'partner_id')
    def _check_partner_required_for_120_320(self):
        for line in self:
            if line.account_id and line.account_id.code:
                code = line.account_id.code.strip()
                if (code.startswith('120') or code.startswith('320')) and not line.partner_id:
                    raise ValidationError(_(
                        "%(account)s hesabı için İş Ortağı (Partner) seçimi zorunludur.\n"
                        "Yevmiye: %(move)s",
                        account=f"{line.account_id.code} - {line.account_id.name}",
                        move=line.move_id.name or 'Yeni',
                    ))

    entry_sequence_no = fields.Integer(string='Yevmiye Sıra No', required=False, copy=False, compute='_compute_entry_sequence_no', store=True)
    line_sequence_no = fields.Integer(string='Satır Sıra No', required=False, copy=False, store=True)

    line_description = fields.Text(string='Açıklama', required=False, copy=False, store=True)

    istisna_kodu = fields.Many2one('mdx.sabit.kod', string='İstisna Kodu', domain=[('liste_tipi_id.code', '=', 'ISTISNA')], compute='_compute_codes', store=True, readonly=False)
    tevkifat_kodu = fields.Many2one('mdx.sabit.kod', string='Tevkifat Kodu', domain=[('liste_tipi_id.code', '=', 'TEVKIFAT')], compute='_compute_codes', store=True, readonly=False)
    ihrac_kayit_kodu = fields.Many2one('mdx.sabit.kod', string='İhraç Kayıt Kodu', domain=[('liste_tipi_id.code', '=', 'IHRACKAYITLI')], compute='_compute_codes', store=True, readonly=False)
    gtip_kodu = fields.Char(string='GTIP Kodu', store=True)
    product_template_open_url = fields.Char(string='Urunu Ac', compute='_compute_product_template_open_url')
    ozel_matrah_kodu = fields.Many2one('mdx.sabit.kod', string='Özel Matrah Kodu', domain=[('liste_tipi_id.code', '=', 'OZELMATRAH')], compute='_compute_codes', store=True, readonly=False)
    vergi_kodu = fields.Many2one('mdx.sabit.kod', string='Vergi Kodu', domain=[('liste_tipi_id.code', '=', 'VERGI')], store=True, readonly=False)
    active = fields.Boolean(string='Aktif', default=True)

    gelen_fatura_line_id = fields.Many2one('mdx.gelen.fatura.line', string='Gelen Fatura Satırı', store=True)

    amount_residual_currency = fields.Monetary(
        string='Residual Amount in Currency',
        compute='_compute_amount_residual', store=True,
        aggregator='sum',
        help="The residual amount on a journal item expressed in its currency (possibly not the "
             "company currency).",
    )

    display_move_identifier = fields.Char(
        string="Fiş Numarası",
        compute='_compute_display_move_identifier',
        store=True  # Pivot görünümü için saklamaya gerek yok
    )

    @api.depends('move_id.fatura_no', 'move_id.name')
    def _compute_display_move_identifier(self):
        for line in self:
            # Fatura numarası varsa onu kullan, yoksa yevmiye numarasını (move_id.name) kullan
            line.display_move_identifier = line.move_id.fatura_no or line.move_id.name

    @api.depends('product_id')
    def _compute_product_template_open_url(self):
        for record in self:
            if record.product_id and record.product_id.product_tmpl_id:
                record.product_template_open_url = '/web#id=%s&model=product.template&view_type=form' % record.product_id.product_tmpl_id.id
            else:
                record.product_template_open_url = False

    @api.depends('partner_id', 'move_id.fatura_tipi_id')
    def _compute_codes(self):
        for record in self:
            if record.partner_id:
                if record.partner_id.parent_id:
                    if not record.istisna_kodu and record.move_id.fatura_tipi_id.code == 'ISTISNA':
                        record.istisna_kodu = record.partner_id.parent_id.istisna_kodu.id if record.partner_id.parent_id.istisna_kodu else False
                        # İstisna kodu set edildiğinde vergileri de %0 yap
                        record._set_zero_tax_for_istisna()
                    if not record.tevkifat_kodu and record.move_id.fatura_tipi_id.code == 'TEVKIFAT':
                        record.tevkifat_kodu = record.partner_id.parent_id.tevkifat_kodu.id if record.partner_id.parent_id.tevkifat_kodu else False
                    if not record.ihrac_kayit_kodu and record.move_id.fatura_tipi_id.code == 'IHRACKAYITLI':
                        record.ihrac_kayit_kodu = record.partner_id.parent_id.ihrac_kayit_kodu.id if record.partner_id.parent_id.ihrac_kayit_kodu else False
                    if not record.ozel_matrah_kodu and record.move_id.fatura_tipi_id.code == 'OZELMATRAH':
                        record.ozel_matrah_kodu = record.partner_id.parent_id.ozel_matrah_kodu.id if record.partner_id.parent_id.ozel_matrah_kodu else False
                    # if not record.vergi_kodu and record.move_id.fatura_tipi_id.code == 'VERGI':
                    #     # record.vergi_kodu = record.partner_id.parent_id.vergi_kodu.id if record.partner_id.parent_id.vergi_kodu else False
                    #     self._compute_vergi_kodu()
                else:
                    if not record.istisna_kodu and record.move_id.fatura_tipi_id.code == 'ISTISNA':
                        record.istisna_kodu = record.partner_id.istisna_kodu.id if record.partner_id.istisna_kodu else False
                        # İstisna kodu set edildiğinde vergileri de %0 yap
                        record._set_zero_tax_for_istisna()
                    if not record.tevkifat_kodu and record.move_id.fatura_tipi_id.code == 'TEVKIFAT':
                        record.tevkifat_kodu = record.partner_id.tevkifat_kodu.id if record.partner_id.tevkifat_kodu else False
                    if not record.ihrac_kayit_kodu and record.move_id.fatura_tipi_id.code == 'IHRACKAYITLI':
                        record.ihrac_kayit_kodu = record.partner_id.ihrac_kayit_kodu.id if record.partner_id.ihrac_kayit_kodu else False
                    if not record.ozel_matrah_kodu and record.move_id.fatura_tipi_id.code == 'OZELMATRAH':
                        record.ozel_matrah_kodu = record.partner_id.ozel_matrah_kodu.id if record.partner_id.ozel_matrah_kodu else False
                    # if not record.vergi_kodu and record.move_id.fatura_tipi_id.code == 'VERGI':
                    #     # record.vergi_kodu = record.partner_id.vergi_kodu.id if record.partner_id.vergi_kodu else False
                    #     self._compute_vergi_kodu()

    @api.depends('move_id')
    def _compute_entry_sequence_no(self):
        for record in self:
            if record.move_id:
                record.entry_sequence_no = record.move_id.entry_sequence_no

    @api.onchange('product_id', 'istisna_kodu')
    def _onchange_product_id_gtip(self):
        warning = False
        for record in self:
            if not record.product_id:
                record.gtip_kodu = False
                record.product_template_open_url = False
                continue

            hs_code = record.product_id.product_tmpl_id.hs_code or record.product_id.hs_code
            record.gtip_kodu = hs_code or False
            record.product_template_open_url = '/web#id=%s&model=product.template&view_type=form' % record.product_id.product_tmpl_id.id

            # Istisna kodu henuz set edilmemisse:
            # 1) Oncelikle urun kartindaki istisna_kodu'na bak
            # 2) Sonra urunun tedarikci partnerlarinin e-donusum istisna_kodu'na bak
            if not record.istisna_kodu:
                # 1. Urun kartindaki istisna_kodu
                tmpl = record.product_id.product_tmpl_id
                if hasattr(tmpl, 'istisna_kodu') and tmpl.istisna_kodu:
                    record.istisna_kodu = tmpl.istisna_kodu.id
                else:
                    # 2. Urunun tedarikci listesinden (satinalma -> tedarikci -> e-donusum -> istisna_kodu)
                    for seller in tmpl.seller_ids:
                        partner = seller.partner_id
                        # Ana partner veya commercial partner'dan bak
                        p = partner.commercial_partner_id if partner.commercial_partner_id else partner
                        if hasattr(p, 'istisna_kodu') and p.istisna_kodu:
                            record.istisna_kodu = p.istisna_kodu.id
                            break

            if not hs_code and record.istisna_kodu:
                warning = {
                    'title': _('GTIP Eksik'),
                    'message': _(
                        "Istisna kodu secili satirda HS Code/GTIP zorunludur. "
                        "Urun kartinda HS Code/GTIP alanini doldurun."
                    ),
                }

        # Istisna kodu varsa vergileri %0 yap (direkt otomatik)
        self._onchange_set_zero_kdv_for_istisna()

        if warning:
            return {'warning': warning}

    def action_open_product_template_for_gtip(self):
        self.ensure_one()
        if not self.product_id:
            raise UserError(_("Once bir urun secin."))

        return {
            'type': 'ir.actions.act_window',
            'name': _('Urun'),
            'res_model': 'product.template',
            'res_id': self.product_id.product_tmpl_id.id,
            'view_mode': 'form',
            'target': 'new',
        }

    @api.onchange('partner_id')
    def _onchange_partner_id(self):
        if self.move_id.partner_id:
            if self.move_id.partner_id.parent_id and ( self.move_id.partner_id.type == 'delivery' or self.move_id.partner_id.type == 'invoice' ):
                self.istisna_kodu = self.move_id.partner_id.parent_id.istisna_kodu.id if self.move_id.partner_id.parent_id.istisna_kodu else False
                self.tevkifat_kodu = self.move_id.partner_id.parent_id.tevkifat_kodu.id if self.move_id.partner_id.parent_id.tevkifat_kodu else False
                self.ihrac_kayit_kodu = self.move_id.partner_id.parent_id.ihrac_kayit_kodu.id if self.move_id.partner_id.parent_id.ihrac_kayit_kodu else False
                self.ozel_matrah_kodu = self.move_id.partner_id.parent_id.ozel_matrah_kodu.id if self.move_id.partner_id.parent_id.ozel_matrah_kodu else False
                # self.vergi_kodu = self.move_id.partner_id.parent_id.vergi_kodu.id if self.move_id.partner_id.parent_id.vergi_kodu else False
            else:    
                self.istisna_kodu = self.move_id.partner_id.istisna_kodu.id if self.move_id.partner_id.istisna_kodu else False
                self.tevkifat_kodu = self.move_id.partner_id.tevkifat_kodu.id if self.move_id.partner_id.tevkifat_kodu else False
                self.ihrac_kayit_kodu = self.move_id.partner_id.ihrac_kayit_kodu.id if self.move_id.partner_id.ihrac_kayit_kodu else False
                self.ozel_matrah_kodu = self.move_id.partner_id.ozel_matrah_kodu.id if self.move_id.partner_id.ozel_matrah_kodu else False
                # self.vergi_kodu = self.move_id.partner_id.vergi_kodu.id if self.move_id.partner_id.vergi_kodu else False
            self._compute_vergi_kodu()
            self._onchange_set_zero_kdv_for_istisna()

    @api.model
    def _get_default_kdv_vergi_kodu(self):
        return self.env['mdx.sabit.kod'].search([
            ('liste_tipi_id.code', '=', 'VERGI'),
            ('efinans_kod', '=', '0015'),
        ], limit=1)

    @api.model
    def _get_default_zero_sale_kdv_tax(self, company):
        company = company or self.env.company
        # Oncelikle '0%' iceren isimde satis vergisi ara (ornegin '0% EX')
        tax = self.env['account.tax'].search([
            ('type_tax_use', '=', 'sale'),
            ('amount', '=', 0.0),
            ('name', 'ilike', '0%'),
            ('company_id', 'in', [company.id, False]),
        ], order='sequence asc', limit=1)
        if not tax:
            # KDV veya VAT gruplu %0 vergi ara
            tax = self.env['account.tax'].search([
                ('type_tax_use', '=', 'sale'),
                ('amount', '=', 0.0),
                ('company_id', 'in', [company.id, False]),
                '|',
                ('tax_group_id.name', 'ilike', 'KDV'),
                ('tax_group_id.name', 'ilike', 'VAT'),
            ], limit=1)
        if not tax:
            # Herhangi bir %0 vergisi al (tum tipler, sifir tutar)
            tax = self.env['account.tax'].search([
                ('amount', '=', 0.0),
                ('company_id', 'in', [company.id, False]),
                ('active', '=', True),
            ], order='sequence asc', limit=1)
        return tax

    @api.depends('product_id', 'product_uom_id', 'istisna_kodu')
    def _compute_tax_ids(self):
        """
        Odoo 18'de tax_ids computed stored field'dir.
        Orijinal depends: product_id, product_uom_id
        Biz istisna_kodu'yu da ekliyoruz.
        Super() cagirdiktan sonra (urunun default vergilerini set eder, mesela %20),
        istisna_kodu varsa zorla %0 vergiyle ezeriz.
        """
        # Once Odoo'nun kendi hesaplamasini yap (urunun default vergilerini set eder)
        super()._compute_tax_ids()
        # Sonra istisna kodu olan satirlarda %0'a override et
        for line in self:
            if line.display_type in ('line_section', 'line_note', 'payment_term'):
                continue
            if not line.istisna_kodu:
                continue
            zero_tax = line._get_default_zero_sale_kdv_tax(
                line.company_id or line.move_id.company_id
            )
            if zero_tax:
                line.tax_ids = [Command.set([zero_tax.id])]

    def _get_computed_taxes(self):
        """
        Override: Istisna kodu varsa urunun default vergisi yerine %0 vergi don.
        Bu metod _compute_tax_ids icinden cagriliyor.
        Boylece Odoo'nun kendi hesaplamasi bile %0 doner.
        """
        self.ensure_one()
        if self.istisna_kodu and self.display_type not in ('line_section', 'line_note', 'payment_term'):
            zero_tax = self._get_default_zero_sale_kdv_tax(
                self.company_id or self.move_id.company_id
            )
            if zero_tax:
                return zero_tax
        return super()._get_computed_taxes()

    def _should_force_zero_kdv_for_istisna(self):
        self.ensure_one()
        # Istisna kodu set edilmisse HER ZAMAN (fatura tipi ne olursa olsun) vergiler %0 olmali.
        # is_invoice() kontrolu kaldirildi - yeni kayit/taslakta False donuyordu.
        return bool(
            not self.display_type
            and self.istisna_kodu
        )

    def _set_zero_tax_for_istisna(self):
        """İstisna kodu varsa vergileri %0 KDV yap - compute ve onchange'den çağrılır"""
        self.ensure_one()
        if not self._should_force_zero_kdv_for_istisna():
            return
        
        zero_tax = self._get_default_zero_sale_kdv_tax(self.company_id or self.move_id.company_id)
        if zero_tax:
            self.tax_ids = [Command.set([zero_tax.id])]

    @api.onchange('istisna_kodu')
    def _onchange_set_zero_kdv_for_istisna(self):
        warning = False
        for line in self:
            if not line._should_force_zero_kdv_for_istisna():
                continue

            zero_tax = line._get_default_zero_sale_kdv_tax(line.company_id or line.move_id.company_id)
            if not zero_tax:
                warning = {
                    'title': _('KDV Ayari Eksik'),
                    'message': _(
                        "Istisna kodu secili satirlarda varsayilan %0 satis KDV vergisi bulunamadi. "
                        "Lutfen %0 satis KDV vergisi tanimlayin."
                    ),
                }
                continue

            # İstisna kodu varsa sadece Vergiler (tax_ids) alanını %0 KDV yap
            # Vergi Kodu (vergi_kodu) alanıyla alakası yok
            line.tax_ids = [Command.set([zero_tax.id])]

        if warning:
            return {'warning': warning}

    def _enforce_zero_kdv_for_istisna(self):
        for line in self:
            if not line._should_force_zero_kdv_for_istisna():
                continue

            zero_tax = line._get_default_zero_sale_kdv_tax(line.company_id or line.move_id.company_id)
            if not zero_tax:
                raise ValidationError(
                    _(
                        "Istisna kodu secili satis satirlarinda %0 KDV zorunludur. "
                        "Lutfen once %0 satis KDV vergisi tanimlayin."
                    )
                )

            # Istisna kodu varsa Vergiler (tax_ids) alanini zorla %0 yap
            if set(line.tax_ids.ids) != {zero_tax.id}:
                super(MdxInhAccountMoveLine, line.with_context(
                    skip_istisna_zero_tax_enforce=True,
                )).write({
                    'tax_ids': [Command.set([zero_tax.id])],
                })

    # GTIP zorunluluk kontrolu artik action_post'ta yapiliyor.
    # Taslak asamasinda GTIP olmadan kaydedilebilir, sadece onaylama sirasinda kontrol edilir.
    # @api.constrains kaldirildi - cunku taslak kayitlari blokluyordu.

    @api.onchange('gtip_kodu')
    def _onchange_gtip_kodu_required(self):
        """GTIP format kontrolü: 12 haneli, sadece rakam"""
        for line in self:
            if line.gtip_kodu:
                # Boşlukları temizle
                cleaned = line.gtip_kodu.strip().replace(' ', '').replace('-', '').replace('.', '')
                line.gtip_kodu = cleaned

                # Sadece rakamlardan oluşmalı
                if not cleaned.isdigit():
                    return {'warning': {
                        'title': _('GTIP Kodu Hatalı'),
                        'message': _(
                            "GTIP kodu sadece rakamlardan oluşmalıdır. "
                            "Harf veya özel karakter içeremez."
                        ),
                    }}

                # 12 haneli olmalı
                if len(cleaned) != 12:
                    return {'warning': {
                        'title': _('GTIP Kodu Hatalı'),
                        'message': _(
                            "GTIP kodu tam olarak 12 haneli olmalıdır. "
                            "Girdiğiniz kod %d haneli."
                        ) % len(cleaned),
                    }}

            # İstisna kodu varsa GTIP zorunlu
            elif line.istisna_kodu and line.product_id:
                hs_code = line.product_id.product_tmpl_id.hs_code or line.product_id.hs_code
                if not hs_code:
                    return {'warning': {
                        'title': _('GTIP Zorunlu'),
                        'message': _(
                            "Istisna kodu secili satirda GTIP Kodu zorunludur. "
                            "GTIP kodunu silmeniz durumunda fatura kaydedilemez."
                        ),
                    }}

    @api.constrains('gtip_kodu', 'istisna_kodu')
    def _check_gtip_kodu_format(self):
        """GTIP kodu format kontrolü + istisna varsa zorunluluk kontrolü"""
        for line in self:
            # Fatura satırı değilse atla
            if line.display_type and line.display_type != 'product':
                continue
            if not line.move_id or not line.move_id.is_invoice(include_receipts=True):
                continue

            # İstisna kodu varsa GTIP zorunlu
            if line.istisna_kodu and not line.gtip_kodu:
                raise ValidationError(_(
                    "İstisna kodu seçili satırda GTIP Kodu zorunludur (12 haneli rakam). "
                    "Lütfen fatura satırında GTIP kodunu girin."
                ))

            # GTIP format kontrolü
            if line.gtip_kodu:
                cleaned = line.gtip_kodu.strip().replace(' ', '').replace('-', '').replace('.', '')
                if not cleaned.isdigit():
                    raise ValidationError(_(
                        "GTIP kodu sadece rakamlardan oluşmalıdır. "
                        "Hatalı değer: '%s'"
                    ) % line.gtip_kodu)
                if len(cleaned) != 12:
                    raise ValidationError(_(
                        "GTIP kodu tam olarak 12 haneli olmalıdır. "
                        "Girdiğiniz kod %d haneli: '%s'"
                    ) % (len(cleaned), line.gtip_kodu))

    @api.model
    def _is_invoice_move_type(self, move_type):
        return move_type in ('out_invoice', 'out_refund', 'in_invoice', 'in_refund', 'out_receipt', 'in_receipt')

    @api.model
    def _validate_hs_code_in_vals(self, vals, current_line=None):
        if self.env.context.get('skip_gtip_validation'):
            return

        product = False
        if vals.get('product_id'):
            product = self.env['product.product'].browse(vals['product_id'])
        elif current_line:
            product = current_line.product_id

        if not product:
            return

        istisna_kodu = vals.get('istisna_kodu') if 'istisna_kodu' in vals else (
            current_line.istisna_kodu.id if current_line and current_line.istisna_kodu else False
        )
        if not istisna_kodu:
            return

        hs_code = product.product_tmpl_id.hs_code or product.hs_code
        gtip_kodu = vals.get('gtip_kodu') if 'gtip_kodu' in vals else (current_line.gtip_kodu if current_line else False)
        if hs_code or gtip_kodu:
            return

        move_type = vals.get('move_type')
        if not move_type and vals.get('move_id'):
            move_type = self.env['account.move'].browse(vals['move_id']).move_type
        if not move_type and current_line and current_line.move_id:
            move_type = current_line.move_id.move_type
        if not move_type:
            move_type = self.env.context.get('default_move_type')

        if self._is_invoice_move_type(move_type):
            raise ValidationError(
                _("Istisna kodu secili satirda GTIP Kodu zorunludur. Lütfen urun kartinda HS Code/GTIP alanini doldurun.")
            )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            # Partner kodları
            if 'partner_id' in vals:
                partner = self.env['res.partner'].browse(vals['partner_id'])
                if partner:
                    if partner.parent_id:
                        vals.update(self._get_partner_codes(partner.parent_id, vals))
                    else:
                        vals.update(self._get_partner_codes(partner, vals))

            # İade faturası satırı için account_id override
            move_type = vals.get('move_type') or (self.env['account.move'].browse(vals.get('move_id')).move_type if vals.get('move_id') else None)
            if move_type == 'out_refund' and vals.get('product_id'):
                product = self.env['product.product'].browse(vals['product_id']).with_company(vals.get('company_id'))
                company = self.env['res.company'].browse(vals.get('company_id')) if vals.get('company_id') else self.env.company
                account = (
                    getattr(product, 'l10n_tr_default_sales_return_account_id', False)
                    or getattr(product.categ_id, 'l10n_tr_default_sales_return_account_id', False)
                    or getattr(company, 'iade_hesabi_id', False)
                )
                if account:
                    vals['account_id'] = account.id

        lines = super().create(vals_list)
        lines._enforce_zero_kdv_for_istisna()
        lines._update_product_hs_code()
        return lines

    def _update_product_hs_code(self):
        """GTIP kodunu urun kartiyla senkronize et (iki yonlu).
        - Fatura satirinda GTIP varsa ve urun kartindakinden farkliysa -> urun kartini guncelle
        - Fatura satirinda GTIP silindiyse -> urun kartindaki hs_code'u da sil
        """
        for line in self:
            if not line.product_id:
                continue
            tmpl = line.product_id.product_tmpl_id
            if line.gtip_kodu:
                # GTIP degeri var - urun kartini guncelle
                if tmpl.hs_code != line.gtip_kodu:
                    tmpl.sudo().write({'hs_code': line.gtip_kodu})
            else:
                # GTIP silindi - urun kartindaki hs_code'u da sil
                if tmpl.hs_code and line.istisna_kodu:
                    # Sadece istisna kodu olan urunlerde senkronize sil
                    # (istisna kodu olmayan urunlerde hs_code'a dokunma)
                    tmpl.sudo().write({'hs_code': False})

    def write(self, vals):
        # Partner bilgisi değişmişse, partner'e göre kodları doldur
        if 'partner_id' in vals:
            partner = self.env['res.partner'].browse(vals['partner_id'])
            if partner:
                if partner.parent_id:
                    vals = self._get_partner_codes(partner.parent_id, vals)
                else:
                    vals = self._get_partner_codes(partner, vals)

        # İade faturası satırı için account_id override
        move_type = vals.get('move_type')
        if not move_type and 'move_id' in vals:
            move_type = self.env['account.move'].browse(vals['move_id']).move_type
        if move_type == 'out_refund' and vals.get('product_id'):
            product = self.env['product.product'].browse(vals['product_id']).with_company(vals.get('company_id'))
            company = self.env['res.company'].browse(vals.get('company_id')) if vals.get('company_id') else self.env.company
            account = (
                getattr(product, 'l10n_tr_default_sales_return_account_id', False)
                or getattr(product.categ_id, 'l10n_tr_default_sales_return_account_id', False)
                or getattr(company, 'iade_hesabi_id', False)
            )
            if account:
                vals['account_id'] = account.id

        result = super().write(vals)
        if not self.env.context.get('skip_istisna_zero_tax_enforce'):
            self._enforce_zero_kdv_for_istisna()
        self._update_product_hs_code()
        return result

    def _get_partner_codes(self, partner, vals):
        """
        Partner'e göre ilgili kodları almak için yardımcı metod.
        """
        if partner:
            if partner.parent_id:
                # İstisna kodunu al
                if not vals.get('istisna_kodu') and partner.parent_id.istisna_kodu:
                    vals['istisna_kodu'] = partner.parent_id.istisna_kodu.id

                # Tevkifat kodunu al
                if not vals.get('tevkifat_kodu') and partner.parent_id.tevkifat_kodu:
                    vals['tevkifat_kodu'] = partner.parent_id.tevkifat_kodu.id

                # İhrac Kayıt kodunu al
                if not vals.get('ihrac_kayit_kodu') and partner.parent_id.ihrac_kayit_kodu:
                    vals['ihrac_kayit_kodu'] = partner.parent_id.ihrac_kayit_kodu.id

                # Özel Matrah kodunu al
                if not vals.get('ozel_matrah_kodu') and partner.parent_id.ozel_matrah_kodu:
                    vals['ozel_matrah_kodu'] = partner.parent_id.ozel_matrah_kodu.id

                # Vergi kodunu al
                if not vals.get('vergi_kodu') and partner.vergi_kodu:
                    vals['vergi_kodu'] = partner.vergi_kodu.id
            else:
                # İstisna kodunu al
                if not vals.get('istisna_kodu') and partner.istisna_kodu:
                    vals['istisna_kodu'] = partner.istisna_kodu.id

                # Tevkifat kodunu al
                if not vals.get('tevkifat_kodu') and partner.tevkifat_kodu:
                    vals['tevkifat_kodu'] = partner.tevkifat_kodu.id

                # İhrac Kayıt kodunu al
                if not vals.get('ihrac_kayit_kodu') and partner.ihrac_kayit_kodu:
                    vals['ihrac_kayit_kodu'] = partner.ihrac_kayit_kodu.id

                # Özel Matrah kodunu al
                if not vals.get('ozel_matrah_kodu') and partner.ozel_matrah_kodu:
                    vals['ozel_matrah_kodu'] = partner.ozel_matrah_kodu.id

                # Vergi kodunu al
                if not vals.get('vergi_kodu') and partner.vergi_kodu:
                    vals['vergi_kodu'] = partner.vergi_kodu.id

        return vals

    @api.depends('tax_ids')
    def _compute_vergi_kodu(self):
        """Bu metod artık kullanılmıyor - vergi_kodu kullanıcı tarafından serbestçe seçilir."""
        pass

    @api.depends('partner_id')
    def _compute_istisna_kodu(self):
        for record in self:
            if record.partner_id:
                if record.partner_id.parent_id:
                    record.istisna_kodu = record.partner_id.parent_id.istisna_kodu.id if record.partner_id.parent_id.istisna_kodu else False
                else:
                    record.istisna_kodu = record.partner_id.istisna_kodu.id if record.partner_id.istisna_kodu else False

    @api.depends('partner_id')
    def _compute_tevkifat_kodu(self):
        for record in self:
            if record.partner_id:
                if record.partner_id.parent_id:
                    record.tevkifat_kodu = record.partner_id.parent_id.tevkifat_kodu.id if record.partner_id.parent_id.tevkifat_kodu else False
                else:
                    record.tevkifat_kodu = record.partner_id.tevkifat_kodu.id if record.partner_id.tevkifat_kodu else False
    
    @api.depends('partner_id')
    def _compute_ihrac_kayit_kodu(self):
        for record in self:
            if record.partner_id:
                if record.partner_id.parent_id:
                    record.ihrac_kayit_kodu = record.partner_id.parent_id.ihrac_kayit_kodu.id if record.partner_id.parent_id.ihrac_kayit_kodu else False
                else:
                    record.ihrac_kayit_kodu = record.partner_id.ihrac_kayit_kodu.id if record.partner_id.ihrac_kayit_kodu else False

    @api.depends('partner_id')
    def _compute_ozel_matrah_kodu(self):
        for record in self:
            if record.partner_id:
                if record.partner_id.parent_id:
                    record.ozel_matrah_kodu = record.partner_id.parent_id.ozel_matrah_kodu.id if record.partner_id.parent_id.ozel_matrah_kodu else False
                else:
                    record.ozel_matrah_kodu = record.partner_id.ozel_matrah_kodu.id if record.partner_id.ozel_matrah_kodu else False

    @api.depends('currency_id', 'company_id', 'move_id.invoice_currency_rate', 'move_id.date')
    def _compute_currency_rate(self):
        for line in self:
            if line.move_id:
                # Eğer move fatura ise
                if line.move_id.is_invoice(include_receipts=True):
                    line.currency_rate = line.move_id.invoice_currency_rate
                # Eğer move üzerinde payment_currency_rate alanı tanımlı ve değeri varsa, o değeri kullan
                elif 'payment_currency_rate' in line.move_id._fields and line.move_id.payment_currency_rate:
                    line.currency_rate = line.move_id.payment_currency_rate
                elif line.move_id.invoice_currency_rate or line.move_id.invoice_currency_rate > 0:
                    line.currency_rate = line.move_id.invoice_currency_rate
                # Diğer durumlarda standart dönüşüm kurlarını hesapla
                elif line.currency_id:
                    line.currency_rate = self.env['res.currency']._get_conversion_rate(
                        from_currency=line.company_currency_id,
                        to_currency=line.currency_id,
                        company=line.company_id,
                        date=line._get_rate_date(),
                    )
                else:
                    line.currency_rate = 1
            else:
                line.currency_rate = 1

    @api.onchange('amount_currency', 'debit', 'credit', 'currency_id')
    def _onchange_currency_related_fields(self):
        for record in self:
            if record.move_type == 'entry' and record.payment_id:
                raise UserError('Ödeme kaydı ile ilişkilendirilmiş bir satırın para birimi, borç ve alacak tutarları değiştirilemez.')
            if record.move_type == 'entry' and record.reconciled:
                raise UserError('Mutabakatlanmış bir satırın para birimi, borç ve alacak tutarları değiştirilemez.')
            
    move_line_ids = fields.Many2many(
        comodel_name="stock.move",
        relation="stock_move_invoice_line_rel",
        column1="invoice_line_id",
        column2="move_id",
        string="Related Stock Moves",
        readonly=True,
        copy=False,
        help="Related stock moves (only when the invoice has been"
        " generated from a sale order).",
    )

    def copy_data(self, default=None):
        """Copy the move_line_ids in case of refund invoice creating new invoices
        (refund_method="modify") for multiple records."""
        vals_list = super().copy_data(default)

        if self.env.context.get("force_copy_stock_moves"):
            for record, vals in zip(self, vals_list, strict=False):
                if "move_line_ids" not in vals and record.move_line_ids:
                    vals["move_line_ids"] = [Command.set(record.move_line_ids.ids)]

        return vals_list

    def _compute_account_id(self):
        # OVERRIDE
        super()._compute_account_id()

        for line in self.filtered(lambda l: l.company_id.country_code == 'TR'
                                  and l.move_id.move_type == 'out_refund'
                                  and l.display_type == 'product'):
            product = line.product_id.with_company(line.company_id)
            company = line.company_id
            # Öncelik: ürün, kategori, şirket
            account = (
                getattr(product, 'l10n_tr_default_sales_return_account_id', False)
                or getattr(product.categ_id, 'l10n_tr_default_sales_return_account_id', False)
                or getattr(company, 'iade_hesabi_id', False)
            )
            if account:
                line.account_id = account
        # Diğer durumlarda Odoo'nun default davranışı devam eder
    def _validate_product_hs_code_required(self):
        if self.env.context.get('skip_gtip_validation'):
            return

        for line in self:
            if not line.move_id or not line.move_id.is_invoice(include_receipts=True):
                continue
            if line.display_type and line.display_type != 'product':
                continue
            if not line.product_id:
                continue
            if not line.istisna_kodu:
                continue
            if not line.gtip_kodu:
                raise ValidationError(
                    _("Istisna kodu secili satirda GTIP Kodu zorunludur (12 haneli rakam). "
                      "Lütfen fatura satırında GTIP kodunu girin.")
                )

