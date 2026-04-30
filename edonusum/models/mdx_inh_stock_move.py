# -*- coding: utf-8 -*-

import datetime
from odoo import models, fields, api, Command
from odoo.exceptions import UserError, ValidationError
import xml.etree.ElementTree as ET

from .mdx_utility_mixin import MdxUtilityMixin

class MdxInhStockMove(models.Model):
    _inherit = 'stock.move'
    
    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        for record in records:
            for line in record.move_line_ids:
                if line.gelen_irsaliye_line_id:
                    line.move_id.purchase_line_id = line.gelen_irsaliye_line_id.ref_po_line_id
        return records
    
    invoice_line_ids = fields.Many2many(
        comodel_name="account.move.line",
        relation="stock_move_invoice_line_rel",
        column1="move_id",
        column2="invoice_line_id",
        string="Invoice Line",
        copy=False,
        readonly=True,
    )

    def write(self, vals):
        """
        User can update any picking in done state, but if this picking already
        invoiced the stock move done quantities can be different to invoice
        line quantities. So to avoid this inconsistency you can not update any
        stock move line in done state and have invoice lines linked.
        """
        if "product_uom_qty" in vals and not self.env.context.get(
            "bypass_stock_move_update_restriction"
        ):
            for move in self:
                if move.state == "done" and move.invoice_line_ids:
                    raise UserError(_("You can not modify an invoiced stock move"))
        res = super().write(vals)
        if vals.get("state", "") == "done":
            stock_moves = self.get_moves_delivery_link_invoice()
            for stock_move in stock_moves.filtered(
                lambda sm: sm.sale_line_id and sm.product_id.invoice_policy == "order"
            ):
                inv_type = stock_move.to_refund and "out_refund" or "out_invoice"
                inv_lines = (
                    self.env["account.move.line"]
                    .sudo()
                    .search(
                        [
                            ("sale_line_ids", "=", stock_move.sale_line_id.id),
                            ("move_id.move_type", "=", inv_type),
                        ]
                    )
                )
                if inv_lines:
                    stock_move.invoice_line_ids = [Command.set(inv_lines.ids)]
        return res

    def get_moves_delivery_link_invoice(self):
        return self.filtered(
            lambda x: x.state == "done"
            and not x.scrapped
            and (
                x.location_id.usage == "internal"
                or (x.location_dest_id.usage == "internal" and x.to_refund)
            )
        )