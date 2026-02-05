const path = require('path');
const express = require('express');
const Datastore = require('nedb-promises');

const app = express();
const PORT = process.env.PORT || 3000;

app.use(express.json());
app.use(express.static(path.join(__dirname, 'public')));

// Datastores
const db = {
  products: Datastore.create({ filename: path.join(__dirname, 'data', 'products.db'), autoload: true }),
  carts: Datastore.create({ filename: path.join(__dirname, 'data', 'carts.db'), autoload: true }),
  orders: Datastore.create({ filename: path.join(__dirname, 'data', 'orders.db'), autoload: true })
};

function newId(prefix = 'id') {
  return `${prefix}_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 8)}`;
}

function computeShipping(subtotal) {
  // Demo rule: free shipping for subtotal >= 500, else flat 49
  return subtotal >= 500 ? 0 : 49;
}

async function seedIfEmpty() {
  const productCount = await db.products.count({});
  if (productCount === 0) {
    const now = Date.now();
    const sample = [
      { id: 'p1', name: 'Kids T-shirt', price: 199, imageUrl: 'https://picsum.photos/seed/p1/200/200', stock: 20, isActive: true, createdAt: now, updatedAt: now },
      { id: 'p2', name: 'Baby Shoes', price: 399, imageUrl: 'https://picsum.photos/seed/p2/200/200', stock: 5, isActive: true, createdAt: now, updatedAt: now },
      { id: 'p3', name: 'Toy Car', price: 149, imageUrl: 'https://picsum.photos/seed/p3/200/200', stock: 0, isActive: true, createdAt: now, updatedAt: now },
      { id: 'p4', name: 'Story Book', price: 249, imageUrl: 'https://picsum.photos/seed/p4/200/200', stock: 10, isActive: false, createdAt: now, updatedAt: now }
    ];
    await db.products.insert(sample);
  }

  const cartCount = await db.carts.count({ buyerId: 'buyer-1' });
  if (cartCount === 0) {
    const items = [
      { id: newId('cart'), buyerId: 'buyer-1', productId: 'p1', quantity: 2, addedAt: Date.now() },
      { id: newId('cart'), buyerId: 'buyer-1', productId: 'p2', quantity: 1, addedAt: Date.now() },
      { id: newId('cart'), buyerId: 'buyer-1', productId: 'p3', quantity: 1, addedAt: Date.now() }, // out of stock
      { id: newId('cart'), buyerId: 'buyer-1', productId: 'p4', quantity: 1, addedAt: Date.now() }  // inactive
    ];
    await db.carts.insert(items);
  }
}

function joinCartItems(cartItems, productsById) {
  return cartItems.map(ci => {
    const p = productsById.get(ci.productId);
    let selectable = false;
    let notSelectableReason = '';
    if (!p) {
      selectable = false; notSelectableReason = 'Product no longer available';
    } else if (!p.isActive) {
      selectable = false; notSelectableReason = 'Product inactive';
    } else if (p.stock <= 0) {
      selectable = false; notSelectableReason = 'Out of stock';
    } else if (ci.quantity > p.stock) {
      selectable = false; notSelectableReason = `Only ${p.stock} left`;
    } else {
      selectable = true;
    }
    return {
      id: ci.id,
      buyerId: ci.buyerId,
      productId: ci.productId,
      quantity: ci.quantity,
      addedAt: ci.addedAt,
      product: p ? { id: p.id, name: p.name, price: p.price, imageUrl: p.imageUrl, stock: p.stock, isActive: p.isActive } : null,
      selectable,
      notSelectableReason
    };
  });
}

async function loadProductsMap(ids = null) {
  const query = ids ? { id: { $in: ids } } : {};
  const products = await db.products.find(query);
  const map = new Map();
  products.forEach(p => map.set(p.id, p));
  return map;
}

async function buildQuote(buyerId, cartItemIds) {
  const cartItems = await db.carts.find({ buyerId, id: { $in: cartItemIds } });
  const productIds = [...new Set(cartItems.map(ci => ci.productId))];
  const productsById = await loadProductsMap(productIds);
  const joined = joinCartItems(cartItems, productsById);

  const invalid = joined.filter(j => !j.selectable).map(j => ({ cartItemId: j.id, reason: j.notSelectableReason }));
  if (invalid.length > 0) {
    return { ok: false, invalid };
  }

  const lineItems = joined.map(j => ({
    cartItemId: j.id,
    productId: j.productId,
    name: j.product.name,
    price: j.product.price,
    quantity: j.quantity,
    lineTotal: j.product.price * j.quantity,
    imageUrl: j.product.imageUrl
  }));
  const subtotal = lineItems.reduce((sum, li) => sum + li.lineTotal, 0);
  const shippingFee = computeShipping(subtotal);
  const total = subtotal + shippingFee;
  return { ok: true, lineItems, subtotal, shippingFee, total };
}

