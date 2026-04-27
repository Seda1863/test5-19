# -*- coding: utf-8 -*-

from odoo import models, fields, api
from odoo import Command, models
from odoo.tools import float_compare, float_is_zero
from odoo.exceptions import UserError, ValidationError

class MdxInhSaleOrder(models.Model):
    _inherit = 'sale.order'

    # filtered_partner_ids = fields.Many2many('res.partner', compute='_compute_filtered_partner_ids', store=False)

    # @api.depends('state')
    # def _compute_filtered_partner_ids(self):
    #     for record in self:
    #         if record.state == 'draft':
    #             record.filtered_partner_ids = self.env['res.partner'].search([('parent_id', '=', False), ('is_customer', '=', True)])
    #         else:
    #             record.filtered_partner_ids = self.env['res.partner'].search([('parent_id', '=', False)])

class MdxInhSaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    def get_stock_moves_link_invoice(self):
        moves_linked = self.env["stock.move"]
        to_invoice = self.qty_to_invoice
        for stock_move in self.move_ids.sorted(
            lambda m: (m.write_date, m.id), reverse=True
        ):
            if (
                stock_move.state != "done"
                or stock_move.scrapped
                or (
                    stock_move.location_dest_id.usage != "customer"
                    and (
                        stock_move.location_id.usage != "customer"
                        or not stock_move.to_refund
                    )
                )
            ):
                continue
            if not stock_move.invoice_line_ids:
                to_invoice -= (
                    stock_move.quantity
                    if not stock_move.to_refund
                    else -stock_move.quantity
                )
                moves_linked += stock_move
                continue
            elif float_is_zero(
                to_invoice, precision_rounding=self.product_uom.rounding
            ):
                break
            to_invoice -= (
                stock_move.quantity
                if not stock_move.to_refund
                else -stock_move.quantity
            )
            moves_linked += stock_move
        return moves_linked

    def _prepare_invoice_line(self, **optional_values):
        vals = super()._prepare_invoice_line(**optional_values)
        stock_moves = self.get_stock_moves_link_invoice()
        # Invoice returned moves marked as to_refund
        if (
            float_compare(
                self.qty_to_invoice, 0.0, precision_rounding=self.currency_id.rounding
            )
            < 0
        ):
            stock_moves = stock_moves.filtered("to_refund")
        vals["move_line_ids"] = [Command.set(stock_moves.ids)]
        return vals