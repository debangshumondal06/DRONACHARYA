import sqlite3

from flask import Blueprint, jsonify, request, session

from database import get_connection

marketplace_bp = Blueprint("marketplace", __name__)


def current_user_id():
    return session.get("user_id")


def require_user():
    user_id = current_user_id()
    if user_id is None:
        return None, (
            jsonify({"error": "Please log in before using the marketplace."}),
            401,
        )
    return user_id, None


def clean_text(value, field, required=True, max_length=500):
    text = str(value or "").strip()
    if required and not text:
        raise ValueError(f"{field} is required.")
    if len(text) > max_length:
        raise ValueError(f"{field} is too long.")
    return text


def parse_number(value, field, minimum=0):
    try:
        number = float(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{field} must be a number.") from error
    if number < minimum:
        raise ValueError(f"{field} must be at least {minimum}.")
    return number


def product_values(payload):
    return {
        "seller_name": clean_text(payload.get("seller_name"), "Seller name"),
        "seller_contact": clean_text(
            payload.get("seller_contact"), "Seller contact", max_length=40
        ),
        "crop_name": clean_text(
            payload.get("crop_name"), "Crop name", max_length=120
        ),
        "category": clean_text(
            payload.get("category"), "Category", max_length=80
        ),
        "quantity": parse_number(
            payload.get("quantity"), "Quantity", minimum=0.01
        ),
        "unit": clean_text(payload.get("unit"), "Unit", max_length=30),
        "price_per_unit": parse_number(
            payload.get("price_per_unit"), "Price per unit", minimum=0
        ),
        "harvest_date": clean_text(
            payload.get("harvest_date"),
            "Harvest date",
            required=False,
            max_length=20,
        ) or None,
        "location": clean_text(
            payload.get("location"), "Location", max_length=200
        ),
        "description": clean_text(
            payload.get("description"),
            "Description",
            required=False,
            max_length=2000,
        ) or None,
    }


@marketplace_bp.get("/api/products")
def list_products():
    user_id = current_user_id()
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT id, seller_id, seller_name, seller_contact, crop_name,
                   category, quantity, unit, price_per_unit, harvest_date,
                   location, description, status, created_at, updated_at
            FROM products
            WHERE status = 'active' OR seller_id = ?
            ORDER BY id DESC
            """,
            (user_id if user_id is not None else -1,),
        ).fetchall()
    return jsonify([dict(row) for row in rows])


@marketplace_bp.post("/api/products")
def create_product():
    user_id, error = require_user()
    if error:
        return error

    try:
        values = product_values(request.get_json(silent=True) or {})
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    with get_connection() as connection:
        cursor = connection.execute(
            """
            INSERT INTO products (
                seller_id, seller_name, seller_contact, crop_name, category,
                quantity, unit, price_per_unit, harvest_date, location,
                description, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'active')
            """,
            (
                user_id,
                values["seller_name"],
                values["seller_contact"],
                values["crop_name"],
                values["category"],
                values["quantity"],
                values["unit"],
                values["price_per_unit"],
                values["harvest_date"],
                values["location"],
                values["description"],
            ),
        )
        product_id = cursor.lastrowid
        connection.commit()

    return jsonify({"id": product_id, "message": "Listing published."}), 201


@marketplace_bp.put("/api/products/<int:product_id>")
def update_product(product_id):
    user_id, error = require_user()
    if error:
        return error

    try:
        values = product_values(request.get_json(silent=True) or {})
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    with get_connection() as connection:
        cursor = connection.execute(
            """
            UPDATE products
            SET seller_name = ?, seller_contact = ?, crop_name = ?, category = ?,
                quantity = ?, unit = ?, price_per_unit = ?, harvest_date = ?,
                location = ?, description = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ? AND seller_id = ?
            """,
            (
                values["seller_name"],
                values["seller_contact"],
                values["crop_name"],
                values["category"],
                values["quantity"],
                values["unit"],
                values["price_per_unit"],
                values["harvest_date"],
                values["location"],
                values["description"],
                product_id,
                user_id,
            ),
        )
        connection.commit()

    if cursor.rowcount == 0:
        return jsonify(
            {"error": "Listing not found or unavailable for this account."}
        ), 404
    return jsonify({"message": "Listing updated."})


@marketplace_bp.delete("/api/products/<int:product_id>")
def delete_product(product_id):
    user_id, error = require_user()
    if error:
        return error

    with get_connection() as connection:
        cursor = connection.execute(
            """
            UPDATE products
            SET status = 'closed', updated_at = CURRENT_TIMESTAMP
            WHERE id = ? AND seller_id = ?
            """,
            (product_id, user_id),
        )
        connection.commit()

    if cursor.rowcount == 0:
        return jsonify(
            {"error": "Listing not found or unavailable for this account."}
        ), 404
    return jsonify({"message": "Listing removed."})


@marketplace_bp.get("/api/orders")
def list_orders():
    user_id, error = require_user()
    if error:
        return error

    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT DISTINCT o.id, o.buyer_id, o.buyer_name, o.total_amount,
                   o.status, o.created_at
            FROM orders o
            LEFT JOIN order_items oi ON oi.order_id = o.id
            WHERE o.buyer_id = ? OR oi.seller_id = ?
            ORDER BY o.id DESC
            """,
            (user_id, user_id),
        ).fetchall()
    return jsonify([dict(row) for row in rows])


