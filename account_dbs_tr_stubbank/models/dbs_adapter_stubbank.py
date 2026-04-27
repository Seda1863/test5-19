# -*- coding: utf-8 -*-
from odoo import models


class DbsAdapterStubBank(models.AbstractModel):
    _name = 'dbs.adapter.stubbank'
    _description = 'DBS Adapter Stub Bank'
    _inherit = 'dbs.adapter.manual'

    # Simdilik manual adaptorun davranisini kullanir.
    # Gercek bankaya geciste export/import formati burada override edilir.
