"""Bot handlers package."""

from aiogram import Router

from . import admin, cheque_menu, cheques, inline, invoices, start, swap, wallet


def setup_routers() -> Router:
    root = Router()
    root.include_router(admin.router)
    root.include_router(start.router)
    root.include_router(wallet.router)
    root.include_router(swap.router)
    root.include_router(cheque_menu.router)
    root.include_router(cheques.router)
    root.include_router(invoices.router)
    root.include_router(inline.router)
    return root
