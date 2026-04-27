# -*- coding: utf-8 -*-
from odoo import fields, models


class SkyPlannerSimulateWizard(models.TransientModel):
    """
    Simulate wizard — shows planned date preview before Apply.
    Fetches /jobs?job_parts=true and renders diff without writing to Odoo.
    """
    _name = 'skyplanner.simulate.wizard'
    _description = 'SkyPlanner Simulate Plan'

    production_id = fields.Many2one(
        'mrp.production',
        string='Manufacturing Order',
        required=True,
        readonly=True,
    )
    result_html = fields.Html(
        string='Plan Preview',
        readonly=True,
        sanitize=False,
    )
    state = fields.Selection(
        selection=[('draft', 'Loading'), ('done', 'Preview Ready'), ('error', 'Error')],
        default='draft',
    )
    error_message = fields.Text(readonly=True)

    def action_load_plan(self):
        """Fetch plan from SkyPlanner and populate result_html."""
        self.ensure_one()
        planner = self.env['skyplanner.planner']
        result = planner.fetch_and_apply(
            production_id=self.production_id.id,
            mode='simulate',
        )
        if result.get('error'):
            self.state = 'error'
            self.error_message = result.get('message')
        else:
            self.state = 'done'
            self.result_html = self._render_preview(result.get('changes', []))
        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'view_mode': 'form',
            'res_id': self.id,
            'target': 'new',
        }

    def _render_preview(self, changes):
        """Build HTML table showing current vs planned dates."""
        if not changes:
            return '<p>No scheduling changes found.</p>'
        rows = ''.join(
            f'<tr>'
            f'<td>{c["wo_name"]}</td>'
            f'<td>{c["workcenter"]}</td>'
            f'<td>{c["current_start"] or "—"}</td>'
            f'<td>{c["planned_start"]}</td>'
            f'<td>{c["current_end"] or "—"}</td>'
            f'<td>{c["planned_end"]}</td>'
            f'<td>{"⚠ Protected" if c.get("protected") else "Will update"}</td>'
            f'</tr>'
            for c in changes
        )
        return f'''
        <table class="table table-sm table-bordered">
            <thead class="table-light">
                <tr>
                    <th>Work Order</th><th>Workcenter</th>
                    <th>Current Start</th><th>Planned Start</th>
                    <th>Current End</th><th>Planned End</th>
                    <th>Action</th>
                </tr>
            </thead>
            <tbody>{rows}</tbody>
        </table>
        '''
