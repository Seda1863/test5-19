# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import UserError
import json
import re

# Fatura, İrsaliye

class MdxChequeBook(models.Model):
    _name = 'mdx.cheque.book'
    _description = 'Çek Defteri'

    # code = fields.Char(string='Kod', required=True, store=True)
    name = fields.Char(string='Ad', required=True, store=True)
    description = fields.Text(string='Açıklama', store=True)
    active = fields.Boolean(string='Aktif', default=True, store=True)
    company_id = fields.Many2one(
        'res.company',
        string='Şirket',
        required=True,
        default=lambda self: self.env.company,
        store=True,
    )
    # bank = fields.Many2one(
    #     'res.bank',
    #     string='Banka',
    #     required=True,
    #     store=True,
    # )

    account_id = fields.Many2one(
        'account.account',
        string='Çek Hesabı',
        required=True,
        store=True,
    )

    bank_name = fields.Char(string='Banka', required=True, store=True)
    bank_branch = fields.Char(string='Banka Şubesi', required=True, store=True)
    currency_id = fields.Many2one(
        'res.currency',
        string='Para Birimi',
        required=True,
        store=True,
    )

    prefix = fields.Char(string='Ön Ek', store=True)
    cheque_leaf_number = fields.Integer(string='Çek Yaprağı Sayısı', required=True, store=True)
    cheque_leaf_start_number = fields.Integer(string='Çek Yaprağı Başlangıç Numarası', required=True, store=True)
    cheque_book_status = fields.Selection(
        selection=[
            ('draft', 'Taslak'),
            ('created', 'Oluşturuldu'),
        ],
        string='Durum',
        default='draft',
        store=True,
    )

    cheque_leaf_ids = fields.One2many(
        'mdx.cheque.leaf',
        'cheque_book_id',
        copy=False,
        string='Çek Yaprakları',
    )

    @api.model
    def create(self, vals):
        """
        Create a new cheque book and generate cheque leaves.
        """
        cheque_book = super(MdxChequeBook, self).create(vals)
        cheque_book.generate_cheque_leaves()
        cheque_book.cheque_book_status = 'created'
        return cheque_book
    
    def generate_cheque_leaves(self):
        """
        Generate cheque leaves based on the cheque book configuration.
        """
        for cheque_book in self:
            for i in range(cheque_book.cheque_leaf_start_number, cheque_book.cheque_leaf_start_number + cheque_book.cheque_leaf_number):
                self.env['mdx.cheque.leaf'].create({
                    'name': f"{cheque_book.prefix}{i}",
                    'cheque_book_id': cheque_book.id,
                    'cheque_number': i,
                    'cheque_status': self.env['mdx.sabit.kod'].search([('liste_id.code', '=', 'CEKSTATU'), ('code', '=', 'TASLAK')], limit=1).id,
                    'due_date': fields.Date.today(),
                    'amount': 0.0,
                    'currency_id': cheque_book.currency_id.id,
                    'account_id': cheque_book.account_id.id,
                    # 'receiver_id': self.env['res.partner'].search([('is_supplier', '=', True)], limit=1).id,
                    # 'issuer_id': self.env['res.partner'].search([('is_customer', '=', True)], limit=1).id,
                    # 'first_owner_id': self.env['res.partner'].search([('is_company', '=', True)], limit=1).id,
                    'owner_type': 'company',
                    'created_with_cheque_book': True,
                })

    def write(self, vals):
        """
        Handle cheque book modifications:
        - Prevent reducing cheque leaf count if leaves exist
        - Generate new leaves when leaf count is increased
        - Prevent changing start number if leaves exist
        """
        # Check for leaf number reduction
        if 'cheque_leaf_number' in vals:
            for record in self:
                new_count = vals['cheque_leaf_number']
                current_count = record.cheque_leaf_number
                existing_leaves = len(record.cheque_leaf_ids)
                
                if new_count < existing_leaves:
                    raise UserError(_("Çek yaprağı sayısı mevcut çek sayısından (%d) az olamaz!") % existing_leaves)
                
                # Prevent reduction even if no leaves exist yet
                if new_count < current_count:
                    raise UserError(_("Çek yaprağı sayısını azaltamazsınız!"))

        # Check for start number change
        if 'cheque_leaf_start_number' in vals and any(book.cheque_leaf_ids for book in self):
            raise UserError(_("Mevcut çekler varken başlangıç numarasını değiştiremezsiniz!"))

        # Handle leaf count increase
        res = super(MdxChequeBook, self).write(vals)
        
        if 'cheque_leaf_number' in vals:
            for record in self:
                new_count = record.cheque_leaf_number
                current_leaves = len(record.cheque_leaf_ids)
                
                if new_count > current_leaves:
                    # Calculate how many new leaves to add
                    additional = new_count - current_leaves
                    
                    # Find next cheque number (max existing + 1 or start number if no leaves)
                    if record.cheque_leaf_ids:
                        next_num = max(record.cheque_leaf_ids.mapped('cheque_number')) + 1
                    else:
                        next_num = record.cheque_leaf_start_number
                    
                    # Generate new leaves
                    record.generate_additional_leaves(additional, next_num)
        
        return res

    def generate_additional_leaves(self, count, start_number):
        """
        Generate additional cheque leaves
        :param count: Number of leaves to add
        :param start_number: Starting cheque number
        """
        for i in range(start_number, start_number + count):
            self.env['mdx.cheque.leaf'].create({
                'name': f"{self.prefix}{i}",
                'cheque_book_id': self.id,
                'cheque_number': i,
                'cheque_status': self.env['mdx.sabit.kod'].search([
                    ('liste_id.code', '=', 'CEKSTATU'),
                    ('code', '=', 'TASLAK')
                ], limit=1).id,
                'due_date': fields.Date.today(),
                'amount': 0.0,
                'currency_id': self.currency_id.id,
                'account_id': self.account_id.id,
                'owner_type': 'company',
                'created_with_cheque_book': True,
            })

    # def action_create_cheque_book(self):
    #     """
    #     Action to create a new cheque book.
    #     """
    #     self.ensure_one()
    #     if not self.cheque_book_status == 'draft':
    #         raise UserError("Çek defteri zaten oluşturulmuş.")
        
    #     # Create the cheque book
    #     cheque_book = self.create({
    #         'name': self.name,
    #         'bank_name': self.bank_name,
    #         'bank_branch': self.bank_branch,
    #         'currency_id': self.currency_id.id,
    #         'prefix': self.prefix,
    #         'cheque_leaf_number': self.cheque_leaf_number,
    #         'cheque_leaf_start_number': self.cheque_leaf_start_number,
    #         'cheque_book_status': 'created',
    #     })
        
    #     return cheque_book
    