@marketplace_bp.post("/api/orders")
def create_order():
    user_id, error = require_user()
    if error:
        return error

    payload = request.get_json(silent=True) or {}
    try:
        buyer_name = clean_text(
            payload.get("buyer_name"), "Buyer name", max_length=120
        )
        buyer_contact = clean_text(
            payload.get("buyer_contact"), "Buyer contact", max_length=40
        )
        buyer_address = clean_text(
            payload.get("buyer_address"), "Buyer address", max_length=1000
        )
        requested_items = payload.get("items") or []
        if not requested_items:
            raise ValueError("Add at least one item to the order.")
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    try:
        with get_connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            selected = []
            total = 0.0

            for item in requested_items:
                product_id = int(item.get("product_id"))
                quantity = parse_number(
                    item.get("quantity"), "Order quantity", minimum=0.01
                )
                row = connection.execute(
                    """
                    SELECT id, seller_id, crop_name, unit, quantity, price_per_unit
                    FROM products
                    WHERE id = ? AND status = 'active'
                    """,
                    (product_id,),
                ).fetchone()

                if row is None:
                    raise ValueError(f"Product {product_id} is no longer available.")
                if row["quantity"] < quantity:
                    raise ValueError(f"Not enough stock for {row['crop_name']}.")

                line_total = quantity * row["price_per_unit"]
                total += line_total
                selected.append((row, quantity, line_total))

            cursor = connection.execute(
                """
                INSERT INTO orders (
                    buyer_id, buyer_name, buyer_contact, buyer_address,
                    total_amount, status
                ) VALUES (?, ?, ?, ?, ?, 'pending')
                """,
                (user_id, buyer_name, buyer_contact, buyer_address, total),
            )
            order_id = cursor.lastrowid

            for row, quantity, line_total in selected:
                connection.execute(
                    """
                    INSERT INTO order_items (
                        order_id, product_id, seller_id, quantity,
                        unit_price, line_total
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        order_id,
                        row["id"],
                        row["seller_id"],
                        quantity,
                        row["price_per_unit"],
                        line_total,
                    ),
                )
                connection.execute(
                    """
                    UPDATE products
                    SET quantity = quantity - ?,
                        status = CASE
                            WHEN quantity - ? <= 0 THEN 'closed'
                            ELSE status
                        END,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                    """,
                    (quantity, quantity, row["id"]),
                )

            connection.commit()
    except (ValueError, TypeError, sqlite3.Error) as exc:
        return jsonify({"error": str(exc) or "Could not place the order."}), 400

    return jsonify(
        {"order_id": order_id, "message": "Order placed successfully."}
    ), 201