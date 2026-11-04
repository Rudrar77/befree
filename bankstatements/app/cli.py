"""Flask CLI commands for database management, seeding, training, and utilities."""

from __future__ import annotations

import os
import shutil
import time
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
import click
from flask import Flask, current_app
from flask.cli import with_appcontext

from app.extensions import db


def ensure_classification_schema() -> None:
    """Add newer classification_rules columns on existing SQLite databases."""
    from sqlalchemy import inspect, text

    inspector = inspect(db.engine)
    if "classification_rules" not in inspector.get_table_names():
        db.create_all()
        return
    cols = {c["name"] for c in inspector.get_columns("classification_rules")}
    if "direction" not in cols:
        db.session.execute(
            text("ALTER TABLE classification_rules ADD COLUMN direction VARCHAR(10) DEFAULT 'any'")
        )
        db.session.commit()


def seed_default_data(*, echo: bool = True) -> None:
    """Idempotently seed default categories and classification rules."""
    from app.classification.seed_catalog import load_seed_rules
    from app.models.category import Category
    from app.models.classification_rule import ClassificationRule
    from app.services.pretrained_classifier import MODEL_CATEGORIES

    def _log(message: str) -> None:
        if echo:
            click.echo(message)

    ensure_classification_schema()

    categories_data: list[dict] = [
        {"name": "Food & Dining", "is_system": True, "is_transfer": False, "color": "#EF4444"},
        {"name": "Transportation", "is_system": True, "is_transfer": False, "color": "#F59E0B"},
        {"name": "Shopping", "is_system": True, "is_transfer": False, "color": "#8B5CF6"},
        {"name": "Salary", "is_system": True, "is_transfer": False, "color": "#10B981"},
        {"name": "Utilities", "is_system": True, "is_transfer": False, "color": "#3B82F6"},
        {"name": "Entertainment", "is_system": True, "is_transfer": False, "color": "#EC4899"},
        {"name": "ATM Withdrawal", "is_system": True, "is_transfer": False, "color": "#F97316"},
        {"name": "Loan & EMI", "is_system": True, "is_transfer": False, "color": "#DC2626"},
        {"name": "Fuel", "is_system": True, "is_transfer": False, "color": "#78716C"},
        {"name": "Healthcare", "is_system": True, "is_transfer": False, "color": "#14B8A6"},
        {"name": "Investment", "is_system": True, "is_transfer": False, "color": "#6366F1"},
        {"name": "Transfers", "is_system": True, "is_transfer": True, "color": "#64748B"},
        {"name": "Refunds & Reversals", "is_system": True, "is_transfer": False, "color": "#22C55E"},
        {"name": "Cash Deposit", "is_system": True, "is_transfer": False, "color": "#84CC16"},
        {"name": "Bank Charges & Fees", "is_system": True, "is_transfer": False, "color": "#A8A29E"},
        {"name": "Donations & Charity", "is_system": True, "is_transfer": False, "color": "#F43F5E"},
        {"name": "Education", "is_system": True, "is_transfer": False, "color": "#0EA5E9"},
        {"name": "Insurance", "is_system": True, "is_transfer": False, "color": "#7C3AED"},
        {"name": "Interest Income", "is_system": True, "is_transfer": False, "color": "#059669"},
        {"name": "Rent & Housing", "is_system": True, "is_transfer": False, "color": "#D97706"},
        {"name": "Taxes", "is_system": True, "is_transfer": False, "color": "#B91C1C"},
        {"name": "Travel & Hotels", "is_system": True, "is_transfer": False, "color": "#0284C7"},
        {"name": "Uncategorized", "is_system": True, "is_transfer": False, "color": "#6B7280"},
        {"name": "Needs Review", "is_system": True, "is_transfer": False, "color": "#FBBF24"},
    ]
    model_category_colors = {
        "Food & Dining": "#EF4444",
        "Shopping": "#8B5CF6",
        "Transport": "#F59E0B",
        "Utilities": "#3B82F6",
        "Entertainment": "#EC4899",
        "Salary": "#10B981",
        "Freelance / Business Income": "#22C55E",
        "Rent": "#D97706",
        "Investment": "#6366F1",
        "Cash Withdrawal": "#F97316",
        "Bank Charges": "#A8A29E",
        "Credit Card Payment": "#DC2626",
        "Cashback / Rewards": "#84CC16",
        "Healthcare": "#14B8A6",
        "Insurance": "#7C3AED",
        "Fitness": "#06B6D4",
        "Interest Income": "#059669",
        "Charity/Donation": "#F43F5E",
        "Transfer": "#64748B",
        "Other": "#6B7280",
    }
    categories_data.extend(
        {
            "name": name,
            "is_system": True,
            "is_transfer": name == "Transfer",
            "color": model_category_colors[name],
        }
        for name in MODEL_CATEGORIES
    )

    category_map: dict[str, Category] = {}

    for cat_data in categories_data:
        existing = db.session.query(Category).filter_by(name=cat_data["name"]).first()
        if existing is None:
            category = Category(**cat_data)
            db.session.add(category)
            db.session.flush()
            category_map[cat_data["name"]] = category
            _log(f"  + Created category: {cat_data['name']}")
        else:
            category_map[cat_data["name"]] = existing
            _log(f"  = Category exists: {cat_data['name']}")

    rules_data = load_seed_rules()

    created_cnt = 0
    updated_cnt = 0
    skipped_cnt = 0
    for r_data in rules_data:
        cat_name = r_data["category"]
        cat_obj = category_map.get(cat_name)
        if not cat_obj:
            skipped_cnt += 1
            continue
        existing = (
            db.session.query(ClassificationRule)
            .filter_by(keyword=r_data["keyword"], category_id=cat_obj.id)
            .first()
        )
        direction = r_data.get("direction", "any")
        if existing is None:
            db.session.add(
                ClassificationRule(
                    category_id=cat_obj.id,
                    keyword=r_data["keyword"],
                    match_type=r_data["match_type"],
                    priority=r_data["priority"],
                    direction=direction,
                    is_active=True,
                    is_user_defined=False,
                )
            )
            created_cnt += 1
        else:
            changed = False
            if existing.match_type != r_data["match_type"]:
                existing.match_type = r_data["match_type"]
                changed = True
            if existing.priority != r_data["priority"]:
                existing.priority = r_data["priority"]
                changed = True
            if (existing.direction or "any") != direction:
                existing.direction = direction
                changed = True
            if changed:
                updated_cnt += 1

    db.session.commit()
    _log(
        f"Seeding complete. Created {created_cnt} rules, updated {updated_cnt}, skipped {skipped_cnt}."
    )


