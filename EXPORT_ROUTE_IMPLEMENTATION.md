# Export Report Backend Implementation Guide

The export buttons in `admin/reports.html` now properly call the backend with all necessary parameters. Here's what you need to implement in your Flask backend:

## Required Route

Add this route to your Flask application (typically in your main app file or admin routes):

```python
from flask import send_file, request
import pandas as pd
from io import BytesIO
from datetime import datetime
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter, A4
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet

@app.route('/admin/export-report')
@login_required
def export_report():
    """Export reports in CSV, Excel, or PDF format"""
    
    # Check if user is admin
    if session.get('user_role') != 'admin':
        return jsonify({'error': 'Unauthorized'}), 403
    
    # Get parameters
    format_type = request.args.get('format', 'csv')
    report_type = request.args.get('report_type', 'monthly')
    start_date = request.args.get('start_date', '')
    end_date = request.args.get('end_date', '')
    detailed = request.args.get('detailed', 'false') == 'true'
    
    # Fetch report data (adjust based on your database models)
    # Example data structure
    report_data = {
        'total_sales': get_total_sales(start_date, end_date),
        'total_orders': get_total_orders(start_date, end_date),
        'total_users': get_total_users(),
        'total_products': get_total_products(),
        'top_products': get_top_products(start_date, end_date, limit=10),
        'top_sellers': get_top_sellers(start_date, end_date, limit=10),
        'order_stats': get_order_statistics(start_date, end_date),
        'monthly_sales': get_monthly_sales_data(report_type, start_date, end_date)
    }
    
    # Generate file based on format
    if format_type == 'csv':
        return export_csv(report_data, report_type, detailed)
    elif format_type == 'excel':
        return export_excel(report_data, report_type, detailed)
    elif format_type == 'pdf':
        return export_pdf(report_data, report_type, detailed)
    else:
        return jsonify({'error': 'Invalid format'}), 400


def export_csv(data, report_type, detailed):
    """Export report as CSV"""
    output = BytesIO()
    
    # Create DataFrame with report data
    if detailed:
        # Detailed CSV with multiple sheets worth of data
        df_summary = pd.DataFrame([{
            'Metric': 'Total Sales',
            'Value': f"₱{data['total_sales']:.2f}"
        }, {
            'Metric': 'Total Orders',
            'Value': data['total_orders']
        }, {
            'Metric': 'Total Users',
            'Value': data['total_users']
        }, {
            'Metric': 'Total Products',
            'Value': data['total_products']
        }])
        
        # Write summary
        df_summary.to_csv(output, index=False)
        output.write(b'\n\n')
        
        # Add top products
        if data.get('top_products'):
            output.write(b'Top Products\n')
            df_products = pd.DataFrame(data['top_products'])
            df_products.to_csv(output, index=False)
            output.write(b'\n\n')
        
        # Add top sellers
        if data.get('top_sellers'):
            output.write(b'Top Sellers\n')
            df_sellers = pd.DataFrame(data['top_sellers'])
            df_sellers.to_csv(output, index=False)
    else:
        # Simple summary CSV
        df = pd.DataFrame([{
            'Report Type': report_type.title(),
            'Total Sales': f"₱{data['total_sales']:.2f}",
            'Total Orders': data['total_orders'],
            'Total Users': data['total_users'],
            'Total Products': data['total_products']
        }])
        df.to_csv(output, index=False)
    
    output.seek(0)
    filename = f"report_{report_type}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    
    return send_file(
        output,
        mimetype='text/csv',
        as_attachment=True,
        download_name=filename
    )


def export_excel(data, report_type, detailed):
    """Export report as Excel with multiple sheets"""
    output = BytesIO()
    
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        # Summary Sheet
        df_summary = pd.DataFrame([{
            'Metric': 'Total Sales',
            'Value': data['total_sales']
        }, {
            'Metric': 'Total Orders',
            'Value': data['total_orders']
        }, {
            'Metric': 'Total Users',
            'Value': data['total_users']
        }, {
            'Metric': 'Total Products',
            'Value': data['total_products']
        }])
        df_summary.to_excel(writer, sheet_name='Summary', index=False)
        
        # Top Products Sheet
        if data.get('top_products'):
            df_products = pd.DataFrame(data['top_products'])
            df_products.to_excel(writer, sheet_name='Top Products', index=False)
        
        # Top Sellers Sheet
        if data.get('top_sellers'):
            df_sellers = pd.DataFrame(data['top_sellers'])
            df_sellers.to_excel(writer, sheet_name='Top Sellers', index=False)
        
        # Order Statistics Sheet
        if data.get('order_stats'):
            df_orders = pd.DataFrame([data['order_stats']])
            df_orders.to_excel(writer, sheet_name='Order Stats', index=False)
        
        # Monthly Sales (if available)
        if data.get('monthly_sales'):
            df_monthly = pd.DataFrame(data['monthly_sales'])
            df_monthly.to_excel(writer, sheet_name='Monthly Sales', index=False)
    
    output.seek(0)
    filename = f"report_{report_type}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    
    return send_file(
        output,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        as_attachment=True,
        download_name=filename
    )


def export_pdf(data, report_type, detailed):
    """Export report as PDF"""
    output = BytesIO()
    
    # Create PDF document
    doc = SimpleDocTemplate(output, pagesize=letter)
    elements = []
    styles = getSampleStyleSheet()
    
    # Title
    title = Paragraph(f"<b>Analytics Report - {report_type.title()}</b>", styles['Title'])
    elements.append(title)
    elements.append(Spacer(1, 12))
    
    # Date
    date_str = f"Generated: {datetime.now().strftime('%B %d, %Y at %I:%M %p')}"
    elements.append(Paragraph(date_str, styles['Normal']))
    elements.append(Spacer(1, 20))
    
    # Summary Section
    elements.append(Paragraph("<b>Summary</b>", styles['Heading2']))
    elements.append(Spacer(1, 6))
    
    summary_data = [
        ['Metric', 'Value'],
        ['Total Sales', f"₱{data['total_sales']:.2f}"],
        ['Total Orders', str(data['total_orders'])],
        ['Total Users', str(data['total_users'])],
        ['Total Products', str(data['total_products'])]
    ]
    
    summary_table = Table(summary_data, colWidths=[200, 200])
    summary_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 12),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
        ('GRID', (0, 0), (-1, -1), 1, colors.black)
    ]))
    elements.append(summary_table)
    elements.append(Spacer(1, 20))
    
    # Top Products Section (if detailed)
    if detailed and data.get('top_products'):
        elements.append(Paragraph("<b>Top Products</b>", styles['Heading2']))
        elements.append(Spacer(1, 6))
        
        products_data = [['#', 'Product Name', 'Units Sold', 'Revenue']]
        for i, product in enumerate(data['top_products'][:10], 1):
            products_data.append([
                str(i),
                product.get('name', ''),
                str(product.get('total_sold', 0)),
                f"₱{product.get('total_revenue', 0):.2f}"
            ])
        
        products_table = Table(products_data, colWidths=[30, 200, 80, 100])
        products_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 10),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
            ('GRID', (0, 0), (-1, -1), 1, colors.black)
        ]))
        elements.append(products_table)
    
    # Build PDF
    doc.build(elements)
    output.seek(0)
    
    filename = f"report_{report_type}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
    
    return send_file(
        output,
        mimetype='application/pdf',
        as_attachment=True,
        download_name=filename
    )


# Helper functions (implement based on your models)
def get_total_sales(start_date, end_date):
    # Query your database for total sales
    # Example: Order.query.filter(...).with_entities(func.sum(Order.total_amount)).scalar() or 0
    return 0

def get_total_orders(start_date, end_date):
    # Query your database for total orders
    return 0

def get_total_users():
    # Query your database for total users
    return 0

def get_total_products():
    # Query your database for total products
    return 0

def get_top_products(start_date, end_date, limit=10):
    # Query your database for top products
    return []

def get_top_sellers(start_date, end_date, limit=10):
    # Query your database for top sellers
    return []

def get_order_statistics(start_date, end_date):
    # Query your database for order statistics
    return {'completed': 0, 'pending': 0, 'canceled': 0, 'refunded': 0}

def get_monthly_sales_data(report_type, start_date, end_date):
    # Query your database for monthly sales data
    return []
```

## Required Dependencies

Install these Python packages:

```bash
pip install pandas openpyxl reportlab
```

## Frontend Changes (Already Implemented)

The JavaScript functions in `admin/reports.html` now:
- ✅ Capture current filter parameters (report_type, start_date, end_date)
- ✅ Show loading spinner while generating
- ✅ Open export in new tab/trigger download
- ✅ Reset button state after completion
- ✅ Handle both quick export and detailed export

## Testing

1. Click "Export CSV" - should download a CSV file
2. Click "Export Excel" - should download an XLSX file with multiple sheets
3. Click "Export PDF" - should download a formatted PDF report
4. Test with different date ranges to ensure filters work
5. Test the detailed export buttons for comprehensive reports

## Notes

- The route `/admin/export-report` handles all three formats (CSV, Excel, PDF)
- The `detailed=true` parameter triggers more comprehensive reports
- Files are generated in-memory for efficient download
- Filenames include timestamp for uniqueness
- All exports respect the current filter parameters
