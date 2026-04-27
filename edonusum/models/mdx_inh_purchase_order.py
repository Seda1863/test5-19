# -*- coding: utf-8 -*-

from odoo import models, fields, api
from odoo.exceptions import UserError, ValidationError
from odoo.tools.sql import SQL

class MdxInhPurchaseOrder(models.Model):
    _inherit = 'purchase.order'

    filtered_partner_ids = fields.Many2many('res.partner', compute='_compute_filtered_partner_ids', store=False)

    # TODO: TEST_GELEN_FATURA_IDS
    gelen_fatura_ids = fields.One2many('mdx.gelen.fatura', 'ref_po_id', string='Gelen Faturalar')
    gelen_irsaliye_ids = fields.One2many('mdx.gelen.irsaliye', 'ref_po_id', string='Gelen İrsaliyeler')

    task_id = fields.Many2one(
        'project.task',
        string='Görev',
        help="Bu satın alma siparişi ile ilişkilendirilmiş proje görevi.",
        store=True,
        ondelete='set null',
        domain="[('id', 'in', filtered_task_ids)]",
        compute='_compute_task_id',
        readonly=False,
    )

    filtered_task_ids = fields.Many2many(
        'project.task',
        compute='_compute_filtered_task_ids',
        string='Filtrelenmiş Görevler',
        store=False,
    )

    @api.depends('project_id')
    def _compute_task_id(self):
        for record in self:
            if record.project_id:
                continue
            else:
                record.task_id = False

    @api.depends('project_id')
    def _compute_filtered_task_ids(self):
        for record in self:
            if record.project_id:
                record.filtered_task_ids = self.env['project.task'].search([
                    ('project_id', '=', record.project_id.id),
                ])
            else:
                record.filtered_task_ids = []

    @api.depends('state')
    def _compute_filtered_partner_ids(self):
        for record in self:
            if record.state == 'draft':
                record.filtered_partner_ids = self.env['res.partner'].search([('parent_id', '=', False), ('is_supplier', '=', True)])
            else:
                record.filtered_partner_ids = self.env['res.partner'].search([('parent_id', '=', False)])

    def write(self, vals):
        res = super(MdxInhPurchaseOrder, self).write(vals)
        # Eğer picking_ids alanında bir değişiklik varsa, ilgili stock.move'lara purchase.order bilgisini işleyelim.
        if vals.get('picking_ids') or vals.get('invoice_ids'):
            self._update_stock_moves_from_picking()
        return res

    def _update_stock_moves_from_picking(self):
        """
        İlgili purchase order'a eklenen pickinge ait stock.move'ların,
        purchase.order line ile eşleşen ürün var ise, purchase_line_id alanına
        purchase order line bilgisini atar.
        """
        for order in self:
            for picking in order.picking_ids:
                if not picking.gelen_irsaliye_id:
                    # bu picking'i sil
                    picking.unlink()
                    continue
                
                for move_line in picking.move_line_ids:
                    for move in move_line.move_id:
                        # Eğer move zaten purchase.order line ile ilişkilendirilmişse geçelim
                        if move.purchase_line_id:
                            continue
                        # Aynı ürünü içeren ilk purchase order line'ı bulup ilişkilendirelim.
                        for po_line in order.order_line:
                            if po_line.product_id.id == move.product_id.id:
                                move.write({'purchase_line_id': po_line.id})
                                break

            for invoice in order.invoice_ids:
                for invoice_line in invoice.invoice_line_ids:
                    if invoice_line.purchase_line_id:
                        continue
                    for po_line in order.order_line:
                        if po_line.product_id.id == invoice_line.product_id.id:
                            invoice_line.write({'purchase_line_id': po_line.id})
                            po_line.write({'invoice_lines': [(4, invoice_line.id)]})
                            break

