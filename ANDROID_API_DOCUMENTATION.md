# Android App API Documentation for QR Code Scanning

## Overview
This document provides the API endpoints that your Android app can use to integrate with the QR code tracking system.

## Base URL
```
http://your-domain.com/api/
```

## Authentication
Currently no authentication required, but you can add API keys later if needed.

## API Endpoints

### 1. Get QR Code Information
**Endpoint:** `GET /api/qr-info/{qr_code}`

**Description:** Get order information by scanning QR code

**Parameters:**
- `qr_code` (path) - The QR code string

**Response:**
```json
{
  "success": true,
  "order_id": 123,
  "tracking_number": "TRK123456789",
  "status": "generated",
  "customer_name": "John Doe",
  "customer_phone": "+639171234567",
  "shipping_address": "123 Main St, City, Country",
  "total_amount": 1500.00,
  "payment_method": "COD",
  "created_at": "2024-12-15T10:30:00",
  "items": [
    {
      "product_name": "Toy Car",
      "quantity": 2,
      "price": 500.00,
      "seller_name": "Jane Seller"
    }
  ]
}
```

**Error Response:**
```json
{
  "success": false,
  "message": "QR Code not found"
}
```

### 2. Scan QR Code (Update Status)
**Endpoint:** `POST /api/qr-scan`

**Description:** Update order status by scanning QR code

**Request Body:**
```json
{
  "qr_code": "KIDS00012320241215143022",
  "scan_type": "pickup",
  "rider_id": 1,
  "scan_notes": "Picked up from seller location"
}
```

**Parameters:**
- `qr_code` (string, required) - The QR code string
- `scan_type` (string, required) - One of: "packing", "pickup", "delivery", "return"
- `rider_id` (integer, required) - ID of the rider scanning
- `scan_notes` (string, optional) - Additional notes

**Response:**
```json
{
  "success": true,
  "message": "QR Code scanned successfully! Status updated to pickup",
  "order_id": 123,
  "order_status": "picked_up",
  "customer_name": "John Doe",
  "customer_phone": "+639171234567",
  "shipping_address": "123 Main St, City, Country"
}
```

**Error Response:**
```json
{
  "success": false,
  "message": "Missing required fields"
}
```

## Scan Types

### 1. Packing (`packing`)
- **When:** Seller packs the order
- **Updates:** Status to "packed", sets packed_at timestamp
- **Notes:** Can include packing notes

### 2. Pickup (`pickup`)
- **When:** Rider picks up order from seller
- **Updates:** Status to "picked_up", sets picked_up_at timestamp
- **Notes:** Can include pickup location or notes

### 3. Delivery (`delivery`)
- **When:** Rider delivers order to customer
- **Updates:** Status to "delivered", sets delivered_at timestamp
- **Notes:** Can include delivery notes or customer signature info

### 4. Return (`return`)
- **When:** Processing a return
- **Updates:** Status to "returned", sets returned_at timestamp
- **Notes:** Can include return reason

## Android App Implementation

### 1. QR Code Scanner
Use a QR code scanning library like:
- ZXing (Zebra Crossing)
- ML Kit Barcode Scanning
- CameraX with ML Kit

### 2. HTTP Requests
Use libraries like:
- Retrofit
- OkHttp
- Volley

### 3. Example Implementation (Kotlin)

