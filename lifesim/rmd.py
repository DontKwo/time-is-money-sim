UNIFORM_LIFETIME_TABLE = {
    72: 27.4,
    73: 26.5,
    74: 25.5,
    75: 24.6,
    76: 23.7,
    77: 22.9,
    78: 22.0,
    79: 21.1,
    80: 20.2,
    81: 19.4,
    82: 18.5,
    83: 17.7,
    84: 16.8,
    85: 16.0,
    86: 15.2,
    87: 14.4,
    88: 13.7,
    89: 12.9,
    90: 12.2,
    91: 11.5,
    92: 10.8,
    93: 10.1,
    94: 9.5,
    95: 8.9,
    96: 8.4,
    97: 7.8,
    98: 7.3,
    99: 6.8,
    100: 6.4,
    101: 6.0,
    102: 5.6,
    103: 5.2,
    104: 4.9,
    105: 4.6,
    106: 4.3,
    107: 4.1,
    108: 3.9,
    109: 3.7,
    110: 3.5,
    111: 3.4,
    112: 3.3,
    113: 3.1,
    114: 3.0,
    115: 2.9,
    116: 2.8,
    117: 2.7,
    118: 2.5,
    119: 2.3,
    120: 2.0,
}

def get_rmd_age(birth_year: int) -> int:
    """Returns the statutory RMD age based on birth year."""
    if birth_year < 1951:
        return 72
    if birth_year <= 1959:
        return 73
    return 75

def compute_rmd_cents(age: int, prior_year_end_balance_cents: int) -> int:
    """Computes the RMD amount based on age and prior year balance."""
    if age < 72 or prior_year_end_balance_cents <= 0:
        return 0

    distribution_factor = UNIFORM_LIFETIME_TABLE.get(age, 2.0)
    return int(round(prior_year_end_balance_cents / distribution_factor))