class MdxInhPurchaseOrderLine(models.Model):
    _inherit = 'purchase.order.line'

    work_type_id = fields.Many2one(
        'mdx.work.type',
        string='İş Türü',
        help="Bu satın alma siparişi satırının ait olduğu iş türü.",
        store=True,
        ondelete='set null',
        related='product_id.work_type_id',
        readonly=True,
        # compute='_compute_work_type_id',
    )

    project_id = fields.Many2one(
        'project.project',
        string='Proje',
        help="Bu satın alma siparişi satırının ait olduğu proje.",
        store=True,
        ondelete='set null',
        related='order_id.project_id',
        readonly=True,
        # compute='_compute_project_id',
    )

    task_id = fields.Many2one(
        'project.task',
        string='Görev',
        help="Bu satın alma siparişi satırının ait olduğu proje görevi.",
        store=True,
        ondelete='set null',
        related='order_id.task_id',
        readonly=True,
        # compute='_compute_task_id',
    )

    # picking_ids = fields.One2many(
    #     'stock.picking',
    #     string='Alımlar',
    #     help="Bu satın alma siparişi ile ilişkilendirilmiş alımlar.",
    #     readonly=True,
    #     compute='_compute_picking_ids',
    # )

    # @api.depends('product_id')
    # def _compute_work_type_id(self):
    #     for line in self:
    #         if line.product_id:
    #             line.work_type_id = line.product_id.work_type_id
    #         else:
    #             line.work_type_id = False

    # @api.depends('order_id.project_id')
    # def _compute_project_id(self):
    #     for line in self:
    #         if line.order_id.project_id:
    #             line.project_id = line.order_id.project_id
    #         else:
    #             line.project_id = False

    # @api.depends('order_id.task_id')
    # def _compute_task_id(self):
    #     for line in self:
    #         if line.order_id.task_id:
    #             line.task_id = line.order_id.task_id
    #         else:
    #             line.task_id = False

    # @api.depends('order_id.picking_ids')
    # def _compute_picking_ids(self):
    #     for line in self:
    #         if line.order_id.picking_ids:
    #             line.picking_ids = line.order_id.picking_ids.filtered(lambda p: p.state not in ['cancel', 'draft'])
    #         else:
    #             line.picking_ids = self.env['stock.picking']