```kotlin
// Get QR Code Info
fun getQRCodeInfo(qrCode: String) {
    val apiService = RetrofitClient.getApiService()
    apiService.getQRInfo(qrCode).enqueue(object : Callback<QRInfoResponse> {
        override fun onResponse(call: Call<QRInfoResponse>, response: Response<QRInfoResponse>) {
            if (response.isSuccessful) {
                val qrInfo = response.body()
                // Display order information
                showOrderInfo(qrInfo)
            } else {
                // Handle error
                showError("QR Code not found")
            }
        }
        
        override fun onFailure(call: Call<QRInfoResponse>, t: Throwable) {
            showError("Network error: ${t.message}")
        }
    })
}

// Scan QR Code
fun scanQRCode(qrCode: String, scanType: String, riderId: Int, notes: String = "") {
    val scanRequest = ScanRequest(
        qr_code = qrCode,
        scan_type = scanType,
        rider_id = riderId,
        scan_notes = notes
    )
    
    val apiService = RetrofitClient.getApiService()
    apiService.scanQR(scanRequest).enqueue(object : Callback<ScanResponse> {
        override fun onResponse(call: Call<ScanResponse>, response: Response<ScanResponse>) {
            if (response.isSuccessful) {
                val result = response.body()
                showSuccess("${result?.message}")
            } else {
                showError("Scan failed")
            }
        }
        
        override fun onFailure(call: Call<ScanResponse>, t: Throwable) {
            showError("Network error: ${t.message}")
        }
    })
}
```

### 4. Data Classes (Kotlin)

```kotlin
data class QRInfoResponse(
    val success: Boolean,
    val order_id: Int,
    val tracking_number: String,
    val status: String,
    val customer_name: String,
    val customer_phone: String,
    val shipping_address: String,
    val total_amount: Double,
    val payment_method: String,
    val created_at: String,
    val items: List<OrderItem>
)

data class OrderItem(
    val product_name: String,
    val quantity: Int,
    val price: Double,
    val seller_name: String
)

data class ScanRequest(
    val qr_code: String,
    val scan_type: String,
    val rider_id: Int,
    val scan_notes: String
)

data class ScanResponse(
    val success: Boolean,
    val message: String,
    val order_id: Int,
    val order_status: String,
    val customer_name: String,
    val customer_phone: String,
    val shipping_address: String
)
```

## Workflow for Riders

### 1. Pickup Process
1. **Scan QR Code** → Get order information
2. **Verify Details** → Check customer name, address, items
3. **Confirm Pickup** → Scan again with scan_type="pickup"
4. **Add Notes** → Include any pickup notes

### 2. Delivery Process
1. **Navigate to Address** → Use shipping_address from API
2. **Contact Customer** → Use customer_phone from API
3. **Deliver Package** → Scan QR code with scan_type="delivery"
4. **Add Delivery Notes** → Include delivery confirmation or issues

### 3. Return Process
1. **Scan QR Code** → Get order information
2. **Process Return** → Scan with scan_type="return"
3. **Add Return Notes** → Include return reason

## Error Handling

### Common Error Codes
- **400** - Bad Request (missing required fields)
- **404** - QR Code not found
- **500** - Server error

### Error Response Format
```json
{
  "success": false,
  "message": "Error description"
}
```

## Testing

### Test QR Codes
You can test with sample QR codes from your database:
```sql
SELECT qr_code FROM order_label LIMIT 5;
```

### Test Endpoints
Use tools like Postman or curl to test:

```bash
# Get QR Info
curl -X GET "http://your-domain.com/api/qr-info/KIDS00012320241215143022"

# Scan QR Code
curl -X POST "http://your-domain.com/api/qr-scan" \
  -H "Content-Type: application/json" \
  -d '{
    "qr_code": "KIDS00012320241215143022",
    "scan_type": "pickup",
    "rider_id": 1,
    "scan_notes": "Test pickup"
  }'
```

## Security Considerations

1. **Rate Limiting** - Consider implementing rate limiting
2. **API Keys** - Add API key authentication if needed
3. **HTTPS** - Use HTTPS in production
4. **Input Validation** - Validate all inputs on server side
5. **Logging** - All scans are logged with IP and user agent

## Future Enhancements

1. **Real-time Updates** - WebSocket for real-time status updates
2. **Push Notifications** - Notify customers of status changes
3. **GPS Tracking** - Track rider location during delivery
4. **Photo Upload** - Allow riders to upload delivery photos
5. **Digital Signatures** - Capture customer signatures

---

## Support

For any issues or questions about the API, contact the development team.

**API Version:** 1.0  
**Last Updated:** December 2024
