import pytest

from backend.property_facts import classify_dwelling, rental_status


@pytest.mark.parametrize('raw,expected', [('Y', True), ('N', False), (' y ', True),
    (None, None), ('', None), ('0', None), ('YES', None)])
def test_rental_is_source_flag_only(raw, expected):
    assert rental_status(raw) is expected


@pytest.mark.parametrize('puc,expected', [('0131', 'detached'), ('0144', 'detached'),
    ('0178', 'detached'), ('0181', 'unknown'), ('0197', 'nonresidential'),
    ('0261', 'nonresidential'), ('0269', 'unknown'), ('0320', 'multifamily'),
    ('0355', 'multifamily'), ('0351', 'unknown'), ('0735', 'attached'), ('0737', 'detached'),
    ('0770', 'nonresidential'), ('0780', 'nonresidential'),
    ('0790', 'nonresidential'), ('0109', 'unknown'), ('01310', 'unknown'),
    ('131', 'unknown'), ('9999', 'unknown'), (None, 'unknown')])
def test_only_documented_codes_are_classified(puc, expected):
    assert classify_dwelling(puc, 'RESIDENTIAL', None) == expected


def test_num_units_never_substitutes_for_dwelling_evidence():
    assert classify_dwelling(None, 'RESIDENTIAL', 1) == 'unknown'
    assert classify_dwelling('0181', 'RESIDENTIAL', 2) == 'unknown'
    assert classify_dwelling('0131', 'RESIDENTIAL', 2) == 'detached'
    assert classify_dwelling('0131', 'COMMERCIAL', 1) == 'nonresidential'
