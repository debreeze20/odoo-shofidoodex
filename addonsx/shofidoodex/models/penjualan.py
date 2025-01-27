from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, UserError
try:
    import qrcode
except ImportError:
    qrcode = None
try:
    import base64
except ImportError:
    base64 = None
from io import BytesIO


class DoodexPenjualan(models.Model):
    _name = 'doodex.penjualan'
    _description = 'model.technical.name'
    _rec_name = 'referensi'

    referensi = fields.Char(
        string="No. Reference",
        required=True, copy=False, readonly=True,
        default=lambda self: _('New'))
    
    
    # referensi = fields.Char(string='No. Referensi')
    membership = fields.Boolean(string='Apakah member?', default=False)
    nama_nonmember = fields.Many2one(comodel_name='res.partner', string='Non Member')
    pelanggan_id = fields.Many2one(comodel_name='doodex.pelanggan', string='ID Pelanggan')
    id_member_penjualan = fields.Char(compute='_compute_id_member_penjualan', string='Nama member')
    tgl_transaksi = fields.Datetime(string='Tanggal transaksi', default=fields.Datetime.now())
    detailpenjualan_ids = fields.One2many(comodel_name='doodex.detailpenjualan', inverse_name='penjualan_id', string='penjualan')
    total_bayar = fields.Integer(compute='_compute_total_bayar', string='total bayar', store=True)    
    total_qty = fields.Char(compute='_compute_total_qty', string='total_qty')  
    qr_code = fields.Char(compute='_compute_qr_code', string='QR code')
    state = fields.Selection(selection=[('draft', 'Draft'), ('confirm', 'Confirm'), ('done', 'Done'), ('cancel', '')], string='state', readonly=True, default="draft", required=True)


    # action button header
    @api.depends('referensi')
    def action_confirm(self):
        self.write({'state':'confirm'})
    def action_done(self):
        self.write({'state':'done'})
    def action_cancel(self):
        self.write({'state':'cancel'})
    def action_draft(self):
        self.write({'state':'draft'})

    

    #create QR Code
    @api.depends('referensi')
    def _compute_qr_code(self):
        for rec in self:
            if qrcode and base64:
                qr = qrcode.QRCode(version=1, error_correction=qrcode.constants.ERROR_CORRECT_L,box_size=3, border=4)
                qr.add_data(rec.referensi)
                qr.make(fit=True)
                img = qr.make_image()
                temp = BytesIO()
                img.save(temp, format="PNG")
                qr_image = base64.b64encode(temp.getvalue())
                rec.update({'qr_code':qr_image})
    

    #
    @api.depends('detailpenjualan_ids')
    def _compute_total_bayar(self):
        # x = []
        for rec in self:
            total = sum(self.env['doodex.detailpenjualan'].search([('penjualan_id','=',rec.id)]).mapped('subtotal')) 

            rec.total_bayar = total
        
        

    @api.depends('detailpenjualan_ids.qty')
    def _compute_total_qty(self):

        for rec in self:
            total_qty = sum(rec.detailpenjualan_ids.mapped('qty')) 
            rec.total_qty = total_qty


    
    @api.depends('pelanggan_id')
    def _compute_id_member_penjualan(self):
        for rec in self:
            rec.id_member_penjualan = rec.pelanggan_id.name


    #def create, create auto genereate referensi code for penjualan
    @api.model
    def create(self,vals):   
        if vals.get('referensi', _("New")) == _("New"):                
           vals['referensi'] = self.env['ir.sequence'].next_by_code('referensi.penjualan') or _("New")         
        record = super(DoodexPenjualan, self).create(vals)
        return record
    

    # create def unlink
    def unlink(self):
        if self.filtered(lambda line:line.state != 'draft'):
            raise ValidationError('Tidak dapat menghapus selain draft')
        # if self.state not in ('draft','cancel'):
        #     raise UserError(_("You can't delete"))
        elif self.detailpenjualan_ids:
            a = []
            for detail in self:
                a = self.env['doodex.detailpenjualan'].search([('penjualan_id', '=', detail.id)])
            print(a)
            for barang in a:
                barang.barang_id.stok += barang.qty
        record = super(DoodexPenjualan, self).unlink()


    # create def write for penjualan and pembelian    
    def write(self,vals):
        for rec in self:
            a = self.env['doodex.detailpenjualan'].search([('penjualan_id','=',rec.id)])
            print(a)
            for data in a:
                print(str(data.barang_id.nama_barang)+" "+str(data.qty))
                data.barang_id.stok += data.qty
        record = super(DoodexPenjualan, self).write(vals)
        for recc in self:
            b = self.env['doodex.detailpenjualan'].search([('penjualan_id','=',recc.id)])
            for databaru in b:
                print(str(databaru.barang_id.nama_barang)+" "+str(databaru.qty))
                databaru.barang_id.stok -= databaru.qty
        return record


class DoodexDetailPenjualan (models.Model):
    _name = 'doodex.detailpenjualan'
    _description = 'model.technical.name'

    penjualan_id = fields.Many2one(comodel_name='doodex.penjualan', string='Penjualan')
    barang_id = fields.Many2one(comodel_name='barang.doodex', string='Nama Barang')
    harga_satuan = fields.Integer(string='Harga satuan')
    qty = fields.Integer(string='Quantity')
    subtotal = fields.Integer(compute='_compute_subtotal', string='subtotal')
    subtotal_qty = fields.Integer(compute='_compute_subtotal_qty', string='subtotal_qty')
    


    # create for sum of quantity    
    @api.depends('harga_satuan', 'qty')
    def _compute_subtotal(self):
        for rec in self:
            rec.subtotal = rec.harga_satuan*rec.qty


    @api.onchange('barang_id')
    def _onchange_barang(self):
        self.harga_satuan = self.barang_id.harga
    
    
    @api.constrains('qty')
    def _checkQuantity(self):
        for record in self:
            if record.qty < 1:
                raise ValidationError('masa beli {} cuma {} pcs.'.format(record.barang_id.nama_barang, record.qty))
            elif record.qty > record.barang_id.stok :
                raise ValidationError('Stok {} tidak cukup atau melebihi stok kami.'.format(record.barang_id.nama_barang))
            # record.qty = record.barang_id.stok

    @api.model
    def create (self, vals): 
        record = super(DoodexDetailPenjualan, self).create(vals)
        if record.qty:
            self.env['barang.doodex'].search([('id', '=', record.barang_id.id)]).write({'stok' : record.barang_id.stok-record.qty})
        return record