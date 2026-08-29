# youzi_web/features/account/__init__.py — 账户(模拟盘 v1:live.db,持仓=fold(成交流水))
from youzi_web.features.account.router import router
from youzi_web.registry import Feature, SubNavItem

feature = Feature(
    id="account", label="账户", icon="💰", router=router,
    subnav=[SubNavItem("总览", "/account/overview")],
)
