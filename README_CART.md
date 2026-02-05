# Selective Checkout Feature
This adds a buyer-side cart where buyers can select specific items to checkout.

## Run
1. Install dependencies
   - PowerShell shim: `cmd /c npm.cmd install`
2. Start server
   - `npm start` (or on PowerShell: `cmd /c npm.cmd start`)
3. Visit `http://localhost:3000/`

## Buyer flow
Cart → select items (single/multi/select all) → Checkout → only selected items are shown on the checkout page → Place Order.

## Notes
- Unchecked items remain in the cart.
- Out-of-stock and inactive items are blocked from selection and from server-side checkout.
- Quantity changes revalidate availability.
- Shipping rule (demo): free if subtotal ≥ 500, else ₱49.