def register_cli_commands(app: Flask) -> None:
    """Register all CLI commands with the Flask app."""

    @app.cli.command("init-db")
    @with_appcontext
    def init_db() -> None:
        """Create all database tables."""
        db.create_all()
        click.echo("Database tables created.")

    @app.cli.command("seed")
    @with_appcontext
    def seed() -> None:
        """Seed the database with 14 default categories and classification rules.

        This command is idempotent: it checks for existing records before creating.
        Creates the 14 standard categories from Appendix A6 and keyword-based
        classification rules with appropriate priorities.
        """
        seed_default_data(echo=True)

    @app.cli.command("train-model")
    @click.option("--csv", "csv_path", required=True, type=click.Path(exists=True), help="Path to labeled training CSV")
    @click.option("--output", "output_path", default=None, help="Path to save trained joblib model")
    @with_appcontext
    def train_model(csv_path: str, output_path: str | None) -> None:
        """Train scikit-learn classification pipeline on verified labeled data."""
        import pandas as pd
        from app.classification.ml_classifier import TransactionClassifier

        click.echo(f"Loading training data from {csv_path}...")
        df = pd.read_csv(csv_path)

        # Expected columns: description, category_name (optional debit, credit)
        if "description" not in df.columns or "category_name" not in df.columns:
            click.echo("Error: CSV must contain 'description' and 'category_name' columns.")
            return

        if "debit" not in df.columns:
            df["debit"] = 0.0
        if "credit" not in df.columns:
            df["credit"] = 0.0

        model = TransactionClassifier(model_version=f"v{datetime.now().strftime('%Y%m%d%H%M')}")
        metrics = model.train(df)

        save_target = output_path or current_app.config.get("MODEL_PATH", "trained_models/classifier.joblib")
        model.save(save_target)

        click.echo(f"Model successfully trained and saved to {save_target}")
        click.echo(f"  Accuracy: {metrics['accuracy']:.4f}")
        click.echo(f"  Macro F1: {metrics['macro_f1']:.4f}")
        click.echo(f"  Weighted F1: {metrics['weighted_f1']:.4f}")
        click.echo(f"  Classes ({len(metrics['classes'])}): {', '.join(metrics['classes'][:5])}...")

    @app.cli.command("cleanup-uploads")
    @with_appcontext
    def cleanup_uploads() -> None:
        """Remove uploaded statement files older than FILE_RETENTION_DAYS."""
        upload_dir = current_app.config["UPLOAD_DIR"]
        retention_days = current_app.config.get("FILE_RETENTION_DAYS", 30)
        cutoff = time.time() - (retention_days * 86400)
        removed = 0

        if not os.path.isdir(upload_dir):
            click.echo(f"Upload directory not found: {upload_dir}")
            return

        for fname in os.listdir(upload_dir):
            fpath = os.path.join(upload_dir, fname)
            if os.path.isfile(fpath):
                try:
                    if os.path.getmtime(fpath) < cutoff:
                        os.remove(fpath)
                        removed += 1
                except OSError as exc:
                    click.echo(f"  Error deleting {fpath}: {exc}")

        click.echo(f"Cleanup complete. Removed {removed} file(s) older than {retention_days} days.")

    @app.cli.command("check-deps")
    @with_appcontext
    def check_deps() -> None:
        """Report availability of Python packages and external system binaries."""
        click.echo("Checking Python packages:")
        packages = [
            ("Flask", "flask"),
            ("Flask-SQLAlchemy", "flask_sqlalchemy"),
            ("SQLAlchemy", "sqlalchemy"),
            ("Pydantic", "pydantic"),
            ("PyMuPDF", "fitz"),
            ("pdfplumber", "pdfplumber"),
            ("pdf2image", "pdf2image"),
            ("pytesseract", "pytesseract"),
            ("OpenCV", "cv2"),
            ("Pillow", "PIL"),
            ("pandas", "pandas"),
            ("scikit-learn", "sklearn"),
            ("openpyxl", "openpyxl"),
            ("waitress", "waitress"),
            ("reportlab", "reportlab"),
        ]

        all_pkgs = True
        for name, mod in packages:
            try:
                m = __import__(mod)
                ver = getattr(m, "__version__", "OK")
                click.echo(f"  [OK] {name} ({ver})")
            except ImportError:
                click.echo(f"  ✗ {name} - MISSING")
                all_pkgs = False

        click.echo("\nChecking external system binaries (required for scanned PDF OCR):")
        tesseract_path = shutil.which("tesseract")
        if tesseract_path:
            click.echo(f"  [OK] tesseract: {tesseract_path}")
        else:
            click.echo("  ⚠ tesseract: NOT FOUND in PATH (text PDFs will still work, scanned pages will report OCR unavailable)")

        configured_provider = current_app.config.get("OCR_PROVIDER", "").strip().lower()
        configured_provider_available = True
        if configured_provider == "paddleocr":
            click.echo("\nChecking configured PaddleOCR provider:")
            try:
                import paddle  # noqa: F401
                from paddleocr import PPStructureV3  # noqa: F401
                from app.extraction.document_ocr import ensure_paddle_structure_dependencies

                ensure_paddle_structure_dependencies()
            except Exception as exc:
                configured_provider_available = False
                click.echo(
                    "  [MISSING] PaddleOCR PP-StructureV3 is not ready "
                    f"({type(exc).__name__}: {exc})\n"
                    "    Install it with: python -m pip install -r requirements-ocr-paddle.txt"
                )
            else:
                click.echo("  [OK] PaddleOCR PP-StructureV3 and the PaddleX OCR extra are available.")

        poppler_path = shutil.which("pdftoppm")
        if poppler_path:
            click.echo(f"  [OK] poppler (pdftoppm): {poppler_path}")
        else:
            click.echo("  ⚠ poppler: NOT FOUND in PATH (needed for pdf2image scanned rendering)")

        if all_pkgs and configured_provider_available:
            click.echo("\n[OK] All core Python dependencies are satisfied.")
        elif all_pkgs:
            click.echo("\n[WARN] Core dependencies are present, but the configured OCR provider is unavailable.")

    @app.cli.command("generate-samples")
    @click.option("--output-dir", default="instance/samples", help="Directory to save generated synthetic PDFs")
    @with_appcontext
    def generate_samples(output_dir: str) -> None:
        """Generate synthetic PDFs (SBI, HDFC, ICICI, scanned, mixed, corrupted, encrypted, etc.)."""
        from reportlab.lib.pagesizes import letter
        from reportlab.pdfgen import canvas
        from PIL import Image, ImageDraw, ImageFont
        import pymupdf as fitz

        os.makedirs(output_dir, exist_ok=True)
        click.echo(f"Generating synthetic statement PDFs in {output_dir}...")

        # 1. SBI Text Statement
        sbi_path = os.path.join(output_dir, "sbi_sample.pdf")
        c = canvas.Canvas(sbi_path, pagesize=letter)
        c.setFont("Helvetica-Bold", 14)
        c.drawString(50, 750, "STATE BANK OF INDIA - STATEMENT OF ACCOUNT")
        c.setFont("Helvetica", 10)
        c.drawString(50, 730, "Customer Name: RAJESH KUMAR")
        c.drawString(50, 715, "Account Number: 30495839201")
        c.drawString(50, 700, "IFSC: SBIN0001234")
        c.drawString(50, 685, "Branch: Connaught Place, New Delhi")
        c.drawString(50, 670, "Period: 01/01/2026 to 31/01/2026")
        c.drawString(50, 655, "Opening Balance: 25,000.00 Cr")
        c.drawString(50, 640, "Closing Balance: 38,450.00 Cr")

        # Table header
        c.line(50, 620, 550, 620)
        c.setFont("Helvetica-Bold", 9)
        c.drawString(50, 605, "Txn Date")
        c.drawString(130, 605, "Description")
        c.drawString(330, 605, "Debit")
        c.drawString(410, 605, "Credit")
        c.drawString(490, 605, "Balance")
        c.line(50, 595, 550, 595)

        # Rows
        sbi_txns = [
            ("02/01/2026", "UPI/Swiggy/Order1234/swiggy@icici", "450.00", "", "24,550.00"),
            ("05/01/2026", "NEFT/Salary Jan 2026/INFOSYS", "", "35,000.00", "59,550.00"),
            ("10/01/2026", "Electricity Bill/Torrent Power", "1,500.00", "", "58,050.00"),
            ("15/01/2026", "ATM/Cash WDL/Connaught Pl", "5,000.00", "", "53,050.00"),
            ("20/01/2026", "Amazon/Shopping/402-948203", "4,600.00", "", "48,450.00"),
            ("25/01/2026", "Fuel/HPCL Petrol Pump", "2,000.00", "", "46,450.00"),
            ("28/01/2026", "SIP/Zerodha Broking/Investment", "8,000.00", "", "38,450.00"),
        ]

        y = 575
        c.setFont("Helvetica", 9)
        for t_date, desc, dr, cr, bal in sbi_txns:
            c.drawString(50, y, t_date)
            c.drawString(130, y, desc[:35])
            c.drawString(330, y, dr)
            c.drawString(410, y, cr)
            c.drawString(490, y, bal)
            y -= 25

        c.save()
        click.echo("  [OK] Created sbi_sample.pdf")

        # 2. HDFC Text Statement
        hdfc_path = os.path.join(output_dir, "hdfc_sample.pdf")
        c = canvas.Canvas(hdfc_path, pagesize=letter)
        c.setFont("Helvetica-Bold", 14)
        c.drawString(50, 750, "HDFC BANK LIMITED - ACCOUNT STATEMENT")
        c.setFont("Helvetica", 10)
        c.drawString(50, 730, "Name: PRIYA SHARMA")
        c.drawString(50, 715, "Account No: 50100492819384")
        c.drawString(50, 700, "IFSC: HDFC0000128")
        c.drawString(50, 685, "Branch Name: KORAMANGALA BANGALORE")
        c.drawString(50, 670, "Period: 01-Jan-2026 to 15-Jan-2026")
        c.drawString(50, 655, "Opening Balance: 10,000.00")
        c.drawString(50, 640, "Closing Balance: 18,250.00")

        c.line(50, 620, 550, 620)
        c.setFont("Helvetica-Bold", 9)
        c.drawString(50, 605, "Date")
        c.drawString(130, 605, "Narration")
        c.drawString(340, 605, "Withdrawal")
        c.drawString(420, 605, "Deposit")
        c.drawString(490, 605, "Closing Bal")
        c.line(50, 595, 550, 595)

        hdfc_txns = [
            ("02-Jan-2026", "UPI/Zomato/order948/zomato@hdfc", "350.00", "", "9,650.00"),
            ("05-Jan-2026", "Uber India/Ride fare/UBER", "400.00", "", "9,250.00"),
            ("10-Jan-2026", "IMPS/Transfer from Dad/948302", "", "10,000.00", "19,250.00"),
            ("12-Jan-2026", "Netflix Entertainment/Mumbai", "1,000.00", "", "18,250.00"),
        ]
        y = 575
        c.setFont("Helvetica", 9)
        for t_date, desc, dr, cr, bal in hdfc_txns:
            c.drawString(50, y, t_date)
            c.drawString(130, y, desc)
            c.drawString(340, y, dr)
            c.drawString(420, y, cr)
            c.drawString(490, y, bal)
            y -= 25

        c.save()
        click.echo("  [OK] Created hdfc_sample.pdf")

        # 3. ICICI Text Statement
        icici_path = os.path.join(output_dir, "icici_sample.pdf")
        c = canvas.Canvas(icici_path, pagesize=letter)
        c.setFont("Helvetica-Bold", 14)
        c.drawString(50, 750, "ICICI BANK STATEMENT")
        c.setFont("Helvetica", 10)
        c.drawString(50, 730, "Account Holder: ANANYA PATEL")
        c.drawString(50, 715, "Account Number: 001201582948")
        c.drawString(50, 700, "IFSC: ICIC0000012")
        c.drawString(50, 685, "Opening Balance: 5,000.00")
        c.drawString(50, 670, "Closing Balance: 3,800.00")

        c.line(50, 650, 550, 650)
        c.setFont("Helvetica-Bold", 9)
        c.drawString(50, 635, "Date")
        c.drawString(140, 635, "Description")
        c.drawString(340, 635, "Debit")
        c.drawString(420, 635, "Credit")
        c.drawString(490, 635, "Balance")
        c.line(50, 625, 550, 625)

        c.setFont("Helvetica", 9)
        c.drawString(50, 605, "2026-01-05")
        c.drawString(140, 605, "Apollo Pharmacy/Medicines")
        c.drawString(340, 605, "1,200.00")
        c.drawString(420, 605, "")
        c.drawString(490, 605, "3,800.00")
        c.save()
        click.echo("  [OK] Created icici_sample.pdf")

        # 4. Scanned PDF (Rendered as pure image in PDF)
        scanned_path = os.path.join(output_dir, "scanned_sample.pdf")
        img = Image.new("RGB", (800, 1000), color="white")
        draw = ImageDraw.Draw(img)
        draw.text((50, 50), "BANK OF BARODA - SCANNED ACCOUNT STATEMENT", fill="black")
        draw.text((50, 80), "Account No: 12345678901234", fill="black")
        draw.text((50, 110), "IFSC: BARB0000001", fill="black")
        draw.text((50, 140), "01/01/2026 Swiggy Food Order 450.00 Dr Bal 4550.00", fill="black")
        img.save(scanned_path, "PDF", resolution=150.0)
        click.echo("  [OK] Created scanned_sample.pdf")

        # 5. Encrypted PDF
        enc_path = os.path.join(output_dir, "encrypted_sample.pdf")
        doc = fitz.open(sbi_path)
        doc.save(
            enc_path,
            encryption=fitz.PDF_ENCRYPT_AES_256,
            owner_pw="owner123",
            user_pw="password123",
        )
        doc.close()
        click.echo("  [OK] Created encrypted_sample.pdf (password protected)")

        # 6. Corrupted PDF
        corr_path = os.path.join(output_dir, "corrupted_sample.pdf")
        with open(corr_path, "wb") as f:
            f.write(b"%PDF-1.4\n%This file has truncated corrupted binary data\x00\xff")
        click.echo("  [OK] Created corrupted_sample.pdf")

        click.echo("\n[OK] Synthetic samples generated successfully.")
