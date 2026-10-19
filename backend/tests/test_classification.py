import csv
import sys

from backend import import_data


def test_property_type_classification_is_closed_and_unknown_safe():
    assert import_data.classify_residential('RESIDENTIAL') is True
    assert import_data.classify_residential(' residential ') is True
    for value in ('COMMERCIAL', 'VACANT', 'AG'):
        assert import_data.classify_residential(value) is False
    for value in ('', None, 'MIXED USE', 'RES'):
        assert import_data.classify_residential(value) is None


def test_import_preserves_classification_and_repeat_import_is_noop(appmod, tmp_path, monkeypatch):
    data_dir = tmp_path / 'Data'
    data_dir.mkdir()
    path = data_dir / 'Secured_Master_BK100.txt'
    rows = []
    for i, (property_type, puc) in enumerate((
        ('RESIDENTIAL', '0131'), ('COMMERCIAL', '0261'), ('VACANT', '0011'),
        ('AG', '4110'), ('UNMAPPED', '00X7'),
    ), start=1):
        rows.append({
            key: {
                'FolioKey': f'1234567{i}', 'SitusAddress': f'{i} TEST ST', 'SitusCity': 'PHOENIX',
                'SitusPostalCode': '85001', 'SitusUnitNumber': '', 'PropertyType': property_type,
                'PUC': puc, 'MCR_Key': '12345', 'MCR_Name': 'TEST SUBDIVISION',
                'RentalInd': 'N', 'MailingAddress1': f'{i} TEST ST', 'MailingAddress2': '',
                'MailingCity': 'PHOENIX', 'MailingState': 'AZ', 'MailingPostalCode': '85001',
                'MailingCountry': 'USA', 'ConstrYear': '2000',
            }.get(key, '') for key in import_data.EXPECTED
        })
    with path.open('w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=import_data.EXPECTED, delimiter='|')
        writer.writeheader()
        writer.writerows(rows)

    monkeypatch.setattr(import_data, 'connect', appmod.connect)
    monkeypatch.setattr(sys, 'argv', ['import_data', '--data-dir', str(data_dir)])
    import_data.main()
    with appmod.connect() as c:
        imported = c.execute('SELECT property_type,puc,residential FROM parcels ORDER BY apn').fetchall()
        dataset_count = c.execute('SELECT count(*) FROM datasets').fetchone()[0]
    assert imported == [
        ('RESIDENTIAL', '0131', True), ('COMMERCIAL', '0261', False), ('VACANT', '0011', False),
        ('AG', '4110', False), ('UNMAPPED', '00X7', None),
    ]

    import_data.main()
    with appmod.connect() as c:
        assert c.execute('SELECT count(*) FROM datasets').fetchone()[0] == dataset_count == 1
        assert c.execute('SELECT count(*) FROM parcels').fetchone()[0] == 5
