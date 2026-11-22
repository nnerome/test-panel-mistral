"""Table accessors, one module per table, contributed by the capability that owns the table.

A model describes a row; an accessor is the only place that reads or writes one, so the hosts stay
free of ORM queries. The base package ships none: each owning capability drops its
``db/accessors/<table>.py`` here, and a caller imports it directly --
``from db.accessors.<table> import <fn>`` -- so nothing in the base has to name it.

For convenience the loader below also imports every sibling on package import (mirroring
``db.models``), so ``from db import accessors as acc; acc.<table>.<fn>`` works too.
"""

import importlib
import pkgutil

for _module in sorted(pkgutil.iter_modules(__path__, f"{__name__}."), key=lambda entry: entry.name):
    if _module.name.rpartition(".")[2].startswith("_"):
        continue
    importlib.import_module(_module.name)
