# -*- coding: utf-8 -*-
from odoo import models, fields, api


class ResUsers(models.Model):
    _inherit = "res.users"

    can_view_audit_logs = fields.Boolean(
        string="Can View Audit Logs",
        compute="_compute_can_view_audit_logs",
        inverse="_inverse_can_view_audit_logs",
        store=True,
    )

    @api.depends('groups_id')
    def _compute_can_view_audit_logs(self):
        group = self.env.ref('mdx_audit_lockdown.group_audit_viewer', raise_if_not_found=False)
        for user in self:
            user.can_view_audit_logs = bool(group and group in user.groups_id)

    def _inverse_can_view_audit_logs(self):
        group = self.env.ref('mdx_audit_lockdown.group_audit_viewer', raise_if_not_found=False)
        if not group:
            return
        for user in self:
            if user.can_view_audit_logs and group not in user.groups_id:
                user.groups_id = [(4, group.id)]
            if not user.can_view_audit_logs and group in user.groups_id:
                user.groups_id = [(3, group.id)]