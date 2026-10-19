"""Conservative assessor classifications; never infer rentals from mailing addresses.

Arizona DOR Property Use Code Manual, residential pages 10-12 and 16:
https://azdor.gov/sites/default/files/2023-03/PROPERTY_useCodeManual.pdf
Codes below use each documented digit, rather than treating every 01/07 prefix
as a house. `detached` for graded 01 codes is an assessor single-family proxy,
not an independent survey of shared walls. `attached` also groups condominium
and townhouse tenure unless the code explicitly documents separate roofs/walls.
"""
import re

CLASSIFICATION_SOURCE = {
    'name': 'Arizona DOR Property Use Code Manual',
    'url': 'https://azdor.gov/sites/default/files/2023-03/PROPERTY_useCodeManual.pdf',
    'pages': [10, 11, 12, 16],
    'version': 'az-dor-puc-2011-1',
    'limitation': 'Assessor single-family classification is a detached-home proxy; shared walls are not independently verified.',
}


def rental_status(rental_ind):
    """Return source Y/N as bool, preserving absent/unrecognized values as unknown."""
    value = str(rental_ind or '').strip().upper()
    return {'Y': True, 'N': False}.get(value)


def classify_dwelling(puc, property_type=None, num_units=None):
    """Return detached/attached/multifamily/nonresidential/unknown.

    NumUnits is intentionally not decisive: additional units can be ADUs, and
    a missing value does not establish a single home. Only verified use codes
    and explicit nonresidential PropertyType values are applied.
    """
    category = str(property_type or '').strip().upper()
    if category in {'COMMERCIAL', 'VACANT', 'AG'}:
        return 'nonresidential'
    code = str(puc or '').strip()
    if not re.fullmatch(r'\d{4}', code):
        return 'unknown'
    group, grade, variant = code[:2], code[2], code[3]
    if group == '01':
        if grade in '01234567' and variant in '01234568':
            return 'detached'
        if grade == '9' and variant in '012345678':
            return 'nonresidential'
        # 018x is a dominant residence with an additional dwelling: ADU policy
        # needs review. Unknown subcodes remain unknown rather than guessed.
        return 'unknown'
    if group == '02' and grade in '12345678' and variant in '12':
        return 'nonresidential'  # PUD common property, including 0261 open space.
    if group == '03' and grade in '123456789' and variant in '012345678':
        if variant in '12' and grade not in '234':
            return 'unknown'  # Building-count variants apply only to 2/3/4plex.
        return 'multifamily'
    if group == '07':
        if grade in '123456':
            if variant == '7':
                return 'detached'  # Manual explicitly says no shared walls/roofs.
            if variant in '012345689':
                return 'attached'  # Condo/townhouse category, not a wall survey.
        if (grade == '7' and variant == '0') or (grade in '89' and variant in '0123456789'):
            return 'nonresidential'  # Associated parcel or common area.
    return 'unknown'
