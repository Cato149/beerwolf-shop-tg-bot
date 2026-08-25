from beerwolf_shop.presentation.telegram.handlers.admin import router as admin_router
from beerwolf_shop.presentation.telegram.handlers.common import router as common_router
from beerwolf_shop.presentation.telegram.handlers.customer import router as customer_router
from beerwolf_shop.presentation.telegram.handlers.order_wizard import router as order_router

__all__ = ["admin_router", "common_router", "customer_router", "order_router"]
