# youzi_web/features/market/__init__.py
from youzi_web.features.market.router import router
from youzi_web.registry import Feature, SubNavItem

feature = Feature(
    id="market", label="市场", icon="📈", router=router,
    subnav=[SubNavItem("盘面", "/market/board")],
)
