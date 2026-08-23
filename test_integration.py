from io import BytesIO
from unittest.mock import patch

from app import app


def login(client):
    response = client.post(
        "/api/auth/login",
        data={
            "aadhaar_number": "123456789012",
            "phone_number": "9876543210",
            "email_id": "integration@example.com",
            "prototype_consent": "true",
        },
    )
    assert response.status_code == 200, response.get_data(as_text=True)


def main():
    app.config.update(TESTING=True)

    with app.test_client() as client:
        assert client.get("/").status_code in (301, 302)
        assert client.get("/login").status_code == 200
        assert client.get("/estimate-yield").status_code == 200
        assert client.get("/api/health").status_code == 200

        login(client)

        assert client.get("/").status_code == 200
        assert client.get("/field-visit").status_code == 200
        assert client.get("/store").status_code == 200
        assert client.get("/assistant").status_code == 200
        assert client.get("/static/js/login.js").status_code == 200
        assert client.get("/static/js/app.js").status_code == 200
        assert client.get("/static/js/store.js").status_code == 200

        yield_page = client.get("/estimate-yield")
        yield_html = yield_page.get_data(as_text=True)
        for marker in ("yieldForm", "/api/estimate", "downloadCsvBtn"):
            assert marker in yield_html, marker

        with patch(
            "yield_backend.geocode_place",
            return_value=(18.52, 73.85, "Pune"),
        ), patch(
            "yield_backend.fetch_rainfall",
            return_value=(["2030-01-01"], [12.0]),
        ):
            estimate = client.post(
                "/api/estimate",
                json={
                    "place": "Pune",
                    "crop": "wheat",
                    "soilType": "black",
                    "irrigation": "canal",
                    "ph": 6.8,
                    "area": 2,
                    "areaUnit": "acre",
                },
            )
        assert estimate.status_code == 200, estimate.get_data(as_text=True)
        report = estimate.get_json()
        assert report["id"]
        assert report["totalYield"] > 0
        assert client.get(f"/api/history/{report['id']}").status_code == 200
        assert client.get(f"/api/history/{report['id']}/csv").status_code == 200

        visit = client.post(
            "/api/field-visits",
            json={
                "fieldName": "Integration field",
                "phone": "9876543210",
                "visitDate": "2030-01-01",
                "tests": ["routine_soil"],
            },
        )
        assert visit.status_code == 201, visit.get_data(as_text=True)

        upload = client.post(
            "/api/upload",
            data={
                "target_column": "yield",
                "dataset": (
                    BytesIO(
                        b"month,temperature,yield\n"
                        b"1,18,2.1\n"
                        b"2,21,2.4\n"
                        b"3,25,2.8\n"
                        b"4,29,3.0\n"
                        b"5,31,3.2\n"
                    ),
                    "sample.csv",
                ),
            },
            content_type="multipart/form-data",
        )
        assert upload.status_code == 200, upload.get_data(as_text=True)
        analysis_id = upload.get_json()["analysis_id"]
        assert client.get(f"/dashboard?analysis_id={analysis_id}").status_code == 200
        assert client.get(f"/api/analysis/{analysis_id}").status_code == 200

        listing = client.post(
            "/api/products",
            json={
                "seller_name": "Integration Farmer",
                "seller_contact": "9876543210",
                "crop_name": "Wheat",
                "category": "Grains",
                "quantity": 10,
                "unit": "kg",
                "price_per_unit": 25,
                "harvest_date": "2030-01-01",
                "location": "Pune",
                "description": "Integration test listing",
            },
        )
        assert listing.status_code == 201, listing.get_data(as_text=True)
        product_id = listing.get_json()["id"]

        products = client.get("/api/products")
        assert products.status_code == 200
        assert any(
            product["id"] == product_id
            for product in products.get_json()
        )

        order = client.post(
            "/api/orders",
            json={
                "buyer_name": "Integration Buyer",
                "buyer_contact": "9876543210",
                "buyer_address": "Pune",
                "items": [{"product_id": product_id, "quantity": 2}],
            },
        )
        assert order.status_code == 201, order.get_data(as_text=True)
        assert client.get("/api/orders").status_code == 200

    print("integration-ok")


if __name__ == "__main__":
    main()