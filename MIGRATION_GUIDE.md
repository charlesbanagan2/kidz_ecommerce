# Database Migration Guide

## ⚠️ IMPORTANT: Safe Database Updates

**NEVER use `DROP TABLE` or `DROP DATABASE` in production!**

This project now uses Flask-Migrate for safe database updates that preserve existing data.

## Installation

1. Install required packages:
```bash
pip install -r requirements.txt
```

## Migration Commands

### For New Installations
```bash
python migrate_db.py init
python migrate_db.py migrate "Initial migration"
python migrate_db.py upgrade
```

### For Existing Databases (Adding New Columns)
```bash
python migrate_db.py migrate "Add notification system"
python migrate_db.py upgrade
```

### Mark Database as Up-to-Date (if no migrations needed)
```bash
python migrate_db.py stamp
```

## Manual Migration Commands

If you prefer using Flask-Migrate directly:

```bash
# Initialize migration repository
flask db init

# Create migration
flask db migrate -m "Add new columns"

# Apply migrations
flask db upgrade

# Mark as up-to-date
flask db stamp head
```

## What Changed

### Before (DANGEROUS):
```python
db.drop_all()  # ❌ DELETES ALL DATA!
db.create_all()
```

### After (SAFE):
```python
db.create_all()  # ✅ Only creates if doesn't exist
# Use Flask-Migrate for schema changes
```

## Benefits

- ✅ **Preserves existing data**
- ✅ **Safe for production**
- ✅ **Automatic schema updates**
- ✅ **Rollback capability**
- ✅ **Version control for database changes**

## Adding New Columns

When you add new columns to models:

1. Update the model in `app.py`
2. Create migration: `python migrate_db.py migrate "Add new column"`
3. Apply migration: `python migrate_db.py upgrade`

The migration will automatically generate `ALTER TABLE` statements instead of dropping tables.

