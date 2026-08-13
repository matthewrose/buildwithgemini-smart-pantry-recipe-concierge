# Copyright 2026 Google LLC
#
# Seed script for Firestore pantry_inventory collection.
# IMPORTANT: Hardcode project ID as a string per requirements.

import datetime
from google.cloud import firestore

FIRESTORE_PROJECT_ID = "qwiklabs-gcp-03-54645ed9a07f"
COLLECTION_NAME = "pantry_inventory"

SEED_ITEMS = [
    {
        "id": "chicken_breast",
        "item_name": "Chicken Breast",
        "category": "Meat & Seafood",
        "quantity": "2 lbs",
        "expiration_date": "2026-08-16",
        "status": "available",
        "notes": "Purchased from Trader Joe's",
    },
    {
        "id": "baby_spinach",
        "item_name": "Baby Spinach",
        "category": "Produce",
        "quantity": "1 bag (10 oz)",
        "expiration_date": "2026-08-15",
        "status": "available",
        "notes": "Organic fresh spinach",
    },
    {
        "id": "garlic_head",
        "item_name": "Garlic Clove",
        "category": "Produce",
        "quantity": "1 bulb",
        "expiration_date": "2026-09-01",
        "status": "available",
        "notes": "Fresh garlic",
    },
    {
        "id": "heavy_cream",
        "item_name": "Heavy Cream",
        "category": "Dairy",
        "quantity": "1 pint",
        "expiration_date": "2026-08-14",
        "status": "available",
        "notes": "Use soon for sauces",
    },
    {
        "id": "olive_oil",
        "item_name": "Extra Virgin Olive Oil",
        "category": "Pantry",
        "quantity": "1 bottle (16 oz)",
        "expiration_date": "2027-01-01",
        "status": "available",
        "notes": "Cold pressed",
    },
    {
        "id": "penne_pasta",
        "item_name": "Penne Pasta",
        "category": "Pantry",
        "quantity": "1 box (16 oz)",
        "expiration_date": "2027-06-01",
        "status": "available",
        "notes": "Whole wheat penne",
    },
]


def seed_database():
    print(f"Connecting to Firestore for project: {FIRESTORE_PROJECT_ID}...")
    db = firestore.Client(project=FIRESTORE_PROJECT_ID)
    collection_ref = db.collection(COLLECTION_NAME)

    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()

    for item in SEED_ITEMS:
        doc_id = item["id"]
        doc_data = {
            "item_name": item["item_name"],
            "category": item["category"],
            "quantity": item["quantity"],
            "expiration_date": item["expiration_date"],
            "status": item["status"],
            "notes": item["notes"],
            "updated_at": now_iso,
        }
        collection_ref.document(doc_id).set(doc_data)
        print(f"  ✓ Seeded item '{doc_id}' -> {item['item_name']} ({item['quantity']})")

    print(f"Successfully seeded {len(SEED_ITEMS)} items into collection '{COLLECTION_NAME}'!")


if __name__ == "__main__":
    seed_database()