// Routes
app.get('/api/health', (req, res) => res.json({ status: 'ok' }));

app.get('/api/cart', async (req, res) => {
  try {
    const buyerId = req.query.buyerId;
    if (!buyerId) return res.status(400).json({ error: 'buyerId is required' });
    const cartItems = await db.carts.find({ buyerId });
    const productIds = [...new Set(cartItems.map(ci => ci.productId))];
    const productsById = await loadProductsMap(productIds);
    const data = joinCartItems(cartItems, productsById);
    res.json({ items: data });
  } catch (e) {
    console.error(e);
    res.status(500).json({ error: 'Failed to load cart' });
  }
});

app.patch('/api/cart/:id', async (req, res) => {
  try {
    const id = req.params.id;
    const { quantity } = req.body || {};
    if (!Number.isInteger(quantity) || quantity < 1) {
      return res.status(400).json({ error: 'quantity must be an integer >= 1' });
    }
    const existing = await db.carts.findOne({ id });
    if (!existing) return res.status(404).json({ error: 'Cart item not found' });
    // Cap quantity at product stock if product exists
    const product = await db.products.findOne({ id: existing.productId });
    let newQty = quantity;
    if (product && product.stock > 0) newQty = Math.min(quantity, product.stock);
    await db.carts.update({ id }, { $set: { quantity: newQty } }, {});

    const updatedDoc = await db.carts.findOne({ id });
    const productsById = await loadProductsMap([existing.productId]);
    const [joined] = joinCartItems([updatedDoc], productsById);
    res.json(joined);
  } catch (e) {
    console.error(e);
    res.status(500).json({ error: 'Failed to update quantity' });
  }
});

app.delete('/api/cart/:id', async (req, res) => {
  try {
    const id = req.params.id;
    await db.carts.remove({ id }, { multi: false });
    res.json({ success: true });
  } catch (e) {
    console.error(e);
    res.status(500).json({ error: 'Failed to remove item' });
  }
});

app.post('/api/checkout/quote', async (req, res) => {
  try {
    const { buyerId, cartItemIds } = req.body || {};
    if (!buyerId || !Array.isArray(cartItemIds) || cartItemIds.length === 0) {
      return res.status(400).json({ error: 'buyerId and non-empty cartItemIds[] are required' });
    }
    const quote = await buildQuote(buyerId, cartItemIds);
    if (!quote.ok) return res.status(400).json(quote);
    res.json(quote);
  } catch (e) {
    console.error(e);
    res.status(500).json({ error: 'Failed to create quote' });
  }
});

app.post('/api/orders', async (req, res) => {
  try {
    const { buyerId, cartItemIds } = req.body || {};
    if (!buyerId || !Array.isArray(cartItemIds) || cartItemIds.length === 0) {
      return res.status(400).json({ error: 'buyerId and non-empty cartItemIds[] are required' });
    }
    const quote = await buildQuote(buyerId, cartItemIds);
    if (!quote.ok) return res.status(400).json(quote);

    const order = {
      id: newId('ord'),
      buyerId,
      items: quote.lineItems,
      subtotal: quote.subtotal,
      shippingFee: quote.shippingFee,
      total: quote.total,
      status: 'TO_PAY',
      createdAt: Date.now(),
      updatedAt: Date.now()
    };
    await db.orders.insert(order);
    await db.carts.remove({ buyerId, id: { $in: cartItemIds } }, { multi: true });

    res.status(201).json({ ok: true, order });
  } catch (e) {
    console.error(e);
    res.status(500).json({ error: 'Failed to create order' });
  }
});

// Dev helper to seed/reset (idempotent)
app.post('/api/dev/seed', async (req, res) => {
  try {
    await seedIfEmpty();
    res.json({ ok: true });
  } catch (e) {
    console.error(e);
    res.status(500).json({ error: 'Failed to seed' });
  }
});

app.get('/', (req, res) => {
  res.sendFile(path.join(__dirname, 'public', 'cart.html'));
});

seedIfEmpty().then(() => {
  app.listen(PORT, () => console.log(`Server listening on http://localhost:${PORT}`));
});