class MdxChequeLeaf(models.Model):
    _name = 'mdx.cheque.leaf'
    _description = 'Çek Yaprağı'
    _rec_name = 'name'
    _order = 'cheque_number'

    created_with_cheque_book = fields.Boolean(
        string='Çek Defteri ile Oluşturuldu',
        default=False,
        store=True,
    )
    name = fields.Char(string='Ad', required=True, store=True)
    prefix = fields.Char(string='Ön Ek', store=True, default=lambda self: self.cheque_book_id.prefix if self.cheque_book_id else '')
    cheque_number = fields.Integer(string='Çek Numarası', required=True, store=True)

    cheque_book_id = fields.Many2one(
        'mdx.cheque.book',
        string='Çek Defteri',
        # required=True,
        readonly=True,
        ondelete="cascade",
        store=True,
    )

    company_id = fields.Many2one(
        'res.company',
        string='Şirket',
        required=True,
        default=lambda self: self.cheque_book_id.company_id.id if self.cheque_book_id else self.env.company.id,
        store=True,
    )
    
    cheque_status = fields.Many2one('mdx.sabit.kod', string='Durum', store=True, domain=[('liste_id.code', '=', 'CEKSTATU')])
    due_date = fields.Date(string='Vade Tarihi', store=True)
    amount = fields.Monetary(string='Çek Tutarı', store=True, currency_field='currency_id')
    currency_id = fields.Many2one(
        'res.currency',
        string='Para Birimi',
        required=True,
        store=True,
    )
    account_id = fields.Many2one(
        'account.account',
        string='Çek Hesabı',
        # required=True,
        store=True,
    )
    receiver_id = fields.Many2one(
        'res.partner',
        string='Çeki Alan / Tedarikçi',
        # required=True,
        store=True,
        related='outbound_payment_id.partner_id',
        readonly=False,
        domain="[('is_supplier', '=', True)]",
    )
    issuer_id = fields.Many2one(
        'res.partner',
        string='Çeki Veren / Müşteri',
        # required=True,
        store=True,
        related='inbound_payment_id.partner_id',
        readonly=False,
        domain="[('is_customer', '=', True)]",
    )
    first_owner_id = fields.Many2one(
        'res.partner',
        string='Çek İlk Sahibi',
        store=True,
    )
    outbound_payment_id = fields.Many2one(
        'account.payment',
        string='Tedarikçi Ödemesi',
        store=True,
        readonly=True,
    )
    inbound_payment_id = fields.Many2one(
        'account.payment',
        string='Müşteri Ödeme',
        store=True,
        readonly=True,
    )
    # account_move_ids = fields.One2many(
    #     'account.move',
    #     'cheque_leaf_id',
    #     string='İlişkiliHesap Hareketleri',
    #     store=True,
    #     readonly=True,
    # )
    owner_type = fields.Selection(
        selection=[
            ('company', 'Şirket'),
            ('individual', 'Gerçek Kişi'),
        ],
        string='Çek Sahibi Türü',
        # required=True,
        default='company',
        store=True,
    )
    active = fields.Boolean(string='Aktif', default=True, store=True)

    # def _compute_account_move_id(self):
    #     # Search for the account move associated with this cheque leaf
    #     for leaf in self:
    #         account_move = self.env['account.move'].search([
    #             ('cheque_leaf_id', '=', leaf.id)
    #         ], limit=1)
    #         leaf.account_move_id = account_move.id if account_move else False

    # def action_open_account_move(self):
    #     self.ensure_one()
    #     if self.account_move_id:
    #         name = _("Account Move")
    #         res_model = 'account.move'
    #         res_id = self.account_move_id.id

    #     return {
    #         'name': name,
    #         'type': 'ir.actions.act_window',
    #         'view_mode': 'form',
    #         'views': [(False, 'form')],
    #         'res_model': res_model,
    #         'res_id': res_id,
    #         'target': 'current',
    #     }

    def action_open_outbound_payment(self):
        self.ensure_one()
        if self.outbound_payment_id:
            name = _("Payment")
            res_model = 'account.payment'
            res_id = self.outbound_payment_id.id

        return {
            'name': name,
            'type': 'ir.actions.act_window',
            'view_mode': 'form',
            'views': [(False, 'form')],
            'res_model': res_model,
            'res_id': res_id,
            'target': 'current',
        }
    
    def action_open_inbound_payment(self):
        self.ensure_one()
        if self.inbound_payment_id:
            name = _("Payment")
            res_model = 'account.payment'
            res_id = self.inbound_payment_id.id

        return {
            'name': name,
            'type': 'ir.actions.act_window',
            'view_mode': 'form',
            'views': [(False, 'form')],
            'res_model': res_model,
            'res_id': res_id,
            'target': 'current',
        }
    
    def action_open_cheque_book(self):
        """
        Open the cheque book associated with this cheque leaf.
        """
        self.ensure_one()
        return {
            'name': _('Cheque Book'),
            'type': 'ir.actions.act_window',
            'view_mode': 'form',
            'res_model': 'mdx.cheque.book',
            'res_id': self.cheque_book_id.id,
            'target': 'current',
        }
    
    @api.model
    def create(self, vals):
        """
        Override create method to set the name based on the cheque number and prefix.
        """
        # If prefix exists in vals, use it directly
        if vals.get('issuer_id') and not vals.get('first_owner_id'):
            # Set first owner to issuer if not set
            vals['first_owner_id'] = vals['issuer_id']
        
        if vals.get('prefix'):
            if vals.get('cheque_number') is None and vals.get('name') is not None:
                # Extract cheque number from name
                cheque_str = str(vals['name'])
                # Search existing prefix in name
                match = re.match(str(f"^{vals['prefix']}(\d+)"), cheque_str)
                if match:
                    cheque_number = match.group(1)
                    vals['cheque_number'] = int(cheque_number) if cheque_number.isdigit() else 0
                else:
                    raise UserError(_("Girilen ön ek ile çek adı uyuşmuyor. Lütfen kontrol edin."))
            elif vals.get('cheque_number') is not None and vals.get('name') is None:
                if vals['cheque_number'] < 0:
                    raise UserError(_("Çek numarası negatif olamaz. Lütfen pozitif bir değer girin."))
                # Set name using prefix and cheque number
                vals['name'] = f"{vals['prefix']}{vals['cheque_number']}"
        else:
            if vals.get('cheque_number') is not None and vals.get('name') is None:
                # Extract prefix using regex (letters at the beginning)
                cheque_str = str(vals['cheque_number'])
                prefix = ''
                match = re.match(r"^([A-Za-z]+)", cheque_str)
                if match:
                    prefix = match.group(1)
                    cheque_str = cheque_str[len(prefix):]
                
                # Set extracted values
                vals['prefix'] = prefix
                vals['name'] = prefix + cheque_str
                vals['cheque_number'] = int(cheque_str) if cheque_str.isdigit() else 0

            elif vals.get('cheque_number') is None and vals.get('name') is not None:
                cheque_str = str(vals['name'])
                prefix = ''
                match = re.match(r"^([A-Za-z]+)", cheque_str)
                if match:
                    prefix = match.group(1)
                    cheque_str = cheque_str[len(prefix):]

                vals['prefix'] = prefix
                vals['cheque_number'] = int(cheque_str) if cheque_str.isdigit() else 0
                vals['name'] = prefix + cheque_str

            # Aynı isimle bir çek yaprağı oluşturulmasını engelle
            existing_leaf = self.search([
                ('name', '=', vals['name']),
                ('cheque_book_id', '=', vals.get('cheque_book_id')),
                ('active', '=', True)
            ], limit=1)

            if existing_leaf:
                raise UserError(_('%s' ' isimli bir çek yaprağı zaten mevcut. Lütfen farklı bir isim kullanın.') % vals['name'])
        
        return super(MdxChequeLeaf, self).create(vals)
