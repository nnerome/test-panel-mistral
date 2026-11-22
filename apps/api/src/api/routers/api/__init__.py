"""The HTTP API mounted at ``/api``; child packages declare access rules.

This app declares ``()`` — gateway-anonymous — on purpose, and that is a *different* layer from
the bank's customer authentication: the Studio login gates who may open the deployed app at
all, while every route here resolves the fictional customer's own session cookie in-band (see
``api.auth``). The two are never conflated; README's authentication paragraph says so explicitly.
"""

from fastapi import params

# The access rule cascading to every module under /api: empty, because app-level access is
# the Studio login's job and customer auth is handled per route by api.auth dependencies.
dependencies: tuple[params.Depends, ...] = ()
