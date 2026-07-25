"""
Database initialization script.
Seed merchant accounts and set up the initial active UPI config.
"""

import asyncio
import sys
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from app.config import get_settings
from app.models.database import Base, MerchantAccount, ActiveUPIConfig


MERCHANT_ACCOUNTS = [
    {
        "id": "bk_01",
        "upi_id": "yourplatform@axisb",
        "display_name": "Platform Alpha",
        "daily_cap_inr": 100000,
        "day_of_week": "Mon",
    },
    {
        "id": "bk_02",
        "upi_id": "yourplatform@oksbi",
        "display_name": "Platform Beta",
        "daily_cap_inr": 100000,
        "day_of_week": "Tue",
    },
    {
        "id": "bk_03",
        "upi_id": "yourplatform@ybl",
        "display_name": "Platform Gamma",
        "daily_cap_inr": 100000,
        "day_of_week": "Wed",
    },
    {
        "id": "bk_04",
        "upi_id": "yourplatform@paytm",
        "display_name": "Platform Delta",
        "daily_cap_inr": 100000,
        "day_of_week": "Thu",
    },
]


async def seed():
    settings = get_settings()
    engine = create_async_engine(settings.DATABASE_URL, echo=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with async_sessionmaker(engine, expire_on_commit=False)() as session:
        # Check if already seeded
        result = await session.execute(select(MerchantAccount))
        existing = list(result.scalars().all())
        if existing:
            print(f"Already seeded: {len(existing)} merchant accounts exist.")
            # Show current state
            for acct in existing:
                print(f"  {acct.id}: {acct.upi_id} ({acct.display_name}) active={acct.is_active}")
            await engine.dispose()
            return

        # Insert merchant accounts
        for i, acct_data in enumerate(MERCHANT_ACCOUNTS):
            acct = MerchantAccount(
                **acct_data,
                current_volume_inr=0,
                is_active=(i == 0),  # first account is active
                is_enabled=True,
            )
            session.add(acct)
            print(f"  Added: {acct.id} → {acct.upi_id} ({'ACTIVE' if acct.is_active else 'standby'})")

        # Flush merchant accounts so FK constraint is satisfied
        await session.flush()

        # Set initial active UPI config
        config = ActiveUPIConfig(
            id=1,
            active_account_id="bk_01",
        )
        session.add(config)
        print(f"  Active UPI set to: bk_01")

        await session.commit()
        print("\nSeeding complete!")

    await engine.dispose()


if __name__ == "__main__":
    print("Seeding database...")
    asyncio.run(seed())
