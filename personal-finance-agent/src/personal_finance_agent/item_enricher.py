from __future__ import annotations

from personal_finance_agent.models import ItemCategorization


ITEM_TO_BUDGET = {
    "Groceries": "Groceries",
    "Household Consumables": "Household & Kids",
    "Kids": "Household & Kids",
    "Clothing": "Household & Kids",
    "Electronics": "Other Discretionary",
    "Books / Media": "Other Discretionary",
    "Gifts": "Other Discretionary",
    "Other": "Other Discretionary",
}


def categorize_item_title(title: str) -> ItemCategorization:
    text = title.upper()
    if any(word in text for word in ["COFFEE", "ESPRESSO"]):
        return ItemCategorization(
            item_category="Groceries",
            item_subcategory="Coffee & Tea",
            confidence=0.8,
            reason="Coffee or tea keyword match.",
        )
    if any(word in text for word in ["SNACK", "CRACKER", "CHIP", "POPCORN", "GRANOLA", "BAR", "COOKIE"]):
        return ItemCategorization(
            item_category="Groceries",
            item_subcategory="Snacks",
            confidence=0.79,
            reason="Snack keyword match.",
        )
    if any(word in text for word in ["CEREAL", "OATMEAL", "PANCAKE", "WAFFLE"]):
        return ItemCategorization(
            item_category="Groceries",
            item_subcategory="Breakfast",
            confidence=0.79,
            reason="Breakfast food keyword match.",
        )
    if any(word in text for word in ["WATER", "SODA", "JUICE", "DRINK", "BEVERAGE"]):
        return ItemCategorization(
            item_category="Groceries",
            item_subcategory="Beverages",
            confidence=0.78,
            reason="Beverage keyword match.",
        )
    if any(word in text for word in ["MILK", "YOGURT", "CHEESE", "FROZEN", "ICE CREAM"]):
        return ItemCategorization(
            item_category="Groceries",
            item_subcategory="Dairy & Frozen",
            confidence=0.78,
            reason="Dairy or frozen food keyword match.",
        )
    if any(word in text for word in ["FOOD", "PANTRY", "FLOUR", "SUGAR", "TORTILLA", "CARROT", "HUMMUS"]):
        return ItemCategorization(
            item_category="Groceries",
            item_subcategory="Pantry & Ingredients",
            confidence=0.78,
            reason="Food or pantry keyword match.",
        )
    if any(
        word in text
        for word in [
            "SOAP",
            "DETERGENT",
            "CLEANER",
            "LAUNDRY",
            "DISH",
            "SPONGE",
        ]
    ):
        return ItemCategorization(
            item_category="Household Consumables",
            item_subcategory="Cleaning & Laundry",
            confidence=0.83,
            reason="Cleaning or laundry consumable keyword match.",
        )
    if any(word in text for word in ["PAPER TOWEL", "TOILET PAPER", "TISSUE", "NAPKIN"]):
        return ItemCategorization(
            item_category="Household Consumables",
            item_subcategory="Paper Goods",
            confidence=0.84,
            reason="Paper goods keyword match.",
        )
    if any(word in text for word in ["FLOSS", "TOOTH", "DENTAL", "MOUTHWASH"]):
        return ItemCategorization(
            item_category="Household Consumables",
            item_subcategory="Dental Care",
            confidence=0.84,
            reason="Dental care keyword match.",
        )
    if any(word in text for word in ["SHAMPOO", "CONDITIONER", "DEODORANT", "LOTION", "LIP BALM", "RAZOR"]):
        return ItemCategorization(
            item_category="Household Consumables",
            item_subcategory="Personal Care",
            confidence=0.82,
            reason="Personal care keyword match.",
        )
    if any(word in text for word in ["DIAPER", "WIPES", "TRAINING UNDERWEAR", "PULL-UP", "PULL UP"]):
        return ItemCategorization(
            item_category="Household Consumables",
            item_subcategory="Diapers & Wipes",
            confidence=0.84,
            reason="Diaper or wipes keyword match.",
        )
    if any(
        word in text
        for word in [
            "PAPER TOWEL",
            "TOILET",
            "FLOSS",
            "MOSQUITO",
            "INSECT",
            "REPELLENT",
        ]
    ):
        return ItemCategorization(
            item_category="Household Consumables",
            item_subcategory="Pest Control",
            confidence=0.82,
            reason="Household consumable keyword match.",
        )
    if any(word in text for word in ["STORAGE", "TOTE", "MAT", "CHAIR MAT", "BASKET"]):
        return ItemCategorization(
            item_category="Household Consumables",
            item_subcategory="Home Supplies",
            confidence=0.76,
            reason="Home supply keyword match.",
        )
    if any(word in text for word in ["TOY", "COLORING", "CRAYOLA", "WALKIE", "PAW PATROL", "GAME"]):
        return ItemCategorization(
            item_category="Kids",
            item_subcategory="Toys & Activities",
            confidence=0.78,
            reason="Kids toy or activity keyword match.",
        )
    if any(word in text for word in ["KID", "BABY", "SCHOOL"]):
        return ItemCategorization(
            item_category="Kids",
            item_subcategory="Kids Supplies",
            confidence=0.75,
            reason="Kids keyword match.",
        )
    if any(word in text for word in ["SHOES", "SNEAKER", "SANDAL"]):
        return ItemCategorization(
            item_category="Clothing",
            item_subcategory="Shoes",
            confidence=0.82,
            reason="Shoes keyword match.",
        )
    if any(word in text for word in ["SHIRT", "PANTS", "CLOTHING", "DRESS", "SHORTS"]):
        return ItemCategorization(
            item_category="Clothing",
            item_subcategory="Clothing",
            confidence=0.8,
            reason="Clothing keyword match.",
        )
    if any(word in text for word in ["USB", "CABLE", "BATTERY", "HEADPHONE", "ELECTRONIC"]):
        return ItemCategorization(
            item_category="Electronics",
            item_subcategory="Electronics Accessories",
            confidence=0.76,
            reason="Electronics keyword match.",
        )
    if any(word in text for word in ["BOOK", "KINDLE", "MOVIE", "GAME"]):
        return ItemCategorization(
            item_category="Books / Media",
            item_subcategory="Books & Media",
            confidence=0.76,
            reason="Media keyword match.",
        )
    if "GIFT" in text:
        return ItemCategorization(
            item_category="Gifts",
            item_subcategory="Gifts",
            confidence=0.74,
            reason="Gift keyword match.",
        )
    if any(word in text for word in ["VITAMIN", "SUPPLEMENT", "PROTEIN", "NUTRICOST"]):
        return ItemCategorization(
            item_category="Other",
            item_subcategory="Health & Supplements",
            confidence=0.7,
            reason="Health supplement keyword match.",
        )
    return ItemCategorization(
        item_category="Other",
        item_subcategory="General Discretionary",
        confidence=0.4,
        reason="No item-level rule matched.",
    )
