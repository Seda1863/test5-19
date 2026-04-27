from odoo import models, api
from odoo.exceptions import AccessError

class MdxInhIrCron(models.Model):
    _inherit = 'ir.cron'

    def unlink(self):
        for record in self:
            if record.id == self.env.ref('edonusum.cron_update_license_expiration').id:
                raise AccessError("Bu cron job'u silemezsiniz.")
        return super(MdxInhIrCron, self).unlink()

    def write(self, vals):
        if self.id == self.env.ref('edonusum.cron_update_license_expiration').id:
            raise AccessError("Bu cron job'u düzenleyemezsiniz.")
        return super(MdxInhIrCron, self).write(vals)