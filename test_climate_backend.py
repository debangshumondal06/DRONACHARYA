import os
import tempfile
from pathlib import Path

from flask import Flask

from climate_backend import register_climate


def make_app():
    temp = tempfile.NamedTemporaryFile(suffix='.sqlite3', delete=False)
    temp.close()
    app = Flask(__name__)
    app.config['TESTING'] = True
    app.config['CLIMATE_DB_PATH'] = temp.name
    register_climate(app)
    return app, Path(temp.name)


def test_routes():
    app, db_path = make_app()
    try:
        with app.test_client() as client:
            health = client.get('/api/climate/health')
            assert health.status_code == 200
            assert health.get_json()['ok'] is True

            bad_weather = client.get('/api/climate/weather?lat=999&lon=0')
            assert bad_weather.status_code == 400

            market = client.get('/api/market-prices?crop=wheat&state=MH')
            assert market.status_code == 503
            assert market.get_json()['connected'] is False

            news = client.get('/api/climate/news?crop=wheat&state=MH')
            assert news.status_code == 200
            assert len(news.get_json()['items']) >= 1

            saved = client.post('/api/climate/watchlist', json={'crop': 'wheat', 'state': 'MH'})
            assert saved.status_code == 200
            assert saved.get_json()['items'][0]['crop_code'] == 'wheat'

            compat = client.get('/api/climate/market-prices?crop=wheat&state=MH')
            assert compat.status_code == 503
    finally:
        db_path.unlink(missing_ok=True)


if __name__ == '__main__':
    test_routes()
    print('climate backend checks passed')
