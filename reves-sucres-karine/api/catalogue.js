// GET /api/catalogue — la carte et les informations utiles pour commander.
import { q, getShop } from '../lib/db.js';
import { handler, send, allow, todayParis, addDays } from '../lib/http.js';
import { PRODUCT_COLS } from '../lib/orders.js';

export default handler(async (req, res) => {
  allow(req, 'GET');
  const [products, shop] = await Promise.all([
    q(`SELECT ${PRODUCT_COLS} FROM kb_products WHERE available ORDER BY position, id`),
    getShop(),
  ]);
  send(res, 200, {
    products,
    shop: {
      orders_open: shop.orders_open,
      closed_message: shop.closed_message,
      delivery: shop.delivery,
      slots: shop.slots,
      notice: shop.notice,
      lead_days: shop.lead_days,
      min_date: addDays(todayParis(), Number(shop.lead_days) || 0),
      max_date: addDays(todayParis(), 365),
    },
  });
});