class MdxInhPurchaseReport(models.Model):
    _inherit = 'purchase.report'

    # Yeni alan tanımları
    work_type_id = fields.Many2one(
        comodel_name='mdx.work.type',
        string='İş Türü',
        readonly=True,
    )
    project_id = fields.Many2one(
        comodel_name='project.project',
        string='Proje',
        readonly=True,
    )
    task_id = fields.Many2one(
        comodel_name='project.task',
        string='Görev',
        readonly=True,
    )
    # invoice_line_count = fields.Integer(
    #     string='Fatura Satırı Sayısı',
    #     readonly=True,
    # )
    # move_count = fields.Integer(
    #     string='Stok Hareketi Sayısı',
    #     readonly=True,
    # )
    # qty_received_manual = fields.Float(
    #     string='Manual Alınan Miktar',
    #     digits='Product Unit of Measure',
    #     readonly=True,
    # )
    # qty_to_invoice = fields.Float(
    #     string='Faturalanacak Miktar',
    #     digits='Product Unit of Measure',
    #     readonly=True,
    # )

    # @property
    # def _table_query(self) -> SQL:
    #     return SQL("%s %s %s %s", self._select(), self._from(), self._where(), self._group_by())

    def _select(self) -> SQL:
        return SQL(
            """
                SELECT
                    po.id as order_id,
                    min(l.id) as id,
                    po.date_order as date_order,
                    po.state,
                    po.date_approve,
                    po.dest_address_id,
                    po.partner_id as partner_id,
                    po.user_id as user_id,
                    po.company_id as company_id,
                    po.fiscal_position_id as fiscal_position_id,
                    l.product_id,
                    l.work_type_id,
                    l.project_id,
                    l.task_id,
                    p.product_tmpl_id,
                    t.categ_id as category_id,
                    c.currency_id,
                    t.uom_id as product_uom,
                    extract(epoch from age(po.date_approve,po.date_order))/(24*60*60)::decimal(16,2) as delay,
                    extract(epoch from age(l.date_planned,po.date_order))/(24*60*60)::decimal(16,2) as delay_pass,
                    count(*) as nbr_lines,
                    sum(l.price_total / COALESCE(po.currency_rate, 1.0))::decimal(16,2) * account_currency_table.rate as price_total,
                    (sum(l.product_qty * l.price_unit / COALESCE(po.currency_rate, 1.0))/NULLIF(sum(l.product_qty/line_uom.factor*product_uom.factor),0.0))::decimal(16,2) * account_currency_table.rate as price_average,
                    partner.country_id as country_id,
                    partner.commercial_partner_id as commercial_partner_id,
                    sum(p.weight * l.product_qty/line_uom.factor*product_uom.factor) as weight,
                    sum(p.volume * l.product_qty/line_uom.factor*product_uom.factor) as volume,
                    sum(l.price_subtotal / COALESCE(po.currency_rate, 1.0))::decimal(16,2) * account_currency_table.rate as untaxed_total,
                    sum(l.product_qty / line_uom.factor * product_uom.factor) as qty_ordered,
                    sum(l.qty_received / line_uom.factor * product_uom.factor) as qty_received,
                    sum(l.qty_invoiced / line_uom.factor * product_uom.factor) as qty_billed,
                    case when t.purchase_method = 'purchase'
                         then sum(l.product_qty / line_uom.factor * product_uom.factor) - sum(l.qty_invoiced / line_uom.factor * product_uom.factor)
                         else sum(l.qty_received / line_uom.factor * product_uom.factor) - sum(l.qty_invoiced / line_uom.factor * product_uom.factor)
                    end as qty_to_be_billed
            """
        )

    # def _from(self) -> SQL:
    #     return SQL(
    #         """
    #         FROM
    #         purchase_order_line l
    #             join purchase_order po on (l.order_id=po.id)
    #             join res_partner partner on po.partner_id = partner.id
    #                 left join product_product p on (l.product_id=p.id)
    #                     left join product_template t on (p.product_tmpl_id=t.id)
    #             left join res_company C ON C.id = po.company_id
    #             left join uom_uom line_uom on (line_uom.id=l.product_uom)
    #             left join uom_uom product_uom on (product_uom.id=t.uom_id)
    #             left join %(currency_table)s ON account_currency_table.company_id = po.company_id
    #         """,
    #         currency_table=self.env['res.currency']._get_simple_currency_table(self.env.companies),
    #     )

    # def _where(self) -> SQL:
    #     return SQL(
    #         """
    #         WHERE
    #             l.display_type IS NULL
    #         """
    #     )

    def _group_by(self) -> SQL:
        return SQL(
            """
            GROUP BY
                po.company_id,
                po.user_id,
                po.partner_id,
                line_uom.factor,
                c.currency_id,
                l.price_unit,
                po.date_approve,
                l.date_planned,
                l.product_uom,
                po.dest_address_id,
                po.fiscal_position_id,
                l.product_id,
                l.work_type_id,
                l.project_id,
                l.task_id,
                p.product_tmpl_id,
                t.categ_id,
                po.date_order,
                po.state,
                line_uom.uom_type,
                line_uom.category_id,
                t.uom_id,
                t.purchase_method,
                line_uom.id,
                product_uom.factor,
                partner.country_id,
                partner.commercial_partner_id,
                po.id,
                account_currency_table.rate                
            """
        )

    # def _read_group_select(self, aggregate_spec: str, query: Query) -> SQL:
    #     """ This override allows us to correctly calculate the average price of products. """
    #     if aggregate_spec != 'price_average:avg':
    #         return super()._read_group_select(aggregate_spec, query)
    #     return SQL(
    #         'SUM(%(f_price)s * %(f_qty)s) / SUM(%(f_qty)s)',
    #         f_qty=self._field_to_sql(self._table, 'qty_ordered', query),
    #         f_price=self._field_to_sql(self._table, 'price_average', query),
    #     )