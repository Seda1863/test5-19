# -*- coding: utf-8 -*-
import io
import zipfile
import base64
import calendar
from dateutil.relativedelta import relativedelta
from odoo import models, fields, api, _
from odoo.exceptions import UserError
from datetime import datetime, date
import json

class MdxEDefter(models.Model):
    _name = 'mdx.edefter'
    _description = 'E-Defter'
    _check_company_auto = True

    # store=True yapılacak alanlar
    owner_id = fields.Many2one('res.users', string='Sorumlu Kişi', related='company_id.owner_id')
    fiscal_year_start_date = fields.Date(
        string='Mali Yıl Başlangıç Tarihi', 
        default=lambda self: date(
            datetime.now().year, 
            int(self.env.company.fiscal_year_start_month or 1), 
            1
        )
    )
    fiscal_year_end_date = fields.Date(
        string='Mali Yıl Bitiş Tarihi', 
        default=lambda self: date(
            datetime.now().year + (1 if int(self.env.company.fiscal_year_end_month or 12) < int(self.env.company.fiscal_year_start_month or 1) else 0),
            int(self.env.company.fiscal_year_end_month or 12), 
            calendar.monthrange(
                datetime.now().year + (1 if int(self.env.company.fiscal_year_end_month or 12) < int(self.env.company.fiscal_year_start_month or 1) else datetime.now().year),
                int(self.env.company.fiscal_year_end_month or 12)
            )[1]
        )
    )

    month = fields.Selection([
        ('01', 'Ocak'),
        ('02', 'Şubat'),
        ('03', 'Mart'),
        ('04', 'Nisan'),
        ('05', 'Mayıs'),
        ('06', 'Haziran'),
        ('07', 'Temmuz'),
        ('08', 'Ağustos'),
        ('09', 'Eylül'),
        ('10', 'Ekim'),
        ('11', 'Kasım'),
        ('12', 'Aralık'),
    ], string='Ay', required=True, default=lambda self: datetime.now().strftime('%m'), store=True)
    
    year_selections = [(str(i), str(i)) for i in range(datetime.now().year - 5, datetime.now().year + 5)]
    year = fields.Selection(year_selections, string='Yıl', required=True, default=lambda self: datetime.now().strftime('%Y'), store=True)
    company_id = fields.Many2one(
        'res.company', 
        string='Şirket', 
        required=True, 
        default=lambda self: self.env.company,
        store=True
    )

    # İşlemi yapan kişi
    user_id = fields.Many2one('res.users', string='İşlemi Yapan', store=True)
    date = fields.Datetime(string='İşlem Tarihi', store=True)

    # computed alanlar
    name = fields.Char(string='İsim', required=True, compute='_compute_name')
    entry_sequence_start_no = fields.Integer(string='Yevmiye Başlama No', required=True, compute='_compute_sequece')
    entry_sequence_end_no = fields.Integer(string='Yevmiye Bitiş No', required=True, compute='_compute_sequece')
    line_sequence_start_no = fields.Integer(string='Satır Sıra Başlama No', required=True, compute='_compute_sequece')
    line_sequence_end_no = fields.Integer(string='Satır Sıra Bitiş No', required=True, compute='_compute_sequece')
    journal_entry_ids = fields.One2many('account.move', string='Hesap Hareketleri', compute='_compute_journal_entry_ids')
    journal_entry_line_ids = fields.One2many('account.move.line', string='Hesap Hareketi Satırları', compute='_compute_journal_entry_line_ids')
    active = fields.Boolean(string='Aktif', default=True)
    
    @api.model
    def create(self, vals):
        # for key in ['entry_sequence_start_no', 'entry_sequence_end_no', 'line_sequence_start_no', 'line_sequence_end_no']:
        #     if not vals.get(key) or vals.get(key) == 0:
        #         raise UserError(_('Yevmiye kayıtları numaralandırılmamış.'))

        existing_record = self.search([
            ('company_id', '=', vals['company_id']),
            ('month', '=', vals['month']),
            ('year', '=', vals['year']),
            # ('state', '=', 'posted'),
        ])
        if existing_record:
            raise UserError(_('Bu döneme ait bir kayıt zaten var.'))

        company = self.env.company
        fiscal_start_month = int(company.fiscal_year_start_month or 1)
        current_month = int(vals['month'])
        current_fiscal_order = current_month - fiscal_start_month
        if current_fiscal_order < 0:
            current_fiscal_order += 12

        if current_fiscal_order > 0:
            records = self.search([('company_id', '=', vals['company_id']), ('year', '=', vals['year'])])
            def get_fiscal_order(rec):
                m = int(rec.month)
                order = m - fiscal_start_month
                if order < 0:
                    order += 12
                return order
            if not any(get_fiscal_order(rec) < current_fiscal_order for rec in records):
                raise UserError(_('Önceki ayların kayıtları oluşturulmamış.'))

        record = super(MdxEDefter, self).create(vals)
        return record

    @api.depends('company_id', 'month', 'year', 'journal_entry_ids.line_ids')
    def _compute_sequece(self):
        for record in self:
            all_lines = record.journal_entry_ids.mapped('line_ids').sorted(key=lambda x: x.entry_sequence_no)
            if all_lines:
                record.entry_sequence_start_no = all_lines[0].entry_sequence_no
                record.entry_sequence_end_no = all_lines[-1].entry_sequence_no
                record.line_sequence_start_no = all_lines[0].line_sequence_no
                record.line_sequence_end_no = all_lines[-1].line_sequence_no
            else:
                record.entry_sequence_start_no = 0
                record.entry_sequence_end_no = 0
                record.line_sequence_start_no = 0
                record.line_sequence_end_no = 0

    @api.depends('month', 'year', 'fiscal_year_start_date', 'fiscal_year_end_date')
    def _compute_journal_entry_ids(self):
        for record in self:
            year = int(record.year)
            month = int(record.month)
            first_day = date(year, month, 1)
            _, last_day = calendar.monthrange(year, month)
            last_day_date = date(year, month, last_day)
            
            if record.fiscal_year_start_date and record.fiscal_year_start_date.year == year and record.fiscal_year_start_date.month == month:
                date_start = record.fiscal_year_start_date
            else:
                date_start = first_day

            if record.fiscal_year_end_date and record.fiscal_year_end_date.year == year and record.fiscal_year_end_date.month == month:
                date_end = record.fiscal_year_end_date
            else:
                date_end = last_day_date

            record.journal_entry_ids = self.env['account.move'].search([
                ('date', '>=', date_start.strftime('%Y-%m-%d')),
                ('date', '<=', date_end.strftime('%Y-%m-%d')),
                ('company_id', '=', record.company_id.id),
                ('state', '=', 'posted'),
            ])

    @api.depends('journal_entry_ids')
    def _compute_journal_entry_line_ids(self):
        for record in self:
            record.journal_entry_line_ids = self.env['account.move.line'].search([
                ('move_id', 'in', record.journal_entry_ids.ids),
            ])

    @api.depends('company_id', 'month', 'year')
    def _compute_name(self):
        for record in self:
            record.name = f'{record.company_id.name} {record.year}-{record.month}'

    def action_create_entry_sequence(self):
        for record in self:
            year = int(record.year)
            month = int(record.month)
            first_day = date(year, month, 1)
            _, last_day = calendar.monthrange(year, month)
            last_day_date = date(year, month, last_day)

            if record.fiscal_year_start_date and record.fiscal_year_start_date.year == year and record.fiscal_year_start_date.month == month:
                date_start = record.fiscal_year_start_date
            else:
                date_start = first_day

            if record.fiscal_year_end_date and record.fiscal_year_end_date.year == year and record.fiscal_year_end_date.month == month:
                date_end = record.fiscal_year_end_date
            else:
                date_end = last_day_date

            moves = self.env['account.move'].search([
                ('date', '>=', date_start.strftime('%Y-%m-%d')),
                ('date', '<=', date_end.strftime('%Y-%m-%d')),
                ('company_id', '=', record.company_id.id),
                ('state', '=', 'posted'),
            ])
            moves = moves.sorted(key=lambda x: x.date)
            if month == (record.fiscal_year_start_date.month if record.fiscal_year_start_date.year == year else 1):
                move_sequence = 1
                line_sequence = 1
            else:
                prev_month = month - 1
                prev_year = year
                if prev_month == 0:
                    prev_month = 12
                    prev_year -= 1
                prev_first_day = date(prev_year, prev_month, 1)
                _, prev_last_day = calendar.monthrange(prev_year, prev_month)
                prev_last_day_date = date(prev_year, prev_month, prev_last_day)
                if record.fiscal_year_end_date and record.fiscal_year_end_date.year == prev_year and record.fiscal_year_end_date.month == prev_month:
                    date_prev_end = record.fiscal_year_end_date
                else:
                    date_prev_end = prev_last_day_date

                moves_prev = self.env['account.move'].search([
                    ('date', '>=', prev_first_day.strftime('%Y-%m-%d')),
                    ('date', '<=', date_prev_end.strftime('%Y-%m-%d')),
                    ('company_id', '=', record.company_id.id),
                    ('state', '=', 'posted'),
                ])
                moves_prev = moves_prev.sorted(key=lambda x: x.date)
                if not moves_prev or not moves_prev[-1].entry_sequence_no:
                    raise UserError(_('Önceki ayın kayıtlarında giriş sıra numarası bulunamadı.'))
                    
                move_sequence = moves_prev[-1].entry_sequence_no + 1
                
                lines_prev = self.env['account.move.line'].search([
                    ('move_id', 'in', moves_prev.ids),
                ])
                lines_prev = lines_prev.sorted(key=lambda x: x.line_sequence_no)
                if not lines_prev:
                    raise UserError(_('Önceki ayın kayıtlarında satır sıra numarası bulunamadı.'))
                line_sequence = lines_prev[-1].line_sequence_no + 1

            for move in moves:
                move.write({'entry_sequence_no': move_sequence})
                for line in move.line_ids:
                    line.write({
                        'line_sequence_no': line_sequence,
                        'entry_sequence_no': move_sequence,
                    })
                    line_sequence += 1
                move_sequence += 1

        record.user_id = self.env.user
        record.date = datetime.now()

    def action_create_csv(self):
        for record in self.with_context(lang='tr_TR'):
            # Kayıtlar numaralandırılmamışsa hata verelim
            if not record.entry_sequence_start_no or record.entry_sequence_start_no == 0:
                raise UserError(_('Yevmiye kayıtları numaralandırılmamış.'))
            
            if not record.user_id:
                raise UserError(_('Önce numaralandırma işlemi yapınız.'))

            if not record.journal_entry_ids:
                raise UserError(_('Yevmiye kaydı bulunamadı.'))

            if not record.journal_entry_line_ids:
                raise UserError(_('Hesap hareketi satırı bulunamadı.'))

            formatted_fiscal_year_start_date = record.fiscal_year_start_date.strftime('%Y%m%d')
            formatted_fiscal_year_end_date = record.fiscal_year_end_date.strftime('%Y%m%d')
            csv_data = f'{record.owner_id.name};;="{record.year}{record.month}01";="{record.year}{record.month}{calendar.monthrange(int(record.year), int(record.month))[1]}";;;="{formatted_fiscal_year_start_date}";="{formatted_fiscal_year_end_date}";={record.company_id.vat}\n'
            # csv_data += f'Yevmiye No;İşlem Yapan;Kayıt Tarihi;Kayıt No;Kayıt Açıklaması;Toplam Borç;Toplam Alacak;Ana Hesap;Ana Hesap Açıklaması;Alt Hesap Açıklaması;Alt Hesap;Tutar;;Posting Date;Belge No;Parça Açıklaması;Belge Tipi;Belge Tipi Açıklaması;Belge No;Belge Tarihi;Ödeme Metodu\n'
            for line in record.journal_entry_line_ids.sorted(key=lambda x: (x.entry_sequence_no, x.line_sequence_no)):
                if line.move_id.invoice_date:
                    date = line.move_id.invoice_date.strftime('%d.%m.%Y')
                else:
                    date = line.date.strftime('%d.%m.%Y')
                # csv_data += f'{line.entry_sequence_no};{line.line_sequence_no};{line.account_id.code};{line.account_id.name};{line.debit};{line.credit};{line.name}\n'
                csv_data += f'{line.entry_sequence_no}'
                if line.create_uid.id == 1:
                    csv_data += ';Sistem'
                else:
                    csv_data += f';{line.create_uid.name}'

                line_date = line.date.strftime('%Y%m%d')

                csv_data += f';="{line_date}"'
                csv_data += f';{line.move_name}'

                record_description = ""
                if line.move_id.move_type == 'out_invoice':
                    record_description = "FS"
                elif line.move_id.move_type == 'in_invoice':
                    record_description = "FA"
                else:
                    # move_name ilk 3 harfi
                    record_description = (line.move_name or '')[:3]

                record_description += f'-{date}'

                if line.move_id.fatura_no:
                    record_description += f'-{line.move_id.fatura_no}'
                else:
                    record_description += f'-{line.move_id.name}'

                record_description += f'-{line.move_id.partner_id.name}'  

                csv_data += f';{record_description}'
                
                total_debit = 0
                total_credit = 0
                for i in record.journal_entry_line_ids.filtered(lambda x: x.move_id == line.move_id):
                    total_debit += i.debit
                    total_credit += i.credit

                if line.balance > 0:
                    csv_data += f';{total_debit};{float(0)}'
                else:
                    csv_data += f';{float(0)};{total_credit}'

                csv_data += f';{line.account_id.group_id.parent_id.code_prefix_start}'
                csv_data += f';{line.account_id.group_id.parent_id.name}'
                csv_data += f';{line.account_id.name}'
                csv_data += f';{line.account_id.code}'
                csv_data += f';{abs(line.balance)}'

                if line.balance > 0:
                    csv_data += f';D'
                else:
                    csv_data += f';C'

                csv_data += f';="{line_date}"'
                csv_data += f';{line.move_name}'
                csv_data += f';{record_description}'
                csv_data += f';{line.move_id.document_type or ""}'
                csv_data += f';{line.move_id.document_type_description_id.name or ""}'
                csv_data += f';{line.move_id.document_number or ""}'

                document_date = line.move_id.document_date.strftime('%Y%m%d') if line.move_id.document_date else ""

                csv_data += f';="{document_date}"'
                csv_data += f';{line.move_id.payment_method or ""}\n'

            csv_data = '\ufeff' + csv_data
            # CSV dosyasını bir ZIP arşivi içerisine ekleyelim
            csv_file_name = f'{record.company_id.vat}_0000_{record.year}{record.month}_1.csv'
            zip_file_name = f'{record.company_id.vat}_0000_{record.year}{record.month}_1.zip'
            zip_buffer = io.BytesIO()
            with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
                zip_file.writestr(csv_file_name, csv_data)

            # ZIP dosyasını base64'e çeviriyoruz
            zip_b64 = base64.b64encode(zip_buffer.getvalue()).decode('utf-8')

            # Attachment oluşturuluyor
            zip_attachment = self.env['ir.attachment'].create({
                'name': zip_file_name,
                'type': 'binary',
                'datas': zip_b64,
                'res_model': 'mdx.edefter',
                'res_id': record.id,
                'mimetype': 'application/zip',
            })

            return {
                'type': 'ir.actions.act_url',
                'url': '/web/content/%s?download=true' % zip_attachment.id,
                'target': 'new',
            }
