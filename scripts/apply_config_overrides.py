#!/usr/bin/env python3
"""Apply workflow_dispatch inputs as config overrides.

Reads INPUT_CHECK_IN, INPUT_CHECK_OUT, INPUT_MAX_PRICE from the environment
and writes config_overrides.py + patches config.py to import it.
"""

import os
import re

overrides = []
check_in = os.environ.get("INPUT_CHECK_IN", "")
check_out = os.environ.get("INPUT_CHECK_OUT", "")
max_price = os.environ.get("INPUT_MAX_PRICE", "")

date_re = re.compile(r"^\d{4}-\d{2}-\d{2}$")
if check_in and date_re.match(check_in):
    overrides.append(f'CHECK_IN = "{check_in}"')
if check_out and date_re.match(check_out):
    overrides.append(f'CHECK_OUT = "{check_out}"')
if max_price and max_price.isdigit():
    overrides.append(f'MAX_PRICE_PER_PERSON_CHF = {max_price}')

if overrides:
    with open("config_overrides.py", "w") as f:
        f.write("\n".join(overrides) + "\n")
    with open("config.py", "a") as f:
        f.write("\ntry:\n    from config_overrides import *\nexcept ImportError:\n    pass\n")
    print("Applied config overrides:", overrides)
else:
    print("No config overrides to apply.")
