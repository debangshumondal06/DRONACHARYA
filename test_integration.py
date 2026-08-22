from app import app


def main():
    client = app.test_client()
    assert client.get('/').status_code in (301, 302)
    assert client.get('/field-visit').status_code in (301, 302)
    assert client.get('/store').status_code in (301, 302)
    assert client.get('/login').status_code in (301, 302)
    page = client.get('/estimate-yield')
    assert page.status_code == 200
    html = page.get_data(as_text=True)
    for marker in ('yieldForm', '/api/estimate', 'downloadCsvBtn', 'url_for'):
        if marker == 'url_for':
            continue
        assert marker in html, marker

    history = client.get('/api/history')
    assert history.status_code == 200
    response = client.post('/api/estimate', json={
        'place': 'Pune',
        'crop': 'wheat',
        'soilType': 'black',
        'irrigation': 'canal',
        'ph': 6.8,
        'area': 2,
        'areaUnit': 'acre',
    })
    assert response.status_code == 200, response.get_data(as_text=True)
    report = response.get_json()
    assert report['id']
    assert report['totalYield'] > 0
    report_id = report['id']
    assert client.get(f'/api/history/{report_id}').status_code == 200
    assert client.get(f'/api/history/{report_id}/csv').status_code == 200
    print('integration-ok', report_id, round(report['totalYield'], 2))


if __name__ == '__main__':
    main()
