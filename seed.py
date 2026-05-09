"""Seed local Pipeline DB with one company + one WhatsApp channel_account.

Idempotent: re-runs are safe; existing rows are reused, not duplicated.
Run from the pipeline root: `python3 seed.py`
"""
from dotenv import load_dotenv
load_dotenv()

from app import app                              # noqa: E402
from models import db, Company, ChannelAccount   # noqa: E402

COMPANY_NAME = "Taxi Production Test"
COMPANY_SLUG = "taxi-production-test"
CHANNEL_DISPLAY_NAME = "Taxi WhatsApp Test"
CHANNEL_TYPE = "whatsapp"
CONNECTOR_TYPE = "whatsapp_baileys"
CHANNEL_STATUS = "pending_qr"


def seed():
    with app.app_context():
        db.create_all()

        company = Company.query.filter_by(slug=COMPANY_SLUG).first()
        created_company = False
        if not company:
            company = Company(name=COMPANY_NAME, slug=COMPANY_SLUG)
            db.session.add(company)
            db.session.flush()
            created_company = True

        ch = ChannelAccount.query.filter_by(
            company_id=company.id,
            connector_type=CONNECTOR_TYPE,
            display_name=CHANNEL_DISPLAY_NAME,
        ).first()
        created_channel = False
        if not ch:
            ch = ChannelAccount(
                company_id=company.id,
                channel_type=CHANNEL_TYPE,
                connector_type=CONNECTOR_TYPE,
                display_name=CHANNEL_DISPLAY_NAME,
                status=CHANNEL_STATUS,
            )
            db.session.add(ch)
            db.session.flush()
            created_channel = True

        db.session.commit()

        bar = "=" * 64
        print()
        print(bar)
        print(f"  COMPANY_ID         = {company.id}")
        print(f"  CHANNEL_ACCOUNT_ID = {ch.id}")
        print(bar)
        print(f"  Company         : {company.name} "
              f"({'created' if created_company else 'existing'})")
        print(f"  Channel account : {ch.display_name} "
              f"({'created' if created_channel else 'existing'})")
        print(f"  Channel status  : {ch.status}")
        print(bar)
        print()
        print("Copy these into connectors/whatsapp-baileys/.env:")
        print(f"  COMPANY_ID={company.id}")
        print(f"  CHANNEL_ACCOUNT_ID={ch.id}")
        print()


if __name__ == "__main__":
    seed()
